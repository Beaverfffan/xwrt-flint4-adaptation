# flint4/ —— GL-BE14000 在 x-wrt 上的构建辅助

这里是让本分支「clone 下来就能编」所需的辅助文件。**入口文档在仓库根目录的
[`FLINT4-XWRT.md`](../FLINT4-XWRT.md)**，包含分支布局、编译步骤、
以及**迁移到其它 x-wrt 分支/tag 的完整流程**。

| 文件 | 作用 |
|---|---|
| `be14000-flint4.config` | GL-BE14000 的 `.config` 种子：`cp` 到 `.config` 后 `make defconfig` |
| `fetch-local-packages.sh` + `local-packages.txt` | 拉取不在 x-wrt feeds 里的本地包（passwall / adguardhome，含固定 commit） |
| `build.sh` | 带日志的构建脚本 |
| `check-xwrt-deadcode.py` | 死代码检测器：找出「补丁改了不参与编译的文件」这类静默失效 |

关键适配补丁在 `../target/linux/mediatek/patches-6.18/999-0001-*.patch`，
逐行说明与原理见 <https://github.com/Beaverfffan/xwrt-flint4-adaptation>。
