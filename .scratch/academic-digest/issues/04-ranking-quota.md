# 04: 相关性排序 + 分组配额 + top 30 候选池

**What to build:** 采集到的论文按相关性与新鲜度排序，进入一个最多 30 条的候选池；G2 不超过 4 条，非空组至少 1 条；标签能解释命中原因。

**Blocked by:** 02, 03.

**Status:** done

- [x] G2 刷屏的 fixture 中，候选池里 G2 不超过 4 条，G1 仍保留至少 1 条。
- [x] 每条候选带 group 与命中标签；标签来自实际命中的组/词。
- [x] 候选池 ≤30 条；候选不足时不补空条目。
- [x] 固定输入的排序确定（同分有稳定 tie-break）。
- [x] 测试覆盖 G2 刷屏、G1 单条、候选不足。

## Comments

- 2026-10-22：已实现。`score` 现在是规则分 = 相关性 + 新鲜度；`relevance` 单独
  保留相关性部分：沿用 `attach_topic`（标题命中 ×3、摘要命中 ×1，归入加权命中分
  最高的组），`ranking` 新增新鲜度加分（运行日当天 +2、前一天 +1，更早、更晚、
  只有年份或日期缺失 +0；年份精度在同分时排在具体日期之后）。
  新增 `ranking.select_candidates`：按 `score` 降序、`date` 降序、`id` 升序排序
  （同分同日的稳定 tie-break）；先按各组最高分的全局顺序为每个有候选的组保留一条，
  再按全局顺序填空位，同时守住每组
  `max_items` 与 `pool.max_items`（默认 30）；候选不足时按实际数量输出，不补空
  条目。`pool.max_items` 必须不少于 topics 数量，否则配置在发请求前失败，保证
  “非空组至少 1 条”不会因配置过小而静默失效。`tags` 仍只含实际命中的组内词，再
  追加 `预印本` / `无摘要` 标记，因此每条候选都能解释自己的 group 与标签来源。
  新增 `ranking-quota` fixture（15 条候选、`pool.max_items: 6`：G2 刷屏 8 条只留
  4 条，G3 留 1 条，低分的 G1 组保留其最高分 1 条）、`ranking-cap` fixture
  （34 条候选、默认 30 条上限：G1 10、G2 4、G3 6、G4 6、G5 4；G1 的 `max_items`
  设为 10 是为了让五组的总容量超过 30，属于“配额只改配置”的示范）与
  `ranking-freshness` fixture（当天 +2、昨天 +1、未来/更早/只有年份 +0，同分时按
  日期降序）与 `ranking-default-quota` fixture（未写 `max_items`，默认每组 6 条）。新增 8 个 CLI 边界测试，覆盖 G2 刷屏/ G1 单条保留、默认 30 条上限、
  标签来源、新鲜度 +2/+1/+0 与配置时区、摘要命中 +1、默认每组 6 条、日期
  tie-break、候选不足不补、`pool.max_items` 过小的坏配置。
  期刊白名单加分仍暂缓，转到 [11-journal-whitelist.md](11-journal-whitelist.md)
  跟踪。验收：`python3 -m pytest`（42 passed，全部经 CLI 子进程、离线、固定
  `--now`）；`mypy` / `pyflakes` 无问题。
