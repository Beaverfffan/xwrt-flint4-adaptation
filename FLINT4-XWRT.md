# x-wrt + flint4 —— GL.iNet GL-BE14000 可编译分支

> 本文件是**入口文档**（相对基线共 39 个提交）。分支布局、编译方法、以及**迁移到其它 x-wrt 分支/tag 的完整步骤**都在这里。
> 适配原理、补丁逐行说明、死代码检测器见同仓库 **`docs` 分支**（`docs/01`~`docs/08`）。

---

## 1. 这是什么

| 项 | 值 |
|---|---|
| 基线 | x-wrt tag **`26.04_b202609121905`**（commit `568999b325a`） |
| 本分支 | `main`（本仓库默认分支） |
| 目标设备 | **GL.iNet GL-BE14000**（mediatek / filogic，MT7988A） |
| 内核 | 6.18.44 |
| 相对基线 | **39 个提交** = 36 个上游提交（John Crispin 17 + JiaY-shi 19，**一个不漏**）+ 3 个本分支提交 |
| 状态 | 已真机验证（LAN↔LAN 2.34 Gbit/s @ CPU ~5%，外网下载峰值 428 Mbit/s） |

一句话：**让 GL-BE14000 在 x-wrt（自带 natflow 硬件加速栈）上真正跑通有线硬件转发。**

### 与「上游原样移植」的关系

本分支**不裁剪任何上游提交**。blogic 与 JiaY-shi 的 36 个提交（含 GL-BE10000 的面板、
触摸屏、u-boot、ATF splash 等）全部按原样搬过来，署名不变。
只有 3 个提交是本分支新增的（见第 4.B 节）。

这样做的好处：BE10000 那部分不需要单独验证一遍 —— 它和上游 `flint4-support-blogic-pr`
是**逐提交一致**的（`git log --format=%H` 对照即可）。本分支只是额外保证
「换到 x-wrt 这个基线上，补丁仍能干净应用、且 YT9224 的端口 tag 真的生效」。

---

## 2. 分支布局

| 分支 | 内容 | 用法 |
|---|---|---|
| `master`、`v26.04_*`、`origin/*` | 纯上游 x-wrt | **只读跟踪，不要在上面开发** |
| **`main`** | 基线 tag + 36 个上游提交 + 3 个本分支提交 | 本分支：**clone 下来就能编** |
| **`docs`** | 适配原理、补丁逐行说明、死代码检测器、验证数据 | 只读参考，不含源码 |

约定：`main` 永远保持「可编译 + 真机验证过」。上游更新时按第 5 节迁移，不要直接在 `main` 上 merge 上游。

---

## 3. 快速编译

### 3.1 依赖

- Ubuntu 22.04 / 24.04（x-wrt 官方构建环境）
- 磁盘 ≥ 60 GB（源码 + 构建产物；用 `-j` 全量约 2 h，增量十几分钟）
- 内存 ≥ 8 GB；只有 4 GB 时请配 zram（本分支作者用 32G zram + 8G NVMe swapfile + `make -j12` 成功）
- 必须的包：`git build-essential libncurses-dev zlib1g-dev gawk unzip file wget rsync`

> 树里自带 `tools/make`（上游提交 `40278cb1427`），宿主的 make 太旧时会自动用它。

### 3.2 三步走

