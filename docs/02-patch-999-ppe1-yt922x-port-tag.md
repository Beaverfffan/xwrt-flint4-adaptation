# 02 · `999-0001-net-mediatek-ppe1-offload-yt922x-four-byte-port-tag.patch` 完整适配说明

这是本仓库的**核心新文件**。它只改一个文件：`drivers/net/ethernet/mediatek/mtk_ppe_offload1.c`
（natflow 的 PPE 卸载实现，见 `01-natflow-deadcode-conflict.md`）。

---

## 1. 它等价于什么

等价于把 flint4 的
`967-41-net-mediatek-ppe-support-yt922x-four-byte-port-tag.patch`
（原作者 **JiaY-shi**）的**出口 tag 部分**，从 `mtk_ppe_offload.c` 重放到 `mtk_ppe_offload1.c`。

- 对 **`mtk`（MT7530）** 协议：行为一行不变。
- 对 **`yt922x_4b`（YT9224）** 协议：出口 tag 从 MediaTek 私有格式改为 802.1Q 形状。
- 其它 tagger（含 8 字节的 `yt922x`）：仍然走老分支，即保持不卸载（软件转发）。

---

## 2. 背景：PPE 到底把什么放进那 4 个字节

MediaTek PPE 对「`vlan_layer = 1` 且未置 `vlan_tag` 位」的表项，会在 SA 之后插入
**4 字节头 = `[l2->etype][l2->vlan1]`**（各 2 字节）。两种目标协议要的内容完全不同：

| | YT9224（`yt922x_4b`，eth1） | MT7530（`mtk`，eth0） |
|---|---|---|
| 需要发出的 4 字节 | `81 00` + `yt922x_4b_port_tag(port)` | `[attr][portmask][00][00]` |
| 端口编码 | `FIELD_PREP(GENMASK(13,5), BIT(port))` | `BIT(port)` 直接放 portmask 字节 |
| PPE 里怎么设 | `etype` 保持载荷 ethertype，`vlan1 = ctrl` | `etype = BIT(port)`，`vlan1 = 0` |

`mtk_foe_entry_set_dsa()` 做的事是后者：

```c
l2->etype = BIT(port);                                  /* 硬件头变成 00 <portmask> 00 00 */
if (!(entry->ib1 & vlan_layer_mask))
        entry->ib1 |= mtk_prep_ib1_vlan_layer(eth, 1);
else
        l2->etype |= BIT(8);                            /* 首字节 0x01 = TAGGED_TPID_8100 */
entry->ib1 &= ~mtk_get_ib1_vlan_tag_mask(eth);
```

`mtk_foe_entry_set_vlan()` 做的事是前者：

```c
case 0:
        entry->ib1 |= vlan_tag_mask | vlan_layer(1);
        l2->vlan1 = vid;                                /* 原样写入，16 位 TCI 全保留 */
        return 0;
```

**关键点**：`set_vlan()` 会把 `vid` **原样**写进 `vlan1`，所以
`yt922x_4b_port_tag()` 那种带 bit12/bit13 的 TCI 能完整保留（967-41 的 commit message
特意提醒过「Keep the full TCI, including DEI: physical port 7 is encoded as 0x1000」）。

`yt922x_4b` tagger 侧（`net/dsa/tag_yt922x.c`）验证了这个形状：

```c
static struct sk_buff *yt922x_4b_tag_xmit(...)
{
        tag[0] = htons(ETH_P_8021Q);              /* 81 00 */
        tag[1] = htons(ctrl);                     /* ctrl = yt922x_4b_port_tag(dp->index) */
}
```

所以：**要发 `81 00 | ctrl`，唯一正确的 API 就是 `mtk_foe_entry_set_vlan(eth, entry, ctrl)`。**

---

## 3. 端口 ctrl 查表

`yt922x_4b_port_tag(port) = FIELD_PREP(GENMASK(13,5), BIT(port)) = BIT(port) << 5`
（定义在 `include/linux/dsa/yt922x.h`）：

| DSA 端口号 | ctrl | GL-BE14000 上是哪个口 |
|---|---|---|
| 0 | `0x0020` = 32 | **sfp**（10G） |
| 1 | `0x0040` = 64 | lan1 |
| 2 | `0x0080` = 128 | lan3 |
| 3 | `0x0100` = 256 | lan4 |
| 4 | `0x0200` = 512 | — |
| 5 | `0x0400` = 1024 | **lan2**（2.5G） |
| 6 | `0x0800` = 2048 | — |
| 7 | `0x1000` = 4096 | （DEI 位，967-41 注释提到的特例） |
| 8 | `0x2000` = 8192 | — |

真机上正是这两个值：

```
BND ...15.157:5201->15.129:61622 ... etype=0008 vlan=1024   # 出口 lan2（端口 5）
BND ...15.129:61622->15.157:5201 ... etype=0008 vlan=32     # 出口 sfp （端口 0）
```

---

## 4. 逐 hunk 说明

### 4.1 Hunk #1 — 头文件

```diff
 #include <net/dsa.h>
 #include <linux/dsa/8021q.h>
+#include <linux/dsa/yt922x.h>
```

`DSA_TAG_PROTO_YT922X_4B` 来自 `include/net/dsa.h`（已有），
但 `yt922x_4b_port_tag()` 是 `include/linux/dsa/yt922x.h` 里的 `static inline`，必须显式包含。
该头文件由 flint4 的 `967-40-net-dsa-yt922x-add-selectable-four-byte-port-tag.patch` 提供，
与本补丁同属 `target/linux/mediatek/patches-6.18/`，作用域一致。

### 4.2 Hunk #2 / #3 — 两处**完全相同**的站点

