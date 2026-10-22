# 01: 走通骨架：配置 + 状态 + PubMed → 候选池

**What to build:** 研究者用一份 fixture 配置和录制的 PubMed 响应运行 collect，得到一份候选池；doctor 能校验配置与源；测试从 CLI 边界跑通，全程不碰网络。

**Blocked by:** None (can start immediately).

**Status:** done

- [x] `collect --fixtures` 在有效配置下退出 0，产出候选池 JSON；每条含标题、摘要、DOI/PMID、group、tags。
- [x] 没有摘要的论文仍进入候选池，并带“无摘要”标记；不崩溃。
- [x] `doctor --fixtures` 报告配置与源检查；坏配置以非零退出并指出具体字段。
- [x] 状态库记录 papers 与 runs；同一 fixture 重跑不会重复写入同一论文。
- [x] pytest 通过 CLI 子进程运行，离线、固定 `--now`，不依赖真实网络。

## Comments

- 2026-10-22：已实现。`collect --fixtures` 从录制的 PubMed XML 产出候选池；
  无摘要论文带 `abstract_missing` 与 `无摘要` 标签；`doctor --fixtures` 校验
  配置字段与 PubMed 录制响应；SQLite `papers`/`runs` 记录并支持重跑去重。
  验收：`python3 -m pytest`（10 passed，全部经 CLI 子进程、离线、固定 `--now`）。
