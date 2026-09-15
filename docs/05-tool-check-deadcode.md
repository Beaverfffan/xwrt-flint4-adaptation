# 05 · `tools/check-xwrt-deadcode.py` 说明

一个 **~250 行的纯标准库 Python 脚本**，用来在 OpenWrt / x-wrt 树上找出
「补丁改了不参与编译的文件」这一类死代码（成因见 `01-natflow-deadcode-conflict.md`）。

## 为什么需要它

- 补丁打得进去、编译不报错、`grep` 还能搜到代码 —— 单看源码树**判断不出来**；
- 内核补丁树里往往有几百个补丁，人工核对每个补丁的每个目标文件不现实；
- 一旦漏掉，症状会表现为「莫名其妙的硬件不工作」，排查成本极高（本次花了很久才定位）。

## 判定原理

1. 扫 `target/linux/**/patches-*/`、`hack-*/`、`pending-*/`、`backport-*/` 下的 `*.patch`，
   取每个补丁的 `+++ b/<path>`；
2. 对每个 `.c`，看它所在目录的 `Makefile` 里有没有同名 `.o` 作为编译目标出现：

   | Kbuild 写法 | 是否识别 |
   |---|---|
   | `obj-y += fork.o` | ✅ |
   | `obj-y     = fork.o exec_domain.o` | ✅ |
   | `foo-y := foo_main.o` | ✅ |
   | `regmap-core-objs = regmap.o` | ✅ |
   | `8021q-y := vlan.o vlan_dev.o`（变量名以数字开头） | ✅ |
   | `br_netfilter-$(subst m,y,$(CONFIG_IPV6)) += br_netfilter_ipv6.o`（变量名含空格/逗号） | ✅ |
   | 续行（`\`） | ✅ 先拼接 |
   | 配方行（以 TAB 开头的命令） | ⛔ 忽略，避免把 `$(RM) foo.o` 误当编译目标 |

3. 目标文件不在清单里 → 报告为死代码；若该文件正是 natflow 影子副本
   （`mtk_ppe.c` / `mtk_ppe_offload.c`）会给出针对性的提示。

**未能读到内核树时**（没有 `build_dir`）会退化为「用补丁里对 Makefile 的改动推断」，
此时结果偏保守，脚本会明确标注 `makefile_source: patches_heuristic`。

## 用法

```sh
# 默认：自动识别「当前已解包/正在构建的 target」+ 版本，结论最可靠
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt

# 树里没有 build_dir 时显式指定
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt --target mediatek --kernel 6.18

# 只关心某几个目录
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt --dir target/linux/mediatek/patches-6.18

# 机器可读（便于接 CI）
python3 tools/check-xwrt-deadcode.py /path/to/x-wrt --json
```

退出码：`0` 未发现 / `1` 发现死代码 / `2` 用法错误 —— 可直接用在 CI 里当 gate。

## 在 GL-BE14000 的 x-wrt 树上的真实结果

见 `tools/example-output-xwrt-flint4.txt`（637 个补丁，4 个补丁目录）：

```
[!] 发现 12 个补丁改了不参与编译的文件：

  generic/pending-6.18/736-03 … 736-05      -> mtk_ppe.c
  generic/pending-6.18/795-01/02/03/07/09   -> mtk_ppe.c / mtk_ppe_offload.c
  mediatek/patches-6.18/967-41              -> mtk_ppe_offload.c   ← 本仓库修复的那一个
  mediatek/patches-6.18/967-43 / 967-44     -> mtk_ppe.c
  mediatek/patches-6.18/967-50              -> mtk_ppe.c + mtk_ppe_offload.c（部分）
```

值得一提：**x-wrt 自己的** `generic/pending-6.18/736-0x`（PPE flow accounting）
和 `795-0x`（MxL862xx / DSA queue map）也在这棵树上失效了 ——
它们和 natflow 的 995 补丁同样冲突。这些不在本仓库的修复范围内，
但列出来是为了说明「这不是 flint4 独有的问题，而是这个组合的通病」。

## 已知局限

- **主机工具目录**（`scripts/`、`tools/`、`usr/`）不适用 `.o` 模型，
  改用「文件名主干是否出现在该目录的 `Makefile` / `Build` / `Makefile.include` / `Kbuild` 里」判定，
  比内核部分的判定弱一些；
- **跨 target 不可靠**：内核树是按 target 解包的，`--all` 会用同一棵内核树的 Makefile
  去判断别的 target 的补丁，结论仅供参考（脚本会打印警告）；
- 只判断「会不会生成 .o」，**不判断** Kconfig 是否选中、代码是否真的走到 —— 
  它解决的是「静默失效」这一类问题，不是全部。