`mtk_ppe_offload1.c` 里有两份对称的出口设备准备代码：

| 函数 | 用途 | 本补丁命中的行（打完补丁后） |
|---|---|---|
| `mtk_offload_prepare_v4()` | IPv4 卸载表项 | hunk #2，约 348 行 |
| `mtk_offload_prepare_v6()` | IPv6 卸载表项 | hunk #3，约 490 行 |

两处都改成：

```diff
 		if ((dest->dsa_port & 0xff00)) {
 			mtk_foe_entry_set_vlan(eth, entry, dest->dsa_port >> 4);
+		} else if (dest->dev->dsa_ptr &&
+		           dest->dev->dsa_ptr->tag_ops->proto == DSA_TAG_PROTO_YT922X_4B) {
+			/* The YT9224 four-byte CPU tag is 802.1Q shaped:
+			 * 0x8100 + yt922x_4b_port_tag().  The MediaTek private
+			 * tag produced by mtk_foe_entry_set_dsa() (BIT(port)
+			 * in the etype field) cannot be decoded by that
+			 * switch, so push the port ctrl through the VLAN TCI.
+			 */
+			u16 ctrl = yt922x_4b_port_tag(dest->dsa_port);
+
+			if (!ctrl)
+				return -EOPNOTSUPP;
+			mtk_foe_entry_set_vlan(eth, entry, ctrl);
 		} else {
 			mtk_foe_entry_set_dsa(eth, entry, dest->dsa_port);
 		}
```

**为什么插在第一个分支之后**：原有分支 `(dest->dsa_port & 0xff00)` 是给
`MXL862_8021Q` 用的 —— 那种 tagger 的 `dsa_flow_offload_check()` 会把
`standalone_vid << 4` 打包进 `dsa_port` 高位，然后在这里 `>> 4` 取回并走 `set_vlan()`。
**它和 YT9224 需要的是同一种「802.1Q 形状 tag」机制**，所以新分支紧挨着它、复用同一个 API，
语义上是一致的。区别只是 YT9224 的 ctrl 直接来自 `yt922x_4b_port_tag()`，
不需要借高位打包（YT9224 的 ctrl 最高到 `0x2000`，左移 4 位会溢出 u16，**不能**照抄 MXL 的打包方式）。

**`-EOPNOTSUPP` 而非静默**：`yt922x_4b_port_tag()` 对 `port > 8` 返回 0。
真出现这种端口说明拓扑超出预期，此时**拒绝卸载**让流量留给软件快转，
比发一个错 tag 出去（就是本次要修的故障形态）安全得多。函数返回非 0 时
调用方 `mtk_flow_offload_add()` 会放弃下发该流。

**为什么不动 `else` 分支**：`mtk`（MT7530）协议需要的正是 `BIT(port)` 私有 tag，
`mtk_foe_entry_set_dsa()` 对它是对的。所以 `else` 一行不改 —— 这也意味着
**lan5~lan8（MT7530）不受本补丁影响**。

---

## 5. 补丁文件名为什么是 999

`target/linux/mediatek/patches-6.18/` 里 996/997/998 都已被 x-wrt 自己的补丁占用
（`996-net-dsa-mt7530-an8855-reset.patch`、`997-mediatek-64-KiB-reserved-for-ramoops-pstore.patch`、
`998-mtd-spinand-...`）。补丁按文件名排序应用，取 **999** 保证排在 natflow 的 `995` **之后**，
并且不与既有编号撞车。

---

## 6. 风险与回滚

| 风险 | 评估 |
|---|---|
| 影响 MT7530 / 其它 tagger | **无** —— 新分支有 tag proto 判定，`else` 未改动 |
| YT9224 上带客户 VLAN 的流 | tag 占用一个 PPE VLAN 层，客户 VLAN 会落到第 2 层（PPE 支持 2 层）。**未专门压测**，见 `04-known-gaps.md` |
| 端口号 > 8 | 直接 `-EOPNOTSUPP` 回落软件，不会出错包 |
| natflow 升级后 `*1.c` 基线变化导致补丁打不上 | 打不上会**立刻报错**（不会静默），按第 2、4 节把逻辑重放即可 |

回滚：

```sh
mv target/linux/mediatek/patches-6.18/999-0001-net-mediatek-ppe1-offload-yt922x-four-byte-port-tag.patch \
   /path/outside/tree/
```

---

## 7. 怎么确认补丁**真的**生效了（别用 grep）

因为 natflow 的 `*1.c` 是独立文件，`grep` 源码树**不能**证明它被编译。可靠办法：

```sh
# 1. 对象文件必须重建且变大（本例 70600 -> 74664 字节）
ls -la build_dir/target-*/linux-*/linux-*/drivers/net/ethernet/mediatek/mtk_ppe_offload1.o

# 2. 落盘的源码里两处站点都在
grep -c DSA_TAG_PROTO_YT922X_4B \
    build_dir/target-*/linux-*/linux-*/drivers/net/ethernet/mediatek/mtk_ppe_offload1.c
#   期望 2

# 3. 镜像 sha256 必须变（对比打补丁前后的产物）

# 4. 真机看 PPE 表项：出口是 YT9224 口时应当 etype=载荷ethertype、vlan=<ctrl>
#    debugfs 打印的 etype 经过字节序翻转：IPv4 载荷 0x0800 -> 打印 0008
cat /sys/kernel/debug/ppe1/entries | grep BND
#    修复前：etype=2000 / 0100（= BIT(port)），vlan=0,0
#    修复后：etype=0008（IPv4），vlan=32（sfp）/ 1024（lan2）
```

第 4 步是最硬的证据，配合吞吐与 CPU 一起看，见 `07-verification.md`。
