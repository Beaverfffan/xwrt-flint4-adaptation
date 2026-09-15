#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
#
# apply-to-xwrt.sh —— 把本仓库的补丁幂等地装进一棵 x-wrt 源码树，并做自检。
#
# 用法:
#   ./apply-to-xwrt.sh /path/to/x-wrt              # 安装并自检
#   ./apply-to-xwrt.sh /path/to/x-wrt --dry-run    # 只看会做什么
#   ./apply-to-xwrt.sh /path/to/x-wrt --list       # 只列补丁
#
# 设计取向：只做「复制补丁文件」这一件事，不修改 x-wrt 的策略文件、
# 不动 natflow、不动 DSA offload 策略。目标目录默认取 mediatek 的
# patches-6.18；可用 --patches-dir 覆盖。

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(cd "$HERE/../patches" && pwd)"

TREE=""
DRY_RUN=0
LIST_ONLY=0
PATCHES_REL="target/linux/mediatek/patches-6.18"

while [ $# -gt 0 ]; do
	case "$1" in
		--dry-run) DRY_RUN=1 ;;
		--list)    LIST_ONLY=1 ;;
		--patches-dir) PATCHES_REL="$2"; shift ;;
		-h|--help) sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		-*) echo "未知参数: $1" >&2; exit 2 ;;
		*)  TREE="$1" ;;
	esac
	shift
done

if [ -z "$TREE" ]; then
	echo "用法: $0 /path/to/x-wrt [--dry-run|--list] [--patches-dir <相对路径>]" >&2
	exit 2
fi

TREE="$(cd "$TREE" && pwd)"
DEST="$TREE/$PATCHES_REL"

[ -d "$TREE/target/linux" ] || { echo "错误: $TREE 不是 OpenWrt/x-wrt 源码树" >&2; exit 2; }
[ -d "$SRC_DIR" ]          || { echo "错误: 找不到补丁目录 $SRC_DIR" >&2; exit 2; }

echo "补丁来源 : $SRC_DIR"
echo "目标目录 : $DEST"
echo

if [ "$LIST_ONLY" -eq 1 ]; then
	ls -1 "$SRC_DIR"/*.patch
	exit 0
fi

[ -d "$DEST" ] || { echo "错误: 目标补丁目录不存在: $DEST（可用 --patches-dir 指定）" >&2; exit 2; }

installed=0
skipped=0
conflict=0

for p in "$SRC_DIR"/*.patch; do
	[ -e "$p" ] || continue
	name="$(basename "$p")"
	target="$DEST/$name"

	if [ -e "$target" ]; then
		if cmp -s "$p" "$target"; then
			echo "  = 已存在且一致，跳过  $name"
			skipped=$((skipped+1))
		else
			echo "  ! 已存在但内容不同: $name"
			echo "      请人工确认（不要盲目覆盖）"
			conflict=$((conflict+1))
		fi
		continue
	fi

	if [ "$DRY_RUN" -eq 1 ]; then
		echo "  + 将安装  $name"
	else
		cp -v "$p" "$target"
	fi
	installed=$((installed+1))
done

echo
echo "安装 $installed / 跳过 $skipped / 冲突 $conflict"
echo

if [ "$conflict" -gt 0 ]; then
	echo "存在内容冲突，请先人工处理再继续。" >&2
	exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
	echo "(dry-run，未改动任何文件)"
	exit 0
fi

# ---------------------------------------------------------------- 自检
if command -v python3 >/dev/null 2>&1; then
	echo "=== 自检：本树里还有没有同类死代码 ==="
	set +e
	python3 "$HERE/check-xwrt-deadcode.py" "$TREE"
	rc=$?
	set -e
	case "$rc" in
		0) echo "OK：未发现死代码。" ;;
		1) cat <<'EOF'

注意：上面列出的补丁改了**不参与编译**的文件（详见 docs/01）。
     如果你需要它们的功能，必须把逻辑搬到对应的 *1.c（natflow 影子副本）。
     仅使用 flint4 的 YT9224 四字节端口 tag 功能时，本仓库的 999 补丁已覆盖。
EOF
		;;
		*) echo "(自检脚本返回 $rc，可能环境不完整)" ;;
	esac
fi

cat <<'EOF'

下一步:
  1) 编译（补丁是新文件，会触发内核 prepare 重跑）
       cd <tree> && make -j$(nproc)
  2) 确认补丁**真的**编进去了（不要只 grep 源码，见 docs/02 第 7 节）
       ls -l build_dir/target-*/linux-*/linux-*/drivers/net/ethernet/mediatek/mtk_ppe_offload1.o
  3) 刷机后确认 natflow 是作者默认，不要套用任何「绕过」脚本
       uci show natflow | grep -E 'ifname_group|hwnat'
       # 期望 ifname_group_type='0'、无 ifname_group 列表、hwnat='1'
  4) 验证：docs/07-verification.md
EOF
