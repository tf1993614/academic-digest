# 02: Europe PMC + 跨源/跨天去重

**What to build:** 加入 Europe PMC 后，同一篇论文从 PubMed 和 EPMC 进来只出现一次；已推送过的条目不再进入候选池；单源失败时另一源仍能产出结果。

**Blocked by:** 01.

**Status:** done

- [x] PubMed/EPMC 的同一 DOI 只出现一次，字段按 PubMed 摘要/期刊优先合并。
- [x] 预印本记录保留 preprint 标记与来源。
- [x] 用 seeded 状态模拟“已推送”的 ID，该条不出现在候选池。
- [x] 输出含各源计数与失败源；一个源 fixture 报错时另一源仍产出候选。
- [x] 测试覆盖重复 DOI、已推送排除、单源失败。

## Comments

- 2026-10-22：已实现。`collect` 增加 Europe PMC 源（`resultType=core`，fixture 为
  `europepmc/search.json`）；跨源按 DOI/PMID/arXiv 强标识去重，PubMed 的摘要与
  期刊优先，EPMC 预印本保留 `is_preprint` 与 `source`；状态库新增 `pushes` 表，
  已推送条目在候选池截断前排除；单源失败时其余源继续产出，并在 `sources` 与
  stderr 标出失败原因。`doctor` 同步校验 EPMC fixture / 连通性。新增
  `multisource` fixture 覆盖重复 DOI/PMID、预印本、EPMC-only 与来源计数。
  验收：`python3 -m pytest`（17 passed，全部经 CLI 子进程、离线、固定 `--now`）；
  `mypy` / `pyflakes` 无问题。
