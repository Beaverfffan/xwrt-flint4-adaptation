# 01 · 冲突成因：natflow 顶掉了两个 PPE 源文件

> 这是本仓库所有内容的根源。理解这一页，其余都是它的推论。

## 1. 事实

x-wrt 的 natflow 支持补丁：

```
target/linux/mediatek/patches-6.18/995-0001-hwnat-add-natflow-flow-offload-support.patch
（作者 Chen Minqiang <ptpt52@gmail.com>）
```

它做了两件关键的事：

1. **新增两份 PPE 源文件**：`mtk_ppe1.c`、`mtk_ppe_offload1.c`
   （MediaTek 原文件的冻结副本 + natflow 需要的改动）；
2. **改写驱动的 Makefile**，把编译对象换成这两份拷贝：

```diff
-mtk_eth-y := mtk_eth_soc.o mtk_eth_path.o mtk_ppe.o mtk_ppe_debugfs.o mtk_ppe_offload.o
+mtk_eth-y := mtk_eth_soc.o mtk_eth_path.o mtk_ppe1.o mtk_ppe_debugfs.o mtk_ppe_offload1.o
```

结果：**`mtk_ppe.c` 与 `mtk_ppe_offload.c` 不再参与编译**。
它们在源码树里还在、能 grep 到、内容也会被你打的补丁改掉 —— 但那个 `.o` 根本不会被生成。

实测确认（GL-BE14000 构建树）：

```
drivers/net/ethernet/mediatek/mtk_ppe1.o            <- 存在，被链接
drivers/net/ethernet/mediatek/mtk_ppe_offload1.o    <- 存在，被链接
drivers/net/ethernet/mediatek/mtk_ppe.o             <- 不存在
drivers/net/ethernet/mediatek/mtk_ppe_offload.o     <- 不存在
```

## 2. 受影响的 flint4 补丁

以下补丁改了**不参与编译**的文件，在 x-wrt 上等于没打：

| flint4 补丁 | 改的文件 | 在 x-wrt 上 | 影响 |
|---|---|---|---|
| `967-41-net-mediatek-ppe-support-yt922x-four-byte-port-tag.patch` | `mtk_ppe_offload.c` | ❌ 死代码 | **严重**：PPE 出口无法生成 YT9224 端口 tag → 硬件转发废掉（本仓库修复的就是它） |
| `967-43-net-mediatek-ppe-match-yt922x-bridge-flows.patch` | `mtk_ppe.c` | ❌ 死代码 | 中：PPE 接收侧无法匹配 YT9222X 的桥接二层流（走 `bridger`/tc-flower 的 L2 offload 会失效） |
| `967-44-net-mediatek-ppe-retire-expired-bridge-subflow.patch` | `mtk_ppe.c` | ❌ 死代码 | 中：同上，桥接子流回收 |
| `967-50-net-dsa-yt922x-add-8021q-vlan-offload.patch` | 多文件（见下） | ⚠️ **部分** | 只有 `mtk_ppe.c` / `mtk_ppe_offload.c` 那部分失效；`yt921x.c`、`yt921x.h`、`tag_yt922x.c`、`include/net/dsa.h`、`net/dsa/user.c` 的部分**仍然生效** |

`967-50` 的分布（示例）：
```
drivers/net/dsa/yt921x.c                       <- 生效
drivers/net/dsa/yt921x.h                       <- 生效
net/dsa/tag_yt922x.c                           <- 生效
include/net/dsa.h                              <- 生效
net/dsa/user.c                                 <- 生效
drivers/net/ethernet/mediatek/mtk_ppe.c        <- 死代码
drivers/net/ethernet/mediatek/mtk_ppe_offload.c<- 死代码
```

### 2.1 用 `check-xwrt-deadcode.py` 跑出来的完整清单（真实结果）

在 x-wrt + flint4 的 GL-BE14000 树上（637 个补丁 / 4 个补丁目录，内核 6.18.44），
**共有 12 个补丁**命中这一类问题：

