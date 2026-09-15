# 04 · 已知缺口 / 尚未覆盖

诚实列出本适配层**没有**验证或**没有**移植的部分。

## 4.1 尚未移植到 `*1.c` 的 flint4 补丁

| 补丁 | 语义 | 现状 | 什么时候需要补 |
|---|---|---|---|
| `967-43-net-mediatek-ppe-match-yt922x-bridge-flows.patch` | PPE 接收侧识别 `yt922x_4b` 的 802.1Q 形状 CPU tag，跳过它再取桥接 VLAN 作为 L2 流 key | ❌ 未移植 | 使用 **`bridger` / tc-flower 二层桥接卸载**时 |
| `967-44-net-mediatek-ppe-retire-expired-bridge-subflow.patch` | 退役过期的桥接子流 | ❌ 未移植 | 同上 |
| `967-50-net-dsa-yt922x-add-8021q-vlan-offload.patch` 中的 `mtk_ppe*.c` 部分 | 802.1Q VLAN 卸载 | ⚠️ 部分未移植（`yt921x.c` / `tag_yt922x.c` / `net/dsa/user.c` 的部分**已生效**） | 需要用 DSA VLAN offload 而不是 natflow 的 8021q 处理时 |

**为什么当前不影响**：x-wrt 的加速路径是 natflow，它自己在 PPE 里用
**5 元组 IP 表项**（debugfs 显示 `IPv4 5T`）+ `FLOW_OFFLOAD_PATH_BRIDGE` 标记来处理 LAN↔LAN，
并不依赖 `mtk_ppe.c` 里那套 `l2_flows` 桥接匹配。
本仓库的修复已经让这条路径上的出口 tag 正确，实测 LAN↔LAN 与 WAN→LAN 均正常。

**但要注意**：GL-BE14000 的 profile 里**包含 `bridger`**
（对应提交 `mediatek: include bridger in the GL-BE14000 profile`）。
若真的启用 bridger 做二层卸载，就会走到那两个未移植的补丁上。
需要时按 `02` 文档同样的方法，把逻辑重放到 `mtk_ppe1.c`。

## 4.2 覆盖不全的测试

| 项 | 状态 | 说明 |
|---|---|---|
| LAN↔LAN 正向（2.5G 口 → 10G 口） | ✅ 已测 | 2.32~2.34 Gbit/s，CPU ~5% |
| LAN↔LAN 反向 | ✅ 已测 | 1.94~1.95 Gbit/s（与软件路径一致，受 Windows 接收侧限制） |
| 外网下载 WAN→LAN | ✅ 已测 | 30~53.5 MB/s，峰值 428 Mbit/s，不归零 |
| LAN→WAN 上行 | ✅ 间接验证 | 出口是 WAN 口（无 DSA tag），`vlan=0,0`，符合预期 |
| **lan5~lan8（MT7530 / `mtk` tag）↔ sfp 跨芯片** | ❌ **未实测** | 现场只有 Ubuntu(sfp) 与 Windows(lan2) 两台可驱动主机；lan7 上的设备不开放 iperf3。**代码上该分支一行未改** |
| **> 2.5 Gbit/s 的 LAN↔LAN** | ❌ 未测 | 测试客户端只有 2.5G 口，拿不到更高单流带宽；CPU 数据已足以证明卸载生效 |
| **IPv6 路径** | ❌ 未单独压测 | 本补丁同时改了 `mtk_offload_prepare_v6`，逻辑与 v4 对称 |
| **带客户 VLAN 的流（QinQ / tag 叠两层）** | ❌ 未测 | CPU tag 占一个 PPE VLAN 层，客户 VLAN 落到第 2 层；`mtk_foe_entry_set_vlan()` 第二层返回 `-ENOSPC` 时会被调用方的错误处理接住，未实测该分支 |
| Wi-Fi ↔ LAN（经 WDMA 出口） | ❌ 未测 | 出口与 YT9224 无关，但同一张 PPE 表 |

## 4.3 上游依赖风险

natflow 的 `mtk_ppe1.c` / `mtk_ppe_offload1.c` 是 **MediaTek 原文件的冻结副本**，因此：

- 上游对 `mtk_ppe.c` / `mtk_ppe_offload.c` 的修复**不会**进 `*1.c`；
- natflow 版本升级时 `*1.c` 的基线会跳变，本补丁需要按 `02` 文档重放（**打不上会报错，不会静默**）；
- 同理，flint4 补丁集后续若新增改动 `mtk_ppe*.c` 的补丁，也需要同样的搬运。

建议：每次同步 natflow 或 flint4 之后，先跑一次

```sh
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt
```

## 4.4 与 x-wrt 作者的沟通

本适配**没有**改动 x-wrt 的任何策略（尤其没有动
`999-Z-0300-dsa-disable-offload.patch`）。如果上游愿意直接吸收，
最省事的形态是让 natflow 的 `995` 补丁在生成 `mtk_ppe_offload1.c` 时，
把 `mtk_flow_get_dsa_port()` / `mtk_flow_set_output_device()` 的 `YT922X_4B` 分支一并带进去 ——
那样本补丁就可以退役。