```sh
git clone -b main https://github.com/Beaverfffan/xwrt-flint4-adaptation.git
cd xwrt-flint4-adaptation

# ① feeds（x-wrt 的 feeds 全部指向自身的 tag，见 feeds.conf.default）
cp feeds.conf.default feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a

# ② 本地额外包（passwall / adguardhome —— 不在 x-wrt feeds 里；用不到可跳过）
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

### A. 上游提交 36 个（John Crispin 17 + JiaY-shi 19，全部保留）

按主题分组（`git log --oneline 26.04_b202609121905..HEAD` 可看全量）：

| 主题 | 代表提交 |
|---|---|
| YT92xx DSA 驱动 backport | `d8c491ed5de`（41 个文件） |
| Motorcomm YT9224 交换机支持与端口 tag | `450e429b3b2`、`1e675c33b00`、`24dc059aa4e`、`7f5aec35d23` |
| YT9224 硬件桥接 / FDB / 组播 / 802.1Q 卸载 | `1908b5a6436`、`dbd1834457d`、`95d875b663f`、`19328189830`、`bc50afbf20f`、`1f08d6fd087` |
| Clause 22 PCS 协商 / 固定 10G 链路 | `e8091e8c911`、`75145df9642` |
| RTL8261C/D 10G PHY 与协商 | `1f4762b2c4f`、`57f207db901` |
| **GL-BE14000 设备支持**（DTS / u-boot / 生产版 DT / profile） | `3385771cadc`、`946f477ff1f`、`6675fb271d8`、`baa3c14d15c`、`9caa3c6c6b0` |
| **GL-BE10000 面板 / 触摸 / u-boot / ATF splash**（原样保留） | `aa3295f40f8`、`e1b7e553961`、`78653ff2fef`、`e522d2f622c`、`28adfbc1537`、`acfd13e0515`、`ba9afefbd98` |
| MT7987 内置 2.5G PHY | `21348609884`、`0251d5a52d3` |
| bridger / mt76 WED | `d198319ccc4`、`7dc923b7d83` |
| 构建基建（tools/make、ATF UBI 变体） | `40278cb1427`、`cbb4ca6e1b0`、`3cf0cbb9206` |

> 这些提交**保留原作者署名**，本分支只是把它们搬到 x-wrt 的 tag 上。
> 想核对是否与上游一致：`git log --format=%H 26.04_b202609121905..HEAD | head -36`。

### B. x-wrt 适配（本分支新增 3 个提交）

| 提交 | 作用 |
|---|---|
| **`x-wrt: 让 YT9224 的四字节端口 tag 在 natflow 树上真正生效`** | ① 新增 `target/linux/mediatek/patches-6.18/999-0001-…patch`（YT9224 端口 tag 的真正修复）；② 适配 `generic/pending-6.18/743-…RTL8261N…patch` 的 hunk 上下文（`57f207db901` 往同一头文件插了一行，旧上下文会对不上）；③ 删除 `mediatek/patches-6.18/975-…usxgmii-fix-link-flapping.patch`（被 `967-38` 取代，两者改同一段代码，留着会补丁失败） |
| `flint4: 加入本分支的编译说明与辅助脚本` | `FLINT4-XWRT.md`（本文件）+ `flint4/` 辅助脚本 + 根 `README.md` 顶部横幅。**该提交的 tree 与已真机验证的那棵树逐字节一致**（见下方「一致性证明」） |
| `flint4: 更新入口文档的仓库地址与提交计数` | 只改文档 |

> **一致性证明**：上面第 2 个提交的 tree hash 与真机验证时编/刷的那棵树完全相同
> （`fbc27d6a7c10ba9b959454d0c2e35ad878888722`）。也就是说，
> **这份 `main` 的构建相关内容 = 已验证过的固件源码，不需要重新编译即可确认结果。**
> 之后只有文档变更。

**为什么需要 999 补丁**（详见 `docs` 分支的 `docs/01`、`docs/02`）：

> x-wrt 的 natflow 补丁 `995-0001` 用 `mtk_ppe1.c` / `mtk_ppe_offload1.c`
> **顶掉了** `mtk_ppe.c` / `mtk_ppe_offload.c`。
> flint4 里负责给 YT9224 生成 802.1Q 形状端口 tag 的 `967-41` 恰好改的是后者 →
> **变成死代码** → PPE 出口发的是 MediaTek 私有 tag → 交换机解不出目的口 →
> 硬件转发几乎断流（实测 0.087~0.15 Gbit/s，**关掉 hwnat 反而有 2.34 Gbit/s**）。
>
> 999 补丁把同一段语义重放到**真正参与编译**的 `mtk_ppe_offload1.c`，让硬件发
> `81 00 | yt922x_4b_port_tag(port)`。**`967-41` 本身不用动**（它对非 natflow 的树仍然有效）。

---

## 5. 迁移到其它 x-wrt 分支 / tag（重点）

上游发新 tag（例如 `26.04_b2026xxxx`）或你想换到 `v26.04_xxx` 这类开发分支时，按下面做。

### 5.1 先确认这次迁移要搬什么

```sh
git fetch origin --tags
BASE=26.04_b202609121905          # 本分支的基线（见第 1 节）
NEW=26.04_b2026xxxxxx             # 新的目标 tag / 分支

