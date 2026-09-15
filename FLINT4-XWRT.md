# x-wrt + flint4 —— GL.iNet GL-BE14000 可编译分支

> 本文件是**入口文档**（相对基线共 42 个提交）。分支布局、编译方法、以及**迁移到其它 x-wrt 分支/tag 的完整步骤**都在这里。
> 通用的适配原理、补丁逐行说明、死代码检测器等另见独立仓库
> <https://github.com/Beaverfffan/xwrt-flint4-adaptation>。

---

## 1. 这是什么

| 项 | 值 |
|---|---|
| 基线 | x-wrt tag **`26.04_b202609121905`**（commit `568999b325a`） |
| 本分支 | `main` |
| 目标设备 | **GL.iNet GL-BE14000**（mediatek / filogic，MT7988A） |
| 内核 | 6.18.44 |
| 相对基线 | **42 个提交** = 36 个 flint4 支持（John Crispin 17 + JiaY-shi 19）+ 6 个本分支的适配/整理 |
| 状态 | 已真机验证（LAN↔LAN 2.34 Gbit/s @ CPU ~5%，外网下载峰值 428 Mbit/s） |

一句话：**让 GL-BE14000 在 x-wrt（自带 natflow 硬件加速栈）上真正跑通有线硬件转发。**

---

## 2. 分支布局

| 分支 | 内容 | 用法 |
|---|---|---|
| `master`、`v26.04_*`、`origin/*` | 纯上游 x-wrt | **只读跟踪，不要在上面开发** |
| **`main`** | 基线 tag + flint4 支持 + 2 个 x-wrt 适配提交 | 本分支：**clone 下来就能编** |

约定：`main` 永远保持「可编译 + 真机验证过」。上游更新时按第 5 节迁移，不要直接在 `main` 上 merge 上游。

---

## 3. 快速编译

### 3.1 依赖

- Ubuntu 22.04 / 24.04（x-wrt 官方构建环境）
- 磁盘 ≥ 60 GB（源码 + 构建产物；用 `-j` 全量约 2 h，增量十几分钟）
- 内存 ≥ 8 GB；只有 4 GB 时请配 zram（本分支作者用 32G zram + 8G NVMe swapfile + `make -j12` 成功）
- 必须的包：`git build-essential libncurses-dev zlib1g-dev gawk unzip file wget rsync`

### 3.2 三步走

```sh
git clone -b main https://github.com/Beaverfffan/x-wrt-flint4.git
cd x-wrt

# ① feeds（x-wrt 的 feeds 全部指向自身的 tag，见 feeds.conf.default）
cp feeds.conf.default feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a

# ② 本地额外包（passwall / adguardhome —— 不在 x-wrt feeds 里）
./flint4/fetch-local-packages.sh

# ③ 配置 + 编译
cp flint4/be14000-flint4.config .config
make defconfig
./flint4/build.sh                 # 等价于 make -j$(nproc)，日志写到 build.log
```

产物：

```
bin/targets/mediatek/filogic/x-wrt-26.04-*-mediatek-filogic-glinet_gl-be14000-squashfs-sysupgrade.bin
bin/targets/mediatek/filogic/x-wrt-26.04-*-mediatek-filogic-glinet_gl-be14000-squashfs-factory.bin
```

### 3.3 ⚠️ 编译前必做的一次自检

```sh
python3 flint4/check-xwrt-deadcode.py .
```

它会告出「补丁改了不参与编译的文件」这类**静默失效**问题。
本分支已知会有 12 条输出，其中 8 条是 x-wrt 自身的历史遗留（见第 6 节），
**不影响 GL-BE14000 的有线硬转**；与本分支相关的那条（`967-41`）已经由 `999-0001` 补丁修好。

---

## 4. 本分支相对基线 tag 增加了什么

### A. flint4 设备支持（36 个提交：John Crispin 17 + JiaY-shi 19）

按主题分组（`git log --oneline 26.04_b202609121905..HEAD` 可看全量）：

| 主题 | 代表提交 |
|---|---|
| Motorcomm YT9224 交换机 DSA 驱动与端口 tag | `d8c491ed5de`、`450e429b3b2`、`1e675c33b00`、`24dc059aa4e`、`7f5aec35d23` |
| YT9224 硬件桥接 / FDB / 组播 / 802.1Q 卸载 | `1908b5a6436`、`dbd1834457d`、`95d875b663f`、`19328189830`、`bc50afbf20f`、`1f08d6fd087` |
| RTL8261C/D 10G PHY 与协商 | `1f4762b2c4f`、`57f207db901` |
| GL-BE14000 设备支持（DTS / uboot / 生产版 DT） | `3385771cadc`、`946f477ff1f`、`6675fb271d8`、`baa3c14d15c`、`9caa3c6c6b0` |
| 构建基建（tools/make、arm-trusted-firmware 等） | `40278cb1427`、`cbb4ca6e1b0`、`3cc61b99d26`… |
| BE10000 面板触摸屏（**与 BE14000 无关**，见 6.3） | `aa3295f40f8`、`e1b7e553961`、`28adfbc1537`、`acfd13e0515`… |

