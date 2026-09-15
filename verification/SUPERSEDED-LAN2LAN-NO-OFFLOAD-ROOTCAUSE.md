# LAN↔LAN 为什么完全不能硬件加速 —— 根因定位

日期：2026-09-15
设备：GL-BE14000 = YT9224(eth1) + MT7530(eth0)，X-WRT 26.04_b202609121905，内核 6.18.44

---

## 一、结论

**不是 YT9224 的限制，也不是驱动 bug —— 是 x-wrt 自己打了个补丁，把整个 DSA 硬件卸载
（bridge offload / VLAN offload / STP 状态下发 / offload_fwd_mark）全部关掉了。**

补丁：`target/linux/generic/hack-6.18/999-Z-0300-dsa-disable-offload.patch`

```
From: Chen Minqiang <ptpt52@gmail.com>
Date: Fri, 15 May 2026 11:46:17 +0800
Subject: [PATCH] dsa: disable offload

Signed-off-by: Chen Minqiang <ptpt52@gmail.com>
---
 net/dsa/port.c   |  4 ++++
 net/dsa/switch.c | 20 ++++++++++----------
 net/dsa/tag.h    |  4 +---
 3 files changed, 15 insertions(+), 13 deletions(-)
```

`ptpt52` 就是 x-wrt 的作者。补丁**没有写任何理由**。
它在 `generic/hack-6.18`（不是 target 级），所以**影响 x-wrt 所有 DSA 机型**。

---

## 二、补丁做了什么

```c
/* net/dsa/port.c */
int dsa_port_set_state(struct dsa_port *dp, u8 state, bool do_fast_age)
{
	struct dsa_switch *ds = dp->ds;
	int port = dp->index;

+	return -EOPNOTSUPP;                     /* ← 直接返回，下面全成死代码 */
	if (!ds->ops->port_stp_state_set)
		return -EOPNOTSUPP;
	ds->ops->port_stp_state_set(ds, port, state);   /* 永不执行 */

/* 同样在 dsa_port_vlan_filtering() 里也有一个 return -EOPNOTSUPP; */

/* net/dsa/switch.c */
 	case DSA_NOTIFIER_BRIDGE_JOIN:
-		err = dsa_switch_bridge_join(ds, info);   /* 永不执行 */
+		err = -EOPNOTSUPP;
 	case DSA_NOTIFIER_VLAN_ADD:       -→ err = -EOPNOTSUPP;
 	case DSA_NOTIFIER_VLAN_DEL:       -→ err = -EOPNOTSUPP;
 	case DSA_NOTIFIER_HOST_VLAN_ADD:  -→ err = -EOPNOTSUPP;
 	case DSA_NOTIFIER_HOST_VLAN_DEL:  -→ err = -EOPNOTSUPP;
（另把若干函数改成 static inline，消 unused 警告）

/* net/dsa/tag.h */
 static inline void dsa_default_offload_fwd_mark(struct sk_buff *skb)
 {
-	struct dsa_port *dp = dsa_user_to_port(skb->dev);
-	skb->offload_fwd_mark = !!(dp->bridge);
+	return;                                  /* 变成空函数 */
 }
```

### 因果链（与实测完全吻合）

1. `DSA_NOTIFIER_BRIDGE_JOIN → -EOPNOTSUPP` ⇒ DSA **从不调用驱动的
   `port_bridge_join()`** ⇒ yt922x 驱动的 `p->yt922x_bridge` 永远是 NULL。
2. `dsa_port_set_state()` 恒返回 `-EOPNOTSUPP` ⇒ 驱动的 `port_stp_state_set()`
   **从不被调用** ⇒ `p->yt922x_stp_state` 恒为 `BR_STATE_DISABLED`。
3. 因此 `yt922x_bridge_learning()` 与 `yt922x_bridge_matrix()` 都算不出可转发状态
   （两者都要求 stp_state ∈ {LEARNING, FORWARDING}）→
   **端口隔离矩阵恒为「只允许到 CPU」，且端口学习恒为关闭**
   （这正是 `yt9222x_port_setup()` 在 probe 时写下的初值，之后再没被打开过）。
4. 硬件不学习 ⇒ ATU 无表项 ⇒ 所有单播都是「未知单播」⇒ 被 trap 到 CPU；
   隔离矩阵只放行 CPU ⇒ 所有跨口二层流量都走 SoC。
5. ⇒ **同芯片（lan2→sfp）、跨芯片（lan7→sfp）全部由 CPU 软件转发**，
   CPU 占用 14~30%，`eth0/eth1` 计数与入口口一一对应。

**注意 yt922x 驱动侧是完整的**：`967-42-net-dsa-yt922x-add-hardware-bridge-offload.patch`
实现了 `port_bridge_join` / `port_stp_state_set` / `port_bridge_flags` / `port_fast_age` /
`port_pre_bridge_flags` / `port_vlan_filtering`，`967-45/49/50` 实现了 FDB / MDB / 8021Q。
芯片判定也正确（`yt921x_infos` 里 `"YT9224", YT9224_MAJOR` → `yt922x_dsa_switch_ops`）。
**是上游 hack 把这条链从 DSA 核心处掐断的。**

