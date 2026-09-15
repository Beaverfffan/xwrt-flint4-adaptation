# 硬件转发修复 —— 真机验证报告（通过）

日期：2026-09-15 21:30 ~ 21:40
设备：GL.iNet GL-BE14000（`192.168.15.1`）
固件：X-WRT `26.04_b202609121905`，revision **`r0+36480-d1b67bef904`**（= 含 999 补丁那版）
内核：6.18.44

---

## 一、测试环境

| 角色 | 地址 | 接入 | 交换芯片 / tag |
|---|---|---|---|
| iperf3 服务端（`-s -p 5201`） | Ubuntu `192.168.15.157` | **sfp**（10G） | YT9224 / `yt922x_4b`（eth1） |
| iperf3 客户端 | Windows `192.168.15.129` | **lan2**（2.5G） | YT9224 / `yt922x_4b`（eth1） |

两个测试口**同属 YT9224** —— 正是本次修复针对的那颗芯片。
（`lan5-8` 走 MT7530 / `mtk` tag，本次未改动其代码路径）

natflow 配置为**作者出厂默认**，未做任何绕过：
```
ifname_group_type = 0        # fastnat_for_all
ifname_group     = (空)      # ^ifname_group_add 计数 = 0
hwnat            = 1
```

---

## 二、结论：修复通过

### 2.1 LAN↔LAN 吞吐（iperf3 `-P 8`）

| 配置 | 正向 Win→Ubuntu | 反向 Ubuntu→Win | CPU 忙 |
|---|---|---|---|
| 修复前，`hwnat=1` | **0.087 ~ 0.15 Gbit/s** | — | — |
| 修复后，`hwnat=1` | **2.32 / 2.34 / 2.34 Gbit/s** | 1.95 / 1.94 Gbit/s | **~2~12%（均 ~5%）** |
| 修复后，`hwnat=0`（对照） | 2.30 / 2.34 Gbit/s | 1.93 / 1.93 Gbit/s | **29~38%（均 ~33%）** |

2.34 Gbit/s = **Windows 2.5G 口的线速**，已经是这条链路的上限。
反向 1.95 Gbit/s 与 `hwnat=0` 的 1.93 Gbit/s 一致 → 是 Windows 接收侧的既有上限，
不是本次改动引入的。

**关键判据是 CPU**：同样跑满 2.34 Gbit/s，
`hwnat=0` 要 33% CPU，`hwnat=1` 只要 ~5% —— **硬件卸载真的接管了**，
而且不再有之前的重传放大（此前线速 542 Mbit/s 换 87 Mbit/s 有效吞吐，约 6 倍放大）。

### 2.2 PPE 表项：tag 编码已经换成 YT9224 的格式

修复后传输中的 `ppe1`（eth1 侧）：

```
BND orig=192.168.15.129:61622->192.168.15.157:5201  eth=1c:86:0b:3d:7f:3a->98:03:9b:a1:69:73
                                                     etype=0008  vlan=32    ib1=20144075
BND orig=192.168.15.157:5201->192.168.15.129:61622  eth=98:03:9b:a1:69:73->1c:86:0b:3d:7f:3a
                                                     etype=0008  vlan=1024  ib1=20144075
```

对照 `yt922x_4b_port_tag(port) = FIELD_PREP(GENMASK(13,5), BIT(port))`：

| 出口 | 期望 ctrl | debugfs `vlan=` | |
|---|---|---|---|
| sfp = 端口 0 | `BIT(0)<<5 = 0x020 = 32` | **32** | ✓ |
| lan2 = 端口 5 | `BIT(5)<<5 = 0x400 = 1024` | **1024** | ✓ |

- `etype=0008`（= `0x0800`，载荷 ethertype）—— 不再是之前的 `BIT(port)`
- 端口 ctrl 出现在 `vlan1` 字段 → 硬件发 `81 00 | ctrl`，即 YT9224 要的 802.1Q 形状 tag
- **修复前**同一位置是 `etype=2000 / 0100` 且 `vlan=0,0`（MTK 私有 tag），目的端收不到

### 2.3 外网下载（WAN→LAN）也不再掉 0

Ubuntu 从华为云镜像拉 ISO（出口 = sfp / YT9224）：

| 配置 | 3 次下载 |
|---|---|
| `hwnat=0` | 39.6 / 48.1 / 11.5 MB/s |
| `hwnat=1` | 33.6 / 33.8 / 30.3 MB/s，另一次实测 37.6 / **53.5 MB/s（428 Mbit/s）** |

**稳定、不归零**，峰值 428 Mbit/s；期间 CPU 忙 ~5.1%。

同时抓到回流方向的卸载表项，**出口 tag 正确**：
```
BND orig=120.46.63.139:443->192.168.51.173:49248  new=120.46.63.139:443->192.168.15.157:49248
    eth=72:db:ff:29:66:bf->98:03:9b:a1:69:73  etype=0008  vlan=32  ib1=205440e4
```
- 目的 MAC = Ubuntu（在 sfp），`vlan=32` = sfp 的 ctrl ✓
- 上行方向（出口 = WAN 口，无 DSA tag）`vlan=0,0` ✓ 符合预期

### 2.4 运行状态

- `dmesg` 无 natflow / DSA / PPE 相关报错，也没有 `-EOPNOTSUPP` 回落记录
- 内存 2,030,200 KB（1.94 GiB，与 GL 规格 DDR4 2GB 一致），load 0.01
- `natflow-dsa-bypass` 脚本已从固件中消失（`ls` 无此文件）

---

## 三、未覆盖的部分（诚实说明）

1. **跨芯片 lan7（MT7530，`mtk` tag）↔ sfp（YT9224）未实测** ——
   现场只有 Ubuntu（sfp）与 Windows（lan2）两台可驱动的主机；
   `lan7` 那个 1G 链路上的设备（`192.168.15.130`）不开放 iperf3。
   **代码层面可保证不受影响**：本次只改了
   `dest->dev->dsa_ptr->tag_ops->proto == DSA_TAG_PROTO_YT922X_4B` 这一条新分支，
   `mtk` 协议仍走原来的 `else { mtk_foe_entry_set_dsa(...) }`，一行未动。
2. **>2.5 Gbit/s 的 LAN↔LAN 未验证** —— 受限于 Windows 只有 2.5G 口，
   拿不到更高的单流带宽；CPU 数据已足以证明卸载生效。
3. IPv6 路径（本补丁同时改了 `mtk_offload_prepare_v6`）未单独压测。

---

## 四、回滚方式

```sh
mv target/linux/mediatek/patches-6.18/999-0001-net-mediatek-ppe1-offload-yt922x-four-byte-port-tag.patch \
   /mnt/data4t/flint4-xwrt/removed-patches/
# 重编
```

或真机上临时规避（会一并关掉 LAN↔LAN 硬转，仅作应急）：
```sh
uci set natflow.main.hwnat=0 && uci commit natflow && /etc/init.d/natflow-boot start
```