git log --oneline $BASE..main     # 就是这 39 个提交要搬过去（36 个上游 + 3 个本分支）
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
grep -n "mtk_ppe.*\.o" build_dir/target-*/linux-*/linux-*/drivers/net/ethernet/mediatek/Makefile
#    期望看到 mtk_ppe1.o / mtk_ppe_offload1.o；若已改回 mtk_ppe.o，说明
#    新 natflow 不再顶文件，本补丁应改为直接作用于 mtk_ppe_offload.c（或直接退役）

# ③ 确认补丁仍然打得进去（打不上会立即报错，不会静默）
make target/linux/prepare V=s 2>&1 | grep -iE "999|975|743|fail|malformed"

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

判定细节见 `docs` 分支的 `docs/07-verification.md`。
**只吞吐恢复、CPU 仍高、没有对应 BND 表项 → 那是「绕过」不是修复。**

### 5.6 迁移到非 mediatek 目标 / 非 DSA 机型

本分支的 x-wrt 适配**只与「x-wrt natflow × flint4 YT9224」这个组合有关**。
如果你只是想要 flint4 的设备支持而不用 natflow，那么 `999-0001` 补丁**不需要**；
反过来，如果用了 natflow 但设备不是 YT9224（例如 MT7530 的 `mtk` tag），补丁也不会改变行为
（它只在 tag proto 为 `DSA_TAG_PROTO_YT922X_4B` 时生效）。

---

## 6. 已知问题与说明

### 6.1 死代码自检会报 12 条，其中 8 条不是本分支的问题

在树上实测：`generic/pending-6.18/736-03/04/05`、`795-01/02/03/07/09`
（x-wrt 自身的 PPE flow accounting、MxL862xx 卸载、DSA queue map 等补丁）
同样因为 natflow 顶掉 `mtk_ppe*.c` 而失效。**它们不影响 GL-BE14000 的有线硬转**
（natflow 自己用 5 元组 PPE 表项处理 L2），但如果你要用 `bridger` 做二层卸载就要留意。

### 6.2 `bridger` 的二层卸载路径未验证

`bridger` 是包含在 GL-BE14000 profile 里的（上游提交 `9caa3c6c6b0`）。它走的是
`mtk_ppe.c` 那套 L2 流匹配，而 flint4 的 `967-43` / `967-44`（正是给这条路做 YT9222X 适配的）
在 x-wrt 上也是死代码。**当前 natflow 路径不受影响**，
但启用 bridger 前建议先按 `docs/02` 的方法把这两个补丁也搬到 `mtk_ppe1.c`。

### 6.3 树里有 BE10000 的设备支持，但默认配置不编它

`flint4/be14000-flint4.config` 只选了 `CONFIG_TARGET_*_DEVICE_glinet_gl-be14000*`，
BE10000 相关的 `package/{fancontrol,glinet-panel-ui,luci-app-fancontrol,lvgl,ucode-mod-lvgl}`
与镜像里都不会出现（实测 0 命中）。**它们留着是为了与上游逐提交一致、避免二次验证**；
想彻底删掉的话，确认你的 `.config` 没引用即可。

### 6.4 BE14000 的固件选择

`glinet_gl-be14000`（stock）与 `glinet_gl-be14000-ubootmod` 共用同一个 DTS，
唯一区别是 bootloader（`mmcblk0boot0` 里的 bootchain 与 fip 分区）与 sysupgrade 的
metadata / CONTROL。**按设备当前装的是哪套 bootloader 选，不要拿 DTB 判断。**

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
| `flint4/check-xwrt-deadcode.py` | 死代码检测器（与 `docs` 分支同源） |
| `target/linux/mediatek/patches-6.18/999-0001-*.patch` | **本分支的关键适配补丁** |

## 9. 致谢

- flint4 设备与 YT9224 支持：**JiaY-shi**、**John Crispin (blogic)**
- x-wrt 与 natflow：**Chen Minqiang (ptpt52)**
- 本分支只做「把两者搬到一起、并让 tag 对齐」，不改动任何一方的策略。
