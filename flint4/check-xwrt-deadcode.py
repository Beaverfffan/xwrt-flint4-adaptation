#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""
check-xwrt-deadcode.py —— 找出「补丁改了不参与编译的文件」这一类死代码。

背景见 docs/01-natflow-deadcode-conflict.md：

  x-wrt 的 natflow 补丁 (995-0001-hwnat-add-natflow-flow-offload-support.patch)
  会新增 mtk_ppe1.c / mtk_ppe_offload1.c，并把驱动的 Makefile 从
      mtk_eth-y := ... mtk_ppe.o    ... mtk_ppe_offload.o
  改成
      mtk_eth-y := ... mtk_ppe1.o   ... mtk_ppe_offload1.o
  于是任何修改 mtk_ppe.c / mtk_ppe_offload.c 的补丁都变成死代码 ——
  补丁打得进去、编译不报错、grep 还能搜到，但那个 .o 根本不会生成。

判定只需三步：
  1. 从补丁里取出它改的文件；
  2. 看这些文件所在目录的 Makefile —— 同名 .o 是否出现在编译清单里；
  3. 不在 → 死代码。

用法:
    # 默认: 只扫「当前已解包/正在构建的那个 target」+ generic，结论最可靠
    python3 check-xwrt-deadcode.py /path/to/x-wrt

    # 指定 target（树里没有 build_dir 时）
    python3 check-xwrt-deadcode.py /path/to/x-wrt --target mediatek --kernel 6.18

    # 额外加目录
    python3 check-xwrt-deadcode.py /path/to/x-wrt --dir target/linux/mediatek/filogic/patches-6.18

    # 全树扫（跨 target 结果仅供参考：内核树是按 target 解包的）
    python3 check-xwrt-deadcode.py /path/to/x-wrt --all

    # 机器可读
    python3 check-xwrt-deadcode.py /path/to/x-wrt --json

