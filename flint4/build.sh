#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
#
# build.sh —— 带日志的构建脚本（在源码树根目录执行）
#
#   ./flint4/build.sh              # make -j$(nproc)
#   ./flint4/build.sh -j8          # 自定义并发
#   LOG=/path/to.log ./flint4/build.sh
#
# 日志默认写到 <tree>/build.log，可用 LOG= 覆盖。
# 用在无头/远程机器上时建议配合 tmux，避免 SSH 断开导致编译中断：
#   tmux new-session -d -s build './flint4/build.sh'

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(cd "$HERE/.." && pwd)"
LOG="${LOG:-$TREE/build.log}"
JOBS=""

while [ $# -gt 0 ]; do
	case "$1" in
		-j*) JOBS="$1" ;;
		-h|--help) sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "未知参数: $1" >&2; exit 2 ;;
	esac
	shift
done

[ -d "$TREE/target/linux" ] || { echo "错误: $TREE 不像源码树" >&2; exit 2; }
[ -f "$TREE/.config" ] || {
	echo "错误: 还没有 .config。先执行：" >&2
	echo "  cp flint4/be14000-flint4.config .config && make defconfig" >&2
	exit 2
}

cd "$TREE" || exit 1

{
	echo "########## BUILD START $(date -Is) ##########"
	echo "--- tree   : $(git branch --show-current 2>/dev/null) @ $(git rev-parse --short HEAD 2>/dev/null)"
	echo "--- config : $(grep -c . .config) lines, $(grep -E '^CONFIG_TARGET_PROFILE=' .config)"
	echo "--- jobs   : ${JOBS:-auto(-j\$(nproc))}"
	echo

	if [ -n "$JOBS" ]; then
		make "$JOBS"
		rc=$?
	else
		make -j"$(nproc)"
		rc=$?
	fi

	echo
	echo "########## BUILD rc=$rc  $(date -Is) ##########"
	echo "--- 产物 ---"
	ls -la bin/targets/mediatek/filogic/*be14000*.bin 2>/dev/null || echo "(无产物)"
	echo "########## DONE $(date -Is) ##########"
} >>"$LOG" 2>&1

# 把结果回显到终端（日志完整版在 $LOG）
echo "日志: $LOG"
tail -n 20 "$LOG"
grep -qE 'BUILD rc=0' "$LOG" && echo && echo "构建成功。产物：" && \
	ls -la "$TREE"/bin/targets/mediatek/filogic/*be14000*.bin 2>/dev/null
