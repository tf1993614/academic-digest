# 05: GitHub 发现：22 条查询 + 新库/活跃库 + 本地打分

**What to build:** 从 GitHub 找到相关的新库与活跃库，带上 stars、语言、最近更新、README 摘要与“为什么相关”；每天最多 1 个新库、2 个活跃库。

**Blocked by:** 01, 04.

**Status:** done

- [x] fixture 搜索结果显示新库（created > 7 天、stars ≥ 5）与活跃库（pushed > 7 天、stars ≥ 30）。
- [x] 每类数量受 1/2 上限约束；不足时不补。
- [x] 每个 repo 含 owner/repo、stars、语言、最近更新、定位、相关性理由；README 通过 raw fixture 读取。
- [x] G6 的 12 条发现查询可用，能产出 Claude Code/Codex/DSH 生态候选。
- [x] 缺 token 时 CLI 明确报错；搜索请求带 UA 并按限速串行。
- [x] 测试覆盖上限、查询构造、缺 token。

## Comments

- 2026-10-22：已实现。新增 `academic_digest/github.py`，导出 `NAME`、
  `discover(config, fixtures_root, now)` 与 `check(config, fixtures_root)`；它不进
  论文源注册表，仓库永远不进入 `papers`。`sources.github: true` 时 `collect`
  额外输出顶层 `github` 区块，并像其它源一样把状态写进 `sources.github`
  （失败时其余源照常产出候选）。
- 配置：`github` 段可整体省略（全部走默认值）。`github.queries` 是组名到检索词
  的映射，默认是 22 条 G1–G5 发现查询且只保留配置里存在的组；
  `github.g6_queries` 默认 12 条 G6 查询，`github.g6_topic` 指定其归属组（默认
  `G6`；没有该组时省略默认 G6 查询）。`github.new` / `github.active` 各含
  `days`、`min_stars`、`max_items`（默认 7/5/1 与 7/30/2），`github.g6.max_items`
  默认 2，`github.readme_limit` 默认 20。GitHub 不需要 `lookback`，用自己的两个
  窗口；`lookback` 段现在也可以整体省略。
- 查询构造：每条查询按 pass 追加 `created:>{since} stars:>={min_stars}` 或
  `pushed:>{since} stars:>={min_stars}`，`sort=updated`、`order=desc`、只取第一页
  `per_page=100`。本地按 `created`/`pushed` 日期、stars 门槛再过滤一遍，并丢弃
  fork 与 archived；仓库的分组来自返回它的查询，不会因未命中关键词被丢掉。
  `passes.<pass>.queries` 输出本次构造的完整查询（含日期与星标门槛）供审计，因此
  查询构造可以在 CLI seam 断言。
- 令牌：`github.token_env`（默认 `GITHUB_TOKEN`）为空时，配置校验在创建状态库、
  发请求之前失败（`github.token`，退出码 2）；搜索与 `/rate_limit` 请求带
  User-Agent、`Bearer` token 与 GitHub API 版本头，串行并间隔约 2 秒（认证后
  30 次/分钟）。token 不进入输出、状态库或日志。
- 本地打分：`relevance` = 组内词命中 full name/description/topics 每个 +3、只命中
  README 每个 +1；`score` = 相关性 + `round(2*log10(stars))` + 最近 push 加分
  （当天 +2、昨天 +1），依次按 score、stars、pushed_at、full_name 排序。README
  走 `raw.githubusercontent.com`（不占 API 配额）；三个区块先各取自己最好的
  `max_items + 3` 个候选，再按 `readme_limit`（默认 20）总额度轮流分配读取，
  避免高分活跃库把新库/G6 的 README 挤掉；没进入预算的候选仍参与选择，只是
  没有 README 加分；README 缺失不是源失败。
- 上限：new 1、active 2、G6 2，不足不补；已作为新库入选的仓库不重复占活跃库
  席位，被 G6 查询命中的仓库只进 G6 区块（即使先被 G1–G5 查询命中，也以 G6 的
  组与查询为准）。`found` 给出截断前的合格数，`limits` 给出三个上限。
- 定位兜底：`positioning` 依次取 description、README 首段，都没有时写成
  `owner/repo（无描述）`，保证字段非空。
- 失败审计：两个 pass 的完整查询在发请求前构造，所以即使搜索中途失败，
  `github.passes` 仍保留查询与已取得的部分 `results` 计数。
- 测试：新增 `tests/test_github.py`（17 个 CLI 用例）与 `tests/fixtures/github/`
  （仅 GitHub 的最小配置、4 条查询 × 2 pass 的录制搜索响应、可选 README），覆盖
  新库/活跃库上限、字段与 README 打分、定位回退、门槛过滤、new/active 不重复、
  空区块不补条目、G6 三种生态、22+12 默认查询构造与请求参数、缺 token、坏
  fixture、doctor 回放与缺 token。`conftest.run_collect` 增加 `env` 参数以便缺
  token 用例清空 `GITHUB_TOKEN`。
- 已知偏差：`docs/decisions.md` 里“活跃库按 SQLite star 增量排序”未实现；当前按
  `spec.md` 的“`log10(stars)` + 最近 push 加分”排序，README 已注明。G6 官方库的
  release 跟踪属于 06。采集耗时也从 spec 的 30–90 秒升到约 2–3 分钟（68 次搜索是
  22+12 查询 × 2 pass 与 30 次/分钟限速的必然结果，整体仍在 2–4 分钟内）。
  `found` 是截断前、也早于跨区块独占的合格数。
