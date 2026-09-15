# 硬件转发为什么失败 —— 根因定案（取代 LAN2LAN-NO-OFFLOAD-ROOTCAUSE.md）

日期：2026-09-15 晚
设备：GL.iNet GL-BE14000（`192.168.15.1`），X-WRT `26.04_b202609121905`，内核 6.18.44
结论一句话：**natflow 的 995 补丁把编译对象换成了 `mtk_ppe_offload1.c`，而 YT9224 四字节 tag
的支持只写在不再参与编译的 `mtk_ppe_offload.c` 里 → 硬件卸载的出口 tag 用错格式 → YT9224 解不出
目的口 → 静默丢帧。**

---

## 〇、先纠正上一版结论

上一版报告把矛头指向 x-wrt 作者的
`999-Z-0300-dsa-disable-offload.patch`（关掉 DSA 交换机卸载）。

**作者 ptpt52 说明：那是故意的** —— 关掉交换机 offload，正是为了让 LAN↔LAN 上到 PPE 里做
**硬件转发**（`Port → PPE → Port`）。所以：

- `999-Z-0300` 是**设计选择，不是 bug 出处**
- 真正的 bug 是 **硬件转发本身失败**，也就是本报告要讲的东西

`LAN2LAN-NO-OFFLOAD-ROOTCAUSE.md` 的因果链分析（`dst_port_set_state → -EOPNOTSUPP` 等）在
"现象解释"层面仍然成立，但它给出的"修法"（把补丁移出树）是**方向性错误**，不要再执行。

---

## 一、实测定界：问题只在硬件卸载路径

真机，natflow 用**作者出厂默认**（`ifname_group_type=0`、`ifname_group` 空），
Windows 2.5G 口（lan2，YT9224）↔ Ubuntu 万兆口（sfp，YT9224），iperf3：

| natflow `hwnat` | 结果 | 说明 |
|---|---|---|
| `hwnat=0`（只关硬件 offload，保留软件快转） | **2.34 Gbit/s** | 满速，正确 |
| `hwnat=1`（出厂默认） | **0.087 ~ 0.15 Gbit/s** | 崩 |

⇒ **软件快转完全没问题；缺陷 100% 落在 PPE 硬件卸载路径上。**

采样期间线速统计（`sfp tx`）约 **542 Mbit/s**，而 iperf3 只统计到 87 Mbit/s
⇒ **约 6 倍重传放大**：帧确实发出去了，但对端收不到 / 收错。

---

## 二、PPE 表项其实已经建对了（所以故障是"静默"的）

`/sys/kernel/debug/ppe1/entries`（ppe1 = eth1 = YT9224 那一侧）在传输中：

```
BND IPv4 5T orig=192.168.15.129:63490->192.168.15.157:5201  ...  etype=0100
BND IPv4 5T orig=192.168.15.157:5201->192.168.15.129:63490  ...  etype=2000
```

- `etype` 是 debugfs 字节序翻转后的值：`0100 → 0x0001 = BIT(0)`、`2000 → 0x0020 = BIT(5)`
- 按本机拓扑：**YT9224 p0 = sfp**（Ubuntu 在 sfp）、**p5 = lan2**（Windows 在 lan2）
- 两个方向的 **BND 都已绑定、DSA 端口位都对**，MAC 也对（源→目的）

也就是说：**控制面全对，数据面发的帧是废的。** 这正是"能 ping 通但一压带宽就崩"的形态。

---

## 三、根因（源码级）

### 3.1 x-wrt 的 natflow 补丁顶掉了两个源文件

`target/linux/mediatek/patches-6.18/995-0001-hwnat-add-natflow-flow-offload-support.patch`
（作者 Chen Minqiang）**新增** `mtk_ppe1.c` / `mtk_ppe_offload1.c`，并把 Makefile 改成：

```make
mtk_eth-y := mtk_eth_soc.o mtk_eth_path.o mtk_ppe1.o mtk_ppe_debugfs.o mtk_ppe_offload1.o
```

⇒ **`mtk_ppe.c` 与 `mtk_ppe_offload.c` 在这个树上根本不参与编译。**
（已实测确认：`mtk_ppe1.o` / `mtk_ppe_offload1.o` 存在且有 `mtk_ppe.c` / `mtk_ppe_offload.c` 的 `.o` 不存在）

⚠️ 项目记忆里记的是"任何改 `mtk_ppe_offload.c` 的补丁是死代码"，这次是同一个坑踩在**整个文件**上。

### 3.2 YT9224 的 tag 支持正好写在死文件上

JiaY-shi 的 flint4 补丁集里：

| 补丁 | 改的文件 | 在本树是否生效 |
|---|---|---|
| `967-41-net-mediatek-ppe-support-yt922x-four-byte-port-tag.patch` | `mtk_ppe_offload.c` | ❌ **死代码** |
| `967-43-net-mediatek-ppe-match-yt922x-bridge-flows.patch` | `mtk_ppe.c` | ❌ **死代码** |

实测：`mtk_ppe1.c` / `mtk_ppe_offload1.c` 里 `YT922X` 命中数 = **0**。

### 3.3 于是出口 tag 用错了格式

两条 tag 格式完全不一样：

| | YT9224（`yt922x_4b`，eth1） | MT7530（`mtk`，eth0） |
|---|---|---|
| 目标 4 字节头 | `81 00` + `yt922x_4b_port_tag(port)` | `[attr][portmask][00][00]` |
| 端口编码 | `FIELD_PREP(GENMASK(13,5), BIT(port))`，端口 7 → `0x1000` | `BIT(port)` 直接放 portmask 字节 |