退出码: 0 = 未发现死代码; 1 = 发现死代码; 2 = 用法/环境错误
"""

import argparse
import json
import os
import re
import sys

NATFLOW_SHADOW = {
    "mtk_ppe.c": "mtk_ppe1.c",
    "mtk_ppe_offload.c": "mtk_ppe_offload1.c",
}
NATFLOW_HINT = (
    "本文件不会生成 .o：该目录编译的是 {shadow_obj}（natflow 的影子副本）"
    " -> 死代码，需要把逻辑搬到 {shadow_src}"
)
PLAIN_HINT = "本文件不会生成 .o（不在该目录 Makefile 的编译清单里）-> 死代码"

RE_NEW_FILE = re.compile(r"^\+\+\+ b/(.+?)(?:\t.*)?$")

# 这些目录是内核的「主机工具」，用各自的构建规则（hostprogs / xxx-in.o / tools/*/Build），
# 不遵循 <var>-y 的 .o 模型，因此改用「文件名主干是否出现在构建描述里」判定。
HOST_PATH_PREFIXES = ("scripts/", "tools/", "usr/")
HOST_BUILD_FILES = ("Makefile", "Build", "Makefile.include", "Kbuild")

PATCH_DIR_RE = re.compile(r"^(patches|hack|pending|backport)-(.+)$")


# ------------------------------------------------------------------ 扫描范围


def kernel_series_match(dir_series, want):
    """补丁目录的版号（如 6.18）与期望版号（如 6.18 / 6.18.44）是否匹配。"""
    return dir_series == want or dir_series.startswith(want + ".") or want.startswith(dir_series + ".")


def patch_dirs_for(root, targets, kernels, extra):
    """产出要扫描的补丁目录（已存在的）。"""
    out = []
    tl = os.path.join(root, "target", "linux")
    if os.path.isdir(tl):
        entries = sorted(os.listdir(tl))
        for name in entries:
            tdir = os.path.join(tl, name)
            if not os.path.isdir(tdir):
                continue
            if name != "generic" and targets and name not in targets:
                continue
            for sub in sorted(os.listdir(tdir)):
                sp = os.path.join(tdir, sub)
                if not os.path.isdir(sp):
                    continue
                # 形式一: target/linux/<t>/patches-<ver>   -> sub 就是补丁目录
                m = PATCH_DIR_RE.match(sub)
                if m:
                    if kernels and not any(kernel_series_match(m.group(2), k) for k in kernels):
                        continue
                    out.append(sp)
                    continue
                # 形式二: target/linux/<t>/<subtarget>/patches-<ver>
                for sub2 in sorted(os.listdir(sp)):
                    m2 = PATCH_DIR_RE.match(sub2)
                    if not m2:
                        continue
                    if kernels and not any(kernel_series_match(m2.group(2), k) for k in kernels):
                        continue
                    out.append(os.path.join(sp, sub2))
    for d in extra or []:
        d = d if os.path.isabs(d) else os.path.join(root, d)
        if os.path.isdir(d):
            out.append(d)
    return sorted(set(out))


def iter_patches(dirs):
    for d in dirs:
        for fn in sorted(os.listdir(d)):
            if fn.endswith((".patch", ".diff")):
                yield os.path.join(d, fn)


def touched_files(patch_path):
    out = []
    try:
        with open(patch_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = RE_NEW_FILE.match(line.rstrip("\n"))
                if not m:
                    continue
                p = m.group(1).strip()
                if p and p != "/dev/null":
                    out.append(p)
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ 编译清单


def makefile_objects(text):
    """
    取出 Makefile 里作为编译目标出现的所有 .o。

    做法故意宽松：Kbuild 里 .o 可能出现在
        obj-$(CONFIG_X) += foo.o
        obj-y     = fork.o exec_domain.o ...        （纯 =）
        foo-y     := foo_main.o                     （:=）
        regmap-core-objs = regmap.o ...             （-objs）
        br_netfilter-$(subst m,y,$(CONFIG_IPV6)) += br_netfilter_ipv6.o   （变量名里带空格/逗号）
    等多种写法里，本用途只需要判断「这个名字有没有作为编译目标出现」。

    规则：跳过配方行（以 TAB 开头，那是命令不是声明），其余含 "=" 的行里的 .o 都算数。
    """
    objs = set()
    joined = re.sub(r"\\\n\s*", " ", text)      # 先把续行拼起来
    for line in joined.splitlines():
        if line.startswith("\t"):               # 配方行（命令）不参与
            continue
        line = line.split("#", 1)[0]
        if "=" not in line:
            continue
        for tok in line.split():
            tok = tok.rstrip("\\")
            if tok.endswith(".o"):
                objs.add(tok)
    return objs


class KernelView:
    """内核相对路径 -> 是否会被编译。"""

    def __init__(self, root, kernel_dir):
        self.root = root
        self.kernel_dir = kernel_dir
        self.obj_cache = {}
        self.mf_cache = {}
        self.heuristic = kernel_dir is None
        self.synth = None if kernel_dir else self._synthesize()

    def _synthesize(self):
        """没解包内核时：把补丁里对 Makefile 的改动拼成近似内容（含新增行）。"""
        synth = {}
        for d in patch_dirs_for(self.root, None, None, None):
            for patch in iter_patches([d]):
                for rel in touched_files(patch):
                    if os.path.basename(rel) != "Makefile":
                        continue
                    try:
                        with open(patch, encoding="utf-8", errors="replace") as fh:
                            for line in fh:
                                if line.startswith("+") and not line.startswith("+++"):
                                    synth.setdefault(rel, []).append(line[1:].rstrip("\n"))
                    except OSError:
                        pass
        return {k: "\n".join(v) for k, v in synth.items()}

    def _makefile(self, rel_dir):
        rel = os.path.join(rel_dir, "Makefile") if rel_dir else "Makefile"
        if rel in self.mf_cache:
            return self.mf_cache[rel]
        text = None
        if self.kernel_dir:
            p = os.path.join(self.kernel_dir, rel)
            if os.path.isfile(p):
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
        if text is None and self.synth:
            text = self.synth.get(rel)
        self.mf_cache[rel] = text
        return text

    def compiled(self, rel_path):
        """True/False/None（None = 信息不足，例如没有该目录的 Makefile）"""
        if not rel_path.endswith(".c"):
            return None
        if rel_path in self.obj_cache:
            return self.obj_cache[rel_path]
        if self.kernel_dir:
            # 文件在内核树里不存在 -> 补丁没有真正生效（版本不匹配等），
            # 属于另一类问题，不由本工具判定。
            if not os.path.exists(os.path.join(self.kernel_dir, rel_path)):
                self.obj_cache[rel_path] = None
                return None
        text = self._makefile(os.path.dirname(rel_path))
        if text is None:
            self.obj_cache[rel_path] = None
            return None

        if rel_path.startswith(HOST_PATH_PREFIXES):
            # 主机工具：不适用 <var>-y 模型（部分还由 tools/*/Build 描述），
            # 退化为「文件名主干是否出现在该目录的构建描述里」。
            rel_dir = os.path.dirname(rel_path)
            blob = ""
            if self.kernel_dir:
                for name in HOST_BUILD_FILES:
                    p = os.path.join(self.kernel_dir, rel_dir, name)
                    if os.path.isfile(p):
                        with open(p, encoding="utf-8", errors="replace") as fh:
                            blob += fh.read()
            if not blob:
                blob = text
            stem = os.path.basename(rel_path)[:-2]
            res = stem in blob
        else:
            obj = os.path.basename(rel_path)[:-2] + ".o"
            res = obj in makefile_objects(text)

        self.obj_cache[rel_path] = res
        return res


# ------------------------------------------------------------------ 入口


RE_KERNEL_DIR = re.compile(r"^linux-(\d+)\.(\d+)(?:\.\d+)?$")


def find_kernel_dir(root):
    """定位已解包的内核源码目录。

    OpenWrt 在 build_dir/target-<arch>/linux-<target>_<subtarget>/ 下会有多个目录
    （linux-6.18.44、ovpn-backports-7.1.0.xxx 等），只有名字形如 linux-<x>.<y>[.<z>]
    的才是内核树。
    """
    bd = os.path.join(root, "build_dir")
    if not os.path.isdir(bd):
        return None, None, None
    best = (None, None, None)
    for target in sorted(os.listdir(bd)):
        if not target.startswith("target-"):
            continue
        sub = os.path.join(bd, target)
        if not os.path.isdir(sub):
            continue
        for lroot in sorted(os.listdir(sub)):
            if not lroot.startswith("linux-"):
                continue
            lr = os.path.join(sub, lroot)
            if not os.path.isdir(lr):
                continue
            tgt = lroot.split("-", 1)[1].split("_")[0]     # mediatek_filogic -> mediatek
            for ver in sorted(os.listdir(lr)):
                m = RE_KERNEL_DIR.match(ver)
                if not m:
                    continue
                kp = os.path.join(lr, ver)
                if not (os.path.isfile(os.path.join(kp, "Makefile"))
                        and os.path.isdir(os.path.join(kp, "drivers"))):
                    continue
                series = f"{m.group(1)}.{m.group(2)}"
                best = (kp, tgt, series)
    return best


def main():
    ap = argparse.ArgumentParser(
        description="找出 x-wrt/OpenWrt 树上「改了不参与编译的文件」的补丁（死代码）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法:")[0].strip(),
    )
    ap.add_argument("tree", help="x-wrt / OpenWrt 源码树根目录")
    ap.add_argument("--target", action="append", help="只扫这些 target（可多次）")
    ap.add_argument("--kernel", action="append", help="只扫这些内核版本文号（如 6.18）")
    ap.add_argument("--dir", action="append", help="额外扫描的补丁目录")
    ap.add_argument("--all", action="store_true", help="扫全树（跨 target 仅供参考）")
    ap.add_argument("--quiet", action="store_true", help="只输出有问题的补丁")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    root = os.path.abspath(args.tree)
    if not os.path.isdir(os.path.join(root, "target", "linux")):
        print(f"错误: {root} 看起来不是 OpenWrt/x-wrt 源码树（找不到 target/linux）",
              file=sys.stderr)
        return 2

    kdir, ktarget, kver = find_kernel_dir(root)

    targets = None if args.all else (args.target or ([ktarget] if ktarget else None))
    kernels = None if args.all else (args.kernel or ([kver] if kver else None))
    if args.all:
        kdir = kdir  # 仍用当前已解包的树做判定，但要提示不可靠

    dirs = patch_dirs_for(root, targets, kernels, args.dir)
    if not dirs:
        print("错误: 没有匹配到任何补丁目录。请显式指定 --target/--kernel 或 --dir。",
              file=sys.stderr)
        return 2

    view = KernelView(root, kdir)
    patches = list(iter_patches(dirs))

    findings = []
    insufficient = 0
    for patch in patches:
        bad = []
        for rel in touched_files(patch):
            c = view.compiled(rel)
            if c is None:
                if rel.endswith(".c"):
                    insufficient += 1
                continue
            if not c:
                obj = os.path.basename(rel)[:-2] + ".o"
                src = os.path.basename(rel)
                shadow = NATFLOW_SHADOW.get(src)
                hint = (NATFLOW_HINT.format(shadow_obj=shadow[:-2] + ".o", shadow_src=shadow)
                        if shadow else PLAIN_HINT)
                bad.append({"file": rel, "object": obj, "hint": hint})
        if bad:
            findings.append({"patch": os.path.relpath(patch, root), "dead_files": bad})

    if args.json:
        print(json.dumps({
            "tree": root,
            "kernel_dir": kdir,
            "target": ktarget,
            "kernel": kver,
            "makefile_source": "kernel_tree" if kdir else "patches_heuristic",
            "patch_dirs": [os.path.relpath(d, root) for d in dirs],
            "patches_scanned": len(patches),
            "insufficient_info": insufficient,
            "findings": findings,
        }, indent=2, ensure_ascii=False))
        return 1 if findings else 0

    if not args.quiet:
        print(f"源码树    : {root}")
        print(f"判定依据  : " + (f"{kdir}" if kdir
                              else "未找到已解包内核 -> 用补丁里的 Makefile 改动推断（偏保守）"))
        print(f"扫描范围  : target={targets or '全部'} kernel={kernels or '全部'}"
              f"  {len(dirs)} 个补丁目录 / {len(patches)} 个补丁")
        if args.all:
            print("            ⚠ --all：内核树是按 target 解包的，跨 target 结论仅供参考")
        print()

    if not findings:
        if not args.quiet:
            print("未发现死代码：所有补丁改动的 .c 都在各自 Makefile 的编译清单里。")
            if insufficient:
                print(f"（{insufficient} 个文件因缺少对应 Makefile 信息被跳过）")
        return 0

    print(f"[!] 发现 {len(findings)} 个补丁改了不参与编译的文件：\n")
    for f in findings:
        print(f"  {f['patch']}")
        for d in f["dead_files"]:
            print(f"      {d['file']}")
            print(f"          {d['hint']}")
        print()
    print("判据: 补丁改的 .c 必须有同名 .o 出现在同目录 Makefile 的编译清单里。")
    print("详见 docs/01-natflow-deadcode-conflict.md")
    return 1


if __name__ == "__main__":
    sys.exit(main())
