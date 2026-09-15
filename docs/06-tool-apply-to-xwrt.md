# 06 · `tools/apply-to-xwrt.sh` 说明

把本仓库 `patches/` 下的补丁**幂等地**装进一棵 x-wrt 源码树，并顺手做死代码自检。

## 设计取向

- **只做「复制补丁文件」这一件事。** 不修改 x-wrt 的任何策略文件、
  不碰 natflow、不碰 DSA offload 策略、不改 `.config`。
  这样可以放心跑在别人正在用的树上。
- **幂等**：目标已存在且内容一致 → 跳过；已存在但内容不同 → **报冲突并退出**，
  绝不静默覆盖（内容不同通常意味着上游已经吸收或本地改过，需要人工判断）。
- **默认落点**是 `target/linux/mediatek/patches-6.18/`；用 `--patches-dir` 覆盖。

## 用法

```sh
./tools/apply-to-xwrt.sh /path/to/x-wrt                # 安装 + 自检
./tools/apply-to-xwrt.sh /path/to/x-wrt --dry-run      # 只看会做什么，不动文件
./tools/apply-to-xwrt.sh /path/to/x-wrt --list         # 只列出补丁
./tools/apply-to-xwrt.sh /path/to/x-wrt --patches-dir target/linux/mediatek/filogic/patches-6.18
```

## 它打印什么

1. 补丁来源 / 目标目录；
2. 每个补丁的动作：`+` 安装 / `=` 跳过 / `!` 冲突；
3. 自检结果：调用 `check-xwrt-deadcode.py`，把「还有哪些补丁是死代码」列出来；
4. 下一步该做什么（编译 → 确认 `.o` 被重建 → 刷机后确认 natflow 处于作者默认配置）。

## 之后手动要做的三件事

脚本不替你做这三步，因为它们需要判断力和现场信息：

```sh
# 1. 编译（新增补丁会触发内核 prepare 重跑）
cd <tree> && make -j$(nproc)

# 2. 确认补丁真的编进去了（不要只 grep 源码！）
ls -l build_dir/target-*/linux-*/linux-*/drivers/net/ethernet/mediatek/mtk_ppe_offload1.o
#    该 .o 必须被重建、且体积比打补丁前变大

# 3. 刷机后确认 natflow 是作者默认，不要套用任何「绕过」脚本
uci show natflow | grep -E 'ifname_group|hwnat'
#    期望：ifname_group_type='0'、无 ifname_group 列表、hwnat='1'
```

第 3 步特别容易踩坑：`sysupgrade` 会保留 `/etc/config`，
如果之前为了「临时能用」设过 `hwnat=0` 或 `ifname_group_type=2`，
它们会跟着带到新固件里，让验证直接失真。