> 这些提交**保留原作者署名**，本分支只是把它们搬到 x-wrt 的 tag 上。

### B. x-wrt 适配（本分支作者）

| 提交 | 作用 |
|---|---|
| `741175fe6ce` | 最初以为 LAN↔LAN 掉速是 natflow 配置问题，试过一套 `natflow-dsa-bypass` 绕过脚本（**同提交内后续又移除**） |
| **`d1b67bef904`** | **真正的修复**：把 flint4 `967-41` 的语义搬到参与编译的 `mtk_ppe_offload1.c`（新增 `target/linux/mediatek/patches-6.18/999-0001-…patch`），并删掉绕过脚本 |

**为什么需要它**（详见独立仓库 `docs/01`、`docs/02`）：

> x-wrt 的 natflow 补丁 `995-0001` 用 `mtk_ppe1.c` / `mtk_ppe_offload1.c`
> **顶掉了** `mtk_ppe.c` / `mtk_ppe_offload.c`。
> flint4 里负责给 YT9224 生成 802.1Q 形状端口 tag 的 `967-41` 恰好改的是后者 →
> **变成死代码** → PPE 出口发的是 MediaTek 私有 tag → 交换机解不出目的口 →
> 硬件转发几乎断流（实测 0.087~0.15 Gbit/s，**关掉 hwnat 反而有 2.34 Gbit/s**）。

---

## 5. 迁移到其它 x-wrt 分支 / tag（重点）

上游发新 tag（例如 `26.04_b2026xxxx`）或你想换到 `v26.04_xxx` 这类开发分支时，按下面做。

### 5.1 先确认这次迁移要搬什么

```sh
git fetch origin --tags
BASE=26.04_b202609121905          # 本分支的基线（见第 1 节）
NEW=26.04_b2026xxxxxx             # 新的目标 tag / 分支

git log --oneline $BASE..main     # 就是这 42 个提交要搬过去（36 个设备支持 + 6 个本分支提交）
```

### 5.2 方式 A：rebase（历史线性，推荐）

```sh
git checkout -b main-next $NEW
git rebase --onto $NEW $BASE main
```

**冲突高发区**（几乎只会在这两处）：
1. `target/linux/mediatek/patches-6.18/` —— **补丁编号撞车**。
   OpenWrt 按**文件名排序**应用补丁，上游新增的补丁可能占用我们现在用的编号。
   规则：`999-0001-…` 只需保证排在 natflow 的 `995-0001-…` **之后**即可；
   若 999 被占就把本补丁改成 998/9xx 中未被占用的最大编号（**必须 > 995**）。
2. `target/linux/mediatek/dts/`、`target/linux/mediatek/image/` —— 设备支持与上游改动重叠。

### 5.3 方式 B：逐提交 cherry-pick（冲突更可控，适合上游改动较大的情况）

```sh
git log --reverse --format=%H $BASE..main > /tmp/commits.txt
git checkout -b main-next $NEW
while read -r c; do
    git cherry-pick -x "$c" || { echo "冲突于 $c，解决后 git cherry-pick --continue"; break; }
done < /tmp/commits.txt
```

`-x` 会在提交信息里记下原提交号，方便将来对照。

### 5.4 迁移后必须重跑的四项检查

```sh
# ① 死代码自检 —— 最重要的一步，别跳过
python3 flint4/check-xwrt-deadcode.py .

# ② 确认 natflow 的 995 是否仍在使用影子副本（如果新版改了这里，999 补丁的写法要跟着改）
grep -n "mtk_ppe.*\.o" drivers/net/ethernet/mediatek/Makefile
#    期望看到 mtk_ppe1.o / mtk_ppe_offload1.o；若已改回 mtk_ppe.o，说明
#    新 natflow 不再顶文件，本补丁应改为直接作用于 mtk_ppe_offload.c（或直接退役）

# ③ 确认补丁仍然打得进去（打不上会立即报错，不会静默）
make target/linux/prepare V=s 2>&1 | grep -iE "999|fail|malformed"

# ④ 编译 + 确认 .o 真的被重建（不要只 grep 源码）
make -j$(nproc)
ls -l build_dir/target-*/linux-*/linux-*/drivers/net/ethernet/mediatek/mtk_ppe_offload1.o
```