```
generic/pending-6.18/736-03-…improve-keeping-track-of-of      -> mtk_ppe.c
generic/pending-6.18/736-04-…fix-ppe-flow-accounting-for-L2   -> mtk_ppe.c + mtk_ppe_offload.c
generic/pending-6.18/736-05-…zero-initialize-PPE-flow-ta      -> mtk_ppe.c
generic/pending-6.18/795-01-…use-rhashtable_lookup_f          -> mtk_ppe_offload.c
generic/pending-6.18/795-02-…set-tport_idx-on-netsys_v3-for   -> mtk_ppe.c
generic/pending-6.18/795-03-…set-output-device-befor          -> mtk_ppe_offload.c
generic/pending-6.18/795-07-…use-DSA-queue-map-in-fl          -> mtk_ppe_offload.c
generic/pending-6.18/795-09-…offload-flows-to-MxL862xx-switc  -> mtk_ppe_offload.c
mediatek/patches-6.18/967-41-…ppe-support-yt922x-four-byte…   -> mtk_ppe_offload.c   ← 本仓库修复的
mediatek/patches-6.18/967-43-…ppe-match-yt922x-bridge-flows   -> mtk_ppe.c
mediatek/patches-6.18/967-44-…ppe-retire-expired-bridge-…     -> mtk_ppe.c
mediatek/patches-6.18/967-50-…yt922x-add-8021q-vlan-offload   -> mtk_ppe.c (+ mtk_ppe_offload.c)
```

⚠️ 注意 **`generic/pending-6.18/736-0x` 与 `795-0x` 是 x-wrt 自己的补丁**
（PPE flow accounting、MxL862xx 卸载、DSA queue map 等）—— 它们和 natflow 的 995
同样冲突，也在同一棵树上失效。也就是说：**这不是 flint4 独有的问题，而是
「上游 PPE 补丁 + x-wrt natflow」这个组合的通病。**

本仓库只修复 YT9224 四字节端口 tag 这一条（因为它直接决定 GL-BE14000 的有线硬转能不能用）；
其余属于 x-wrt 自身的历史遗留，列出来供上游参考。

完整原始输出见 `tools/example-output-xwrt-flint4.txt`。

## 3. 通用判定规则

> **某补丁改了 `X.c` ≠ `X.c` 会被编译。**

判定步骤：

1. 从补丁里取出所有 `+++ b/<path>`；
2. 去看该目录 `Makefile` 的 `obj-y` / `xxx-y` 行；
3. 目标文件不在里面 → 这个补丁是死代码（或部分死代码）。

`tools/check-xwrt-deadcode.py` 把这三步自动化了：

```sh
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt
```

它会逐个扫 `target/linux/*/patches-*/*.patch`，解析 Makefile 的编译列表，
输出「改了不参与编译的文件」的补丁清单，并对 `mtk_ppe1.c` / `mtk_ppe_offload1.c` 这类
**natflow 影子文件**给出明确提示。

## 4. 为什么这个坑特别贵

- **完全静默**：补丁打得上、编译不报错、没有 warning，`grep` 还能搜到代码。
- **症状误导**：数据面表现为「PPE 表项已 BND、端口位也对，就是没速度」，
  很自然会被怀疑成 DSA 硬件桥接、交换机隔离矩阵、驱动 bug。
- **上游还在动**：natflow 的 `*1.c` 是冻结副本，上游对 `mtk_ppe.c` 的修复
  **也不会进 `*1.c`**。所以这类树上的 PPE 问题都要先问一句
  「这个改动进的是哪一份文件？」

## 5. 正确的适配姿势

有两种，本仓库采用 **A**：

**A. 把 flint4 的相关逻辑搬到 `*1.c`（推荐，本仓库做法）**
- 优点：不碰 natflow，升级 natflow 时改动面最小；`*1.c` 与 flint4 补丁语义一一对应，好对照。
- 缺点：每次 natflow 更新 `*1.c` 基线，需要重放一次（本仓库把补丁写成标准 unified diff，
  `patch -p1` / `git apply` 都能重放，重放过不了会立刻报错而不是静默失效）。

**B. 反过来，让 natflow 的改动基于 `mtk_ppe.c`（不推荐）**
- 需要和 natflow 上游持续对抗，且会让 natflow 的 `*1.c` 与驱动主线渐行渐远。

补充：**不要**通过「关掉硬件加速」或「把 LAN 排除出快转」来回避问题 ——
那等于把作者想要的 LAN↔LAN 硬转也关掉，见 `03-removed-dsa-bypass-workaround.md`。