而**参与编译**的 `mtk_ppe_offload1.c` 只有一条出路口：

```c
if ((dest->dsa_port & 0xff00)) {
        mtk_foe_entry_set_vlan(eth, entry, dest->dsa_port >> 4);   /* 802.1Q 形状，MXL862 用 */
} else {
        mtk_foe_entry_set_dsa(eth, entry, dest->dsa_port);          /* MTK 私有 tag */
}
```

`yt922x_4b` 不置 `0xff00` 位（只有 `MXL862_8021Q` 会置），所以走 `mtk_foe_entry_set_dsa()`：

```c
l2->etype = BIT(port);          /* 硬件把 [etype][vlan1] 当 4 字节头发出 → 00 <portmask> 00 00 */
```

**YT9224 收到 `00 20 00 00` 这种头，按自己那套 802.1Q 形状的规则解析 → 解不出目的口 → 丢帧。**

### 3.4 硬件插入语义（读 `mtk_ppe1.c` 反推，以后可复用）

PPE 发出的 4 字节头 = `[l2->etype][l2->vlan1]`：

- `mtk_foe_entry_set_dsa()`：`etype = BIT(port)` + 清 vlan_tag + vlan_layer=1
  → 发 `00 <portmask> 00 00`（MTK 私有 tag）
  （若已有 vlan 层则 `etype |= BIT(8)` → 首字节变 `0x01`，正好对应
   `MTK_HDR_XMIT_TAGGED_TPID_8100`，即"后面还跟一个 802.1Q 标签"）
- `mtk_foe_entry_set_vlan()` case 0：置 vlan_tag + vlan_layer=1、`vlan1 = vid`
  → 硬件发 `0x8100 | vid` —— **802.1Q 形状**，这正是 MXL862_8021Q 和 YT9224_4B 都要的形状

所以正确做法就是：**把端口 ctrl 塞进 VLAN TCI 走 `set_vlan()`，而不是走 `set_dsa()`。**

### 3.5 为什么"外网下载也掉 0"

WAN→LAN 的回流方向，出口同样是 YT9224 用户口（sfp/lanN）→ 同一个 bug。
只有 **LAN→WAN 上行**（出口是 gmac2 WAN 口，无 DSA tag）是好的 —— 与用户观察一致。

也可以反推：如果测试机能挂到 **lan5~lan8（MT7530，tag proto = `mtk`）**，
当前固件的硬件卸载应该是正常的，因为 `set_dsa()` 产出的正是 `mtk` 格式。待验证。

---

## 四、修复

新增补丁（必须编号 **999**，996/997 都已被 x-wrt 自己的补丁占用）：

```
target/linux/mediatek/patches-6.18/999-0001-net-mediatek-ppe1-offload-yt922x-four-byte-port-tag.patch
```

把 967-41 的逻辑搬到**参与编译**的 `mtk_ppe_offload1.c`，两处相同站点（IPv4/IPv6 路径）都改：

```c
if ((dest->dsa_port & 0xff00)) {
        mtk_foe_entry_set_vlan(eth, entry, dest->dsa_port >> 4);
} else if (dest->dev->dsa_ptr &&
           dest->dev->dsa_ptr->tag_ops->proto == DSA_TAG_PROTO_YT922X_4B) {
        u16 ctrl = yt922x_4b_port_tag(dest->dsa_port);
        if (!ctrl)
                return -EOPNOTSUPP;
        mtk_foe_entry_set_vlan(eth, entry, ctrl);      /* → 硬件发 81 00 | ctrl */
} else {
        mtk_foe_entry_set_dsa(eth, entry, dest->dsa_port);
}
```

同时**删除** `natflow-dsa-bypass`（init.d + hotplug + `rc.d/S96` 软链）——
它会把 `ifname_group_type` 强制成 `2`，等于把作者想要的 LAN↔LAN 硬转又关掉。

- 构建树：`/mnt/data4t/flint4-xwrt/x-wrt-flint4`，分支 `flint4-pr-build`
- commit：`d1b67bef904`
- 补丁已用 `git apply --check` + `patch -p1` 双验证，且落盘后与目标文件逐字节对比一致

---

## 五、刷新固件后要跑的验证

1. 确认 natflow 是作者默认：`ifname_group_type=0`、`ifname_group` 空、`hwnat=1`
2. **LAN↔LAN**（Windows lan2 ↔ Ubuntu sfp）：目标 ≈ 2.34 Gbit/s（2.5G 口线速），CPU 应显著低于 22%
3. 抓 `ppe1`：`BND` 条目两个方向都在，`etype` 应变成 `0100`(sfp) / `2000`(lan2) 之外的形式
   —— 改成 VLAN 路径后 `etype` 会回到载荷 ethertype（0608=0x0800、dd86=0x86dd），
   端口 ctrl 转到了 `vlan=` 字段
4. **外网下载**（WAN→LAN）：不再掉 0
5. 跨芯片 **lan7（MT7530）↔ sfp（YT9224）**：两个方向都验证
6. 异常时回滚：把 999 补丁移到 `/mnt/data4t/flint4-xwrt/removed-patches/` 重编

---

## 六、方法论教训（写进长期记忆了）

> `grep -rl <符号> target/linux/` 命中补丁 **≠** 补丁生效。

判断"某特性有没有编进去"，第一步先看目标 `.c` **在不在 `Makefile` 的 `mtk_eth-y` 里**。
本树已知被 natflow 顶掉的文件：`mtk_ppe.c`、`mtk_ppe_offload.c`（只看 `*1.c`）。