---

## 三、实测证据

### 端口拓扑（权威）
| 接口 | ifindex | 速率 | 芯片 | DSA 端口号 |
|---|---|---|---|---|
| lan2 | 11 | 2500 | YT9224 (`mdio-bus:1d`, eth1, tag `yt922x_4b`) | p5 |
| sfp | 9 | 10000 | YT9224 | p0 |
| lan7 | 7 | 1000 | MT7530 (`15020000.switch`, eth0, tag `mtk`) | p2 |

### 二层转发实测（natflow 已按前一份报告修好，排除 natflow 干扰）

**同芯片 lan2 → sfp（2.35 Gbit/s）：**
```
lan2  rx=155.44  tx=0.26
sfp   rx=0.24    tx=155.91
eth0  rx=0        tx=0
eth1  rx=156.88  tx=156.86     ← CPU 口承载了全部流量
br-lan rx/tx ≈ 0
CPU 22.1%
```

**跨芯片 lan7 → sfp（795 Mbit/s）：**
```
lan7  rx=84.26  tx=0.40
eth0  rx=84.31  tx=0.40        ← MT7530 的 CPU 口
eth1  rx=0.42   tx=84.38       ← YT9224 的 CPU 口
sfp   tx=84.08
br-lan rx/tx ≈ 0
CPU 14.8%
```

两条路径都把流量交给 SoC ⇒ 交换芯片完全没参与二层转发。

### 排除过的其它可能（都验证过不是原因）
| 怀疑 | 结论 |
|---|---|
| `bridge-nf-call-iptables` | =0，无关 |
| br-lan `vlan_filtering` | =0，不会触发 MST/VLAN 限制 |
| 端口 flag（hairpin/isolated/locked/bcast_flood） | 全部合格（0/0/0/1） |
| MST | `BROPT_MST_ENABLED` 无 sysfs 可设，恒 false，`br_mst_enabled()` 过 |
| `max_num_bridges` | 两个驱动都没设 → 检查被跳过 |
| 多芯片同桥被拒 | 不会，`nbp_switchdev_hwdom_set()` 支持每芯片独立 hwdom |
| 芯片变体选错 ops | 不会，`YT9224_MAJOR` → `yt922x_dsa_switch_ops` |
| `port_setup` 覆盖桥配置 | 不会，`dsa_port_setup()` 只在 probe 时调用一次 |
| **强制重推 STP 状态** | 试过（`brctl setfd 0` + stp on/off 跳变），**无效** —— 因为
`dsa_port_set_state()` 被写死返回 `-EOPNOTSUPP`，桥的 STP 路径全部汇入这个桩函数 |

> 顺带纠正一个我自己犯过的误判：**Linux 桥 master 设备的 rx/tx 统计不包含转发帧**，
> 所以 `br-lan rx=0` 不能用来判断"是否绕过软件桥"。这条推断已作废。
> 真正的判据是 `eth0/eth1`（DSA conduit）的计数。

---

## 四、怎么修（需用户决策）

**直接做法**：把 `999-Z-0300-dsa-disable-offload.patch` 移出树（例如移到
`/mnt/data4t/flint4-xwrt/removed-patches/`），重新编译。让 DSA 硬件桥接恢复，
配合 yt9222x 驱动已有的 `port_bridge_join` 等实现，LAN↔LAN 应当转为硬件转发。

**但要谨慎**：这是 x-wrt 作者的主动选择，没有理由说明。可能的原因与风险：

1. **可能与 natflow 冲突**：x-wrt 的 natflow 自己在 PPE 层做加速，DSA 硬件桥接若是
   也接管同一条流量，可能出现双重转发 / `offload_fwd_mark` 语义冲突。
2. **broadcast 重复**：驱动 `967-42` 在 tagger 里对广播帧调
   `dsa_default_offload_fwd_mark()`，而该 hack 把它变成空函数 → 硬件已泛洪的广播帧
   还会被软件桥再转发一次（潜在重复广播）。移除 hack 后这个语义才正确。
3. 也可能只是规避某个当时未定位的 DSA/交换芯片老问题。

**建议的验证顺序**：
1. 先按 `removed-patches` 备份补丁 → 重编 → 刷机
2. 复测 LAN↔LAN（同芯片/跨芯片）吞吐与 CPU 占用
3. 复测 WAN 硬件卸载是否仍正常（`ppeBND` / CPU）
4. 若出现异常，立即把补丁放回去

---

## 五、与 natflow 那份报告的关系

前一份 `NATFLOW-DROP-ANALYSIS.md` 讲的是**掉到 0**（natflow 误快转 LAN↔LAN）。
本报告讲的是**能通但完全不吃硬件加速**（x-wrt 关掉了 DSA offload）。

两者会叠加，但不互相解释：
- 关掉 natflow 后 LAN↔LAN 能跑满（2.35G / 795M），但**全靠 CPU**
- 开着 natflow 且未修 bypass 组时，LAN↔LAN 直接归零