### 5.5 刷机后的功能验证（三项证据缺一不可）

```sh
# 确认 natflow 处于作者默认，不要残留任何「绕过」配置
uci show natflow | grep -E 'ifname_group|hwnat'
#    期望：ifname_group_type='0'、无 ifname_group 列表、hwnat='1'
```

| 证据 | 期望 |
|---|---|
| 吞吐 | LAN↔LAN 跑到链路线速（2.5G 口 → 2.34 Gbit/s） |
| CPU | 同吞吐下 **~5%**（软件转发是 ~33%） |
| PPE 表项 | `grep BND /sys/kernel/debug/ppe1/entries`，出口是 YT9224 口时 `etype=载荷ethertype`、`vlan=<端口 ctrl>`（sfp=32、lan2=1024） |

判定细节见独立仓库 `docs/07-verification.md`。
**只吞吐恢复、CPU 仍高、没有对应 BND 表项 → 那是「绕过」不是修复。**

### 5.6 迁移到非 mediatek 目标 / 非 DSA 机型

本分支的适配**只与「x-wrt natflow × flint4 YT9224」这个组合有关**。
如果你只是想要 flint4 的设备支持而不用 natflow，那么 `999-0001` 补丁**不需要**；
反过来，如果用了 natflow 但设备不是 YT9224（例如 MT7530 的 `mtk` tag），补丁也不会改变行为
（它只在 tag proto 为 `DSA_TAG_PROTO_YT922X_4B` 时生效）。

---

## 6. 已知问题与说明

### 6.1 死代码自检会报 12 条，其中 8 条不是本分支的问题

在那棵树上实测：`generic/pending-6.18/736-03/04/05`、`795-01/02/03/07/09`
（x-wrt 自身的 PPE flow accounting、MxL862xx 卸载、DSA queue map 等补丁）
同样因为 natflow 顶掉 `mtk_ppe*.c` 而失效。**它们不影响 GL-BE14000 的有线硬转**
（natflow 自己用 5 元组 PPE 表项处理 L2），但如果你要用 `bridger` 做二层卸载就要留意。

### 6.2 `bridger` 的二层卸载路径未验证

`bridger` 是包含在 GL-BE14000 profile 里的。它走的是 `mtk_ppe.c` 那套 L2 流匹配，
而 flint4 的 `967-43` / `967-44`（正是给这条路做 YT9222X 适配的）在 x-wrt 上也是死代码。
**当前 natflow 路径不受影响**，但启用 bridger 前建议先按 `docs/02` 的方法把这两个补丁也搬到 `mtk_ppe1.c`。

### 6.3 树里有几个 BE10000 的面板/风扇包，BE14000 用不到

`package/{fancontrol,glinet-panel-ui,luci-app-fancontrol,lvgl,ucode-mod-lvgl}` 是 BE10000
（带屏/带风扇）的遗留物，`flint4/be14000-flint4.config` **没有选中它们**，
编出来的镜像里也不会有（实测 0 命中）。可以删，删之前确认你的 `.config` 没引用。

### 6.4 `fancontrol` / 显示类插件的取舍

BE14000 没有风扇与屏幕，本分支的配置里已把它们去掉。

---

## 7. 回滚

```sh
# 方式一：把修复补丁移出树，重编（回到「硬件转发不可用」的状态）
mv target/linux/mediatek/patches-6.18/999-0001-*.patch ../removed-patches/

# 方式二：真机上临时规避（会一并关掉 LAN↔LAN 硬转，仅应急）
uci set natflow.main.hwnat=0 && uci commit natflow && /etc/init.d/natflow-boot start
```

---

## 8. 目录说明

| 路径 | 内容 |
|---|---|
| `FLINT4-XWRT.md` | 本文件 |
| `flint4/be14000-flint4.config` | GL-BE14000 的 `.config` 种子（`cp` 到 `.config` 后 `make defconfig`） |
| `flint4/fetch-local-packages.sh` + `local-packages.txt` | 拉取 passwall / adguardhome 等不在 x-wrt feeds 里的本地包（含固定 commit） |
| `flint4/build.sh` | 带日志的构建脚本 |
| `flint4/check-xwrt-deadcode.py` | 死代码检测器（镜像自 `xwrt-flint4-adaptation` 仓库，改动请回上游改） |
| `target/linux/mediatek/patches-6.18/999-0001-*.patch` | **本分支的关键适配补丁** |

## 9. 致谢

- flint4 设备与 YT9224 支持：**JiaY-shi**、**John Crispin**
- x-wrt 与 natflow：**Chen Minqiang (ptpt52)**
- 本分支只做「把两者搬到一起、并让 tag 对齐」，不改动任何一方的策略。
