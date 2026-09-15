# docs 索引

按「先懂原理 → 再看补丁 → 再动手 → 再看证据」的顺序读。

| 文档 | 内容 | 什么时候看 |
|---|---|---|
| [01-natflow-deadcode-conflict.md](01-natflow-deadcode-conflict.md) | **起因**：natflow 顶掉 `mtk_ppe.c` / `mtk_ppe_offload.c`，导致 flint4 的一批补丁静默失效；受影响的补丁全清单；通用判定规则 | 第一次接触这个仓库 |
| [02-patch-999-ppe1-yt922x-port-tag.md](02-patch-999-ppe1-yt922x-port-tag.md) | **修复补丁的完整说明**：PPE 那 4 个字节到底怎么组成、为什么必须用 `set_vlan()`、端口 ctrl 查表、逐 hunk 解释、为什么编号 999、风险与回滚、**怎么确认补丁真的编进去了** | 要用/要改/要重放这个补丁 |
| [03-removed-dsa-bypass-workaround.md](03-removed-dsa-bypass-workaround.md) | **被删掉的绕过方案**：它是怎么把症状盖住的、为什么不能用、判定「真修复 vs 绕过」的方法 | 想说「先能用就行」之前 |
| [04-known-gaps.md](04-known-gaps.md) | **已知缺口**：哪些 flint4 补丁还没移植到 `*1.c`（`bridger` 会用到）、哪些测试还没做、上游依赖风险 | 上生产前 |
| [05-tool-check-deadcode.md](05-tool-check-deadcode.md) | `check-xwrt-deadcode.py` 的原理、Kbuild 各种写法的识别范围、真实输出、局限 | 换树/升级后 |
| [06-tool-apply-to-xwrt.md](06-tool-apply-to-xwrt.md) | `apply-to-xwrt.sh` 的设计取向（只复制补丁、幂等、冲突即停）与用法 | 装补丁时 |
| [07-verification.md](07-verification.md) | **怎么证明修复生效**（吞吐 + CPU + PPE 三证据）与本次实测数据 | 验证 / 复现 |

补丁本体：`../patches/`
完整报告：`../verification/`
