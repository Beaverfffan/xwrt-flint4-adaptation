# 03 · 被删除的「绕过方案」：`natflow-dsa-bypass`

定位问题的中途，树上曾短暂加入过一套脚本 `natflow-dsa-bypass`
（`/etc/init.d/` + `/etc/hotplug.d/iface/22-natflow-dsa-bypass` + `rc.d/S96` 软链）。
**它已经从固件里彻底移除，本仓库不收录。** 这一页解释为什么，免得后人重新踩进来。

---

## 它做了什么

把 natflow 配成「LAN 口之间不加速」：

```sh
uci set natflow.main.ifname_group_type='2'      # 2 = fastnat_ifname_group_bypass
for i in lan1 lan2 lan3 lan4 lan5 lan6 lan7 lan8 sfp; do
    uci add_list natflow.main.ifname_group="$i"
done
```

`natflow_path.c:2404` 的判定语义：

| `ifname_group_type` | 语义 |
|---|---|
| `0` = `fastnat_for_all` | 全部流都尝试快转（**出厂默认**） |
| `1` = `fastnat_ifname_group_only` | 只有 **orig 与 reply 两端都在组内** 才快转 |
| `2` = `fastnat_ifname_group_bypass` | **两端都在组内就跳过**快转 |

⇒ `type=2` + 全 LAN 口，效果是「两端都是 LAN 口的流（= LAN↔LAN）不加速」。

## 为什么它「看起来有效」

- LAN↔LAN 吞吐从 **0.087 Gbit/s 恢复到 2.3 Gbit/s**（退回 Linux 软件桥转发）
- 因为 LAN↔LAN 都是桥接流，绕过 natflow 后就不会再把错 tag 写进 PPE

于是它把症状盖住了：**能跑满，但 CPU 22%~33%，硬件转发完全没参与。**

## 为什么必须删

1. **方向错了**：x-wrt 作者 ptpt52 明确说明，x-wrt 关掉交换机 offload
   （`target/linux/generic/hack-6.18/999-Z-0300-dsa-disable-offload.patch`）**是故意的**，
   目的正是让 LAN↔LAN 上到 PPE 做 `Port → PPE → Port` 硬转。
   这套脚本等于反其道而行，把作者想要的能力关掉。
2. **掩盖真实故障**：绕过之后 PPE 不再接管 LAN↔LAN，没人会去看 tag 对不对。
3. **它不解决 WAN→LAN**：外网下载的回流方向出口同样是 YT9224 用户口，
   用 `type=2` 挡不住（`type=2` 只排除「两端都在组内」的流），所以下载还是会掉速。
   **只堵 LAN↔LAN 一个症状，是不完整的修法。**
4. **跨升级残留**：它是 uci 配置，`sysupgrade` 会保留 ——
   刷了新固件后仍然生效，会让「修复是否生效」的验证直接失真（本次就遇到了这点）。

## 教训

> 「把出问题的路径从加速里排除」在**症状**层面永远有效，但它不是修复。
> 判定一个改动是不是真修复，要同时看**吞吐 + CPU + PPE 表项**三样：
> 只吞吐恢复、CPU 依然高、PPE 没有对应 BND 表项 → 那只是绕过了。

## 正确的替代

正确修法是让 PPE 出口发对 tag：见 `02-patch-999-ppe1-yt922x-port-tag.md`。

如果只想要「先能用」的应急手段（例如在现场无法立刻重编），
**应临时用 `hwnat=0`**，它只关硬件卸载、保留软件快转，语义清晰且不伪造「已修复」的假象：

```sh
uci set natflow.main.hwnat=0 && uci commit natflow && /etc/init.d/natflow-boot start
```

但如果最终目标是「LAN↔LAN 走硬转」，这两种做法的结果是一样的：
**都没有硬转** —— 只是 `hwnat=0` 更诚实。
