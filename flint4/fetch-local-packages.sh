#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
#
# fetch-local-packages.sh —— 把不在 x-wrt feeds 里的本地包克隆到 package/
#
# 清单见同目录 local-packages.txt（含固定 commit，保证可复现）。
# 幂等：目标目录已存在则只做 fetch + checkout，不重新 clone。
#
# 用法:
#   ./flint4/fetch-local-packages.sh            # 在源码树根目录执行
#   ./flint4/fetch-local-packages.sh --dry-run

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(cd "$HERE/.." && pwd)"
LIST="$HERE/local-packages.txt"
DRY_RUN=0

[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

[ -f "$LIST" ] || { echo "错误: 找不到 $LIST" >&2; exit 2; }
[ -d "$TREE/package" ] || { echo "错误: $TREE 不像 OpenWrt/x-wrt 源码树" >&2; exit 2; }

echo "源码树 : $TREE"
echo "清单   : $LIST"
echo

while read -r name url commit _rest; do
	case "$name" in ""|\#*) continue ;; esac
	dest="$TREE/package/$name"

	if [ -d "$dest/.git" ]; then
		echo "  = 已存在，更新到 $commit   package/$name"
		[ "$DRY_RUN" -eq 1 ] && continue
		git -C "$dest" fetch --quiet --all --tags
		git -C "$dest" checkout --quiet "$commit"
	else
		echo "  + 克隆 $url"
		echo "      -> package/$name @ $commit"
		[ "$DRY_RUN" -eq 1 ] && continue
		git clone --quiet "$url" "$dest"
		git -C "$dest" checkout --quiet "$commit"
	fi

	printf "      现在 HEAD = %s\n" "$(git -C "$dest" rev-parse HEAD)"
done < "$LIST"

echo
echo "完成。下一步："
cat <<'EOF'
  cp flint4/be14000-flint4.config .config
  make defconfig
  ./flint4/build.sh
EOF
