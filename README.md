# xwrt-flint4-adaptation

把 [JiaY-shi](https://github.com/JiaY-shi/openwrt) 的 **flint4**（GL.iNet GL-BE14000 / YT9224 交换机）支持
适配到 **x-wrt** 的补丁与说明。

> **配套仓库（可直接编译的完整源码分支）**：
> <https://github.com/Beaverfffan/x-wrt-flint4>
> —— 基于 x-wrt tag `26.04_b202609121905` + flint4 支持 + 本仓库的修复补丁，
> `main` 分支 clone 下来就能编；分支迁移方法见其根目录 `FLINT4-XWRT.md`。
> **本仓库只放适配层（原理、补丁、工具、验证），不放整棵源码树。**

x-wrt 自带 `natflow` 硬件加速栈，它替换了 MediaTek 以太网驱动里的两个 PPE 源文件。
flint4 补丁集中所有改这两个文件的补丁在 x-wrt 上会**静默失效**（编译进去的是另一份拷贝），
表现为**硬件转发完全不可用**：PPE 表项正常绑定、端口位也对，但帧在交换机上被丢弃到几乎断流。

本仓库给出：

1. 这一冲突的**成因与通用检测方法**；
2. 让 YT9224 四字节端口 tag 重新生效的**修复补丁**；
3. **真机验证数据**（吞吐 / CPU / PPE 表项）；
4. 一个**通用检测脚本**，用来在任意 x-wrt + 上游补丁集组合里找出同类死代码。

---

## 一句话结论

> 在 x-wrt 上，凡是 `+++ b/drivers/net/ethernet/mediatek/mtk_ppe.c`
> 或 `mtk_ppe_offload.c` 的补丁**都是死代码** ——
> 编译的是 natflow 的 `mtk_ppe1.c` / `mtk_ppe_offload1.c`。
> 把逻辑搬到 `*1.c` 才能生效。

---

## 症状与定位（GL-BE14000 实测）

natflow 使用作者出厂默认（`ifname_group_type=0`、接口组为空、`hwnat=1`），
测试机接在 **lan2（2.5G，YT9224）** 与 **sfp（10G，YT9224）**：

| 配置 | LAN↔LAN 吞吐 | CPU 忙 |
|---|---|---|
| 修复前 `hwnat=1` | **0.087 ~ 0.15 Gbit/s**（几乎断流） | — |
| 修复后 `hwnat=1` | **2.32 ~ 2.34 Gbit/s**（2.5G 口线速） | **~5%** |
| 修复后 `hwnat=0`（对照） | 2.30 ~ 2.34 Gbit/s | ~33% |

修复前后 PPE 表项对比（`/sys/kernel/debug/ppe1/entries`）：

```
# 修复前：出口 tag 是 MediaTek 私有格式，YT9224 解不出目的口
BND ... eth=98:03:9b:a1:69:73->1c:86:0b:3d:7f:3a  etype=2000  vlan=0,0

# 修复后：出口 tag 是 YT9224 要的 802.1Q 形状，ctrl 落在 vlan1
BND ... eth=98:03:9b:a1:69:73->1c:86:0b:3d:7f:3a  etype=0008  vlan=1024
```

`vlan=1024` = `yt922x_4b_port_tag(5)` = `BIT(5) << 5` = lan2 的端口 ctrl；
`etype=0008` 是载荷 ethertype（IPv4 的 `0x0800` 字节序翻转）。详见 `docs/`。

---

## 快速使用

假设你的 x-wrt 树是 `/path/to/x-wrt`（已经 cherry-pick 了 flint4 补丁集）：

```sh
# 1. 先自检：这个树里有没有同类死代码
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt

# 2. 装上修复补丁
cp patches/999-0001-net-mediatek-ppe1-offload-yt922x-four-byte-port-tag.patch \
   /path/to/x-wrt/target/linux/mediatek/patches-6.18/

# 3. 编译
cd /path/to/x-wrt && make -j$(nproc)

# 4. 刷机后确认 natflow 是作者默认，不要套用任何「绕过」脚本
uci show natflow | grep -E 'ifname_group|hwnat'
#   期望：ifname_group_type='0'、无 ifname_group 列表、hwnat='1'
```

`tools/apply-to-xwrt.sh` 把 1~2 步合在一起，并做幂等检查。

---

## 适配清单（每个新文件都有独立说明）

**新增补丁**

| 文件 | 作用 | 说明文档 |
|---|---|---|
| `patches/999-0001-net-mediatek-ppe1-offload-yt922x-four-byte-port-tag.patch` | 让 PPE 出口按 YT9224 的 802.1Q 形状发端口 tag（唯一必须打的补丁） | [docs/02](docs/02-patch-999-ppe1-yt922x-port-tag.md) |

**新增工具**

| 文件 | 作用 | 说明文档 |
|---|---|---|
| `tools/check-xwrt-deadcode.py` | 找出「补丁改了不在 Makefile 编译清单里的文件」这类死代码（可直接当 CI gate） | [docs/05](docs/05-tool-check-deadcode.md) |
| `tools/apply-to-xwrt.sh` | 幂等地把补丁装进目标树，并顺手自检 | [docs/06](docs/06-tool-apply-to-xwrt.md) |
| `tools/example-output-xwrt-flint4.txt` | 检测器在真实 x-wrt+flint4 树上的完整输出（12 个死代码补丁） | [docs/05](docs/05-tool-check-deadcode.md) |

**说明文档（不含代码，但每页都对应一个具体结论）**

| 文件 | 内容 |
|---|---|
| `docs/01-natflow-deadcode-conflict.md` | 冲突成因、受影响的 flint4 补丁全清单、通用判定规则 |
| `docs/03-removed-dsa-bypass-workaround.md` | 被删除的「绕过方案」及其误导性，真修复 vs 绕过的判定方法 |
| `docs/04-known-gaps.md` | 尚未移植 / 尚未压测的部分，上游依赖风险 |
| `docs/07-verification.md` | 验证方法（吞吐 + CPU + PPE 三证据）与实测数据 |
| `docs/08-verification-files.md` | `verification/` 三份记录的定位（含一份**故意保留的作废结论**） |

**验证记录**

| 文件 | 状态 |
|---|---|
| `verification/HWNAT-FAIL-ROOTCAUSE.md` | ✅ 根因定案 |
| `verification/HWNAT-FIX-VERIFICATION.md` | ✅ 修复后真机验证 |
| `verification/SUPERSEDED-LAN2LAN-NO-OFFLOAD-ROOTCAUSE.md` | ❌ 已作废的错误结论（保留作为方法论反面案例） |

---

## 验证结论（摘要）

- 固件 revision `r0+36480-d1b67bef904`，内核 6.18.44
- LAN↔LAN：2.32~2.34 Gbit/s（正向）、1.94~1.95 Gbit/s（反向），稳定复现
- 同吞吐下 CPU 由软件的 ~33% 降到 ~5% → 硬件卸载确实接管
- 外网下载（WAN→LAN，出口 sfp）30~53.5 MB/s 稳定，峰值 428 Mbit/s，回流方向 PPE 出口 tag 正确
- `dmesg` 无 natflow / DSA / PPE 报错，无 `-EOPNOTSUPP` 回落记录

完整报告见 `verification/`。

---

## 上游来源与致谢

- flint4 设备与 YT9224 支持：**JiaY-shi**（`JiaY-shi/openwrt`，分支 `flint4-support*`）
- x-wrt 与 natflow：**Chen Minqiang (ptpt52)**（`x-wrt/x-wrt`、`ptpt52/natflow`）
- 本仓库只包含 **x-wrt 适配层**（让两者的冲突消解），不重复收录 flint4 的设备支持补丁。

作者也明确说明过：**x-wrt 关掉交换机 offload 是故意的**，目的是让 LAN↔LAN 上到 PPE 做
`Port → PPE → Port` 硬转。所以正确的做法不是去动 x-wrt 的 DSA 策略，而是**把 tag 对齐**。

---

## License

GPL-2.0-only（补丁作用于 Linux 内核源码）。
