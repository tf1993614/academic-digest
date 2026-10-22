# GitHub 仓库发现用服务端双通道查询 + 本地关键词与星标打分

Issue 05 要求每天给出至多 1 个新库、2 个活跃库，并单独给出至多 2 个 G6 区块
（AI 工具 / Agent Harness）仓库，每条带 stars、语言、最近更新、一句话定位与
“为什么相关”。2026-10 调研实测：GitHub Search 未认证只有 10 次/分钟且按出口 IP
共享，必须用 token（认证后 30 次/分钟、core 5000/小时）；`sort=stars` 每天返回同一批
头部仓库，`sort=updated` 与 `pushed:>` 才能做增量，但 `sort=updated` 翻页会错乱；
官方没有 trending API；`created:>` 能单独抓“刚出现的新库”，`pushed:>` 抓“老库的
新活动”。因此决定：**用固定查询清单分两遍调用
`/search/repositories`（新库 `created:>{since} stars:>={5}`、活跃库
`pushed:>{since} stars:>={30}`），`sort=updated&order=desc` 只取第一页，结果按查询
所属关键词组在本地打分与限量；README 走 `raw.githubusercontent.com`（不占 API
配额），G6 区块独立于论文席位。**

**Decision**：
- 查询清单：G1–G5 共 22 条发现查询（topic 与 `in:name,description,readme` 混用），
  G6 单独 12 条 Claude Code / Codex / DeepSeek Harness 生态查询；清单可整体覆盖，
  省略时按配置里实际存在的组使用默认值。
- 归属：仓库的分组来自返回它的查询，而不是“是否命中关键词”，因此 `ESM-2`、
  `GraphRAG` 这类未写进 topics 的查询仍然可用；分组同时决定它属于论文相关区块
  还是 G6 区块。若同一仓库也被 G6 查询命中，则以 G6 为准并只出现在 G6 区块，
  避免同一个 repo 在两个区块重复。
- 过滤：fork、archived、stars 不足、`created`/`pushed` 落在窗口外的结果在本地
  丢弃，fixture 里可以直接放不合格样本。
- 打分：组内词命中 full name/description/topics 每个 +3、只命中 README 每个 +1；
  分数再加 `round(2 × log10(stars))` 与最近 push 加分（当天 +2、昨天 +1），
  依次按 score、stars、pushed_at、full_name 排序。
- README 预算：每次最多读 `readme_limit`（默认 20）个 README；三个区块各提供
  自己最好的 `max_items + 3` 个候选，预算按区块轮流分配，避免高 star 活跃库把
  新库/G6 的 README 证据挤掉；没进入预算的候选仍参与选择，只是没有 README 加分。
- 令牌与限速：token 从 `github.token_env`（默认 `GITHUB_TOKEN`）读取，启用
  GitHub 而该变量为空时在配置阶段失败；搜索与 `/rate_limit` 请求串行、间隔约
  2 秒，带 User-Agent 与 API 版本头。
- 上限：new 1、active 2、G6 2，不足不补；已作为新库入选的仓库不重复占活跃库
  席位；被 G6 查询命中的仓库只进 G6 区块。
- 定位：依次取 description、README 首段，两者都没有时写成 `owner/repo（无描述）`，
  保证每条记录都有非空的“一句话定位”。
- 审计：查询清单在发起请求前就构造好，因此失败的运行仍保留 `github.passes`
  （查询与已取得的部分计数）。

**Considered options**：GraphQL search（否决：对“发现”没有优势，一样 1000 条上限，
成本不透明、部分字段报错整单失败，只在已知 repo 批量补数据时更省请求）；官方
trending（否决：不存在 JSON API，`/trending` 是网页）；按 `sort=stars` 取头部
（否决：每天同一批仓库）；一次 `topic:` 查询覆盖全部主题（否决：召回低且有 256
字符上限）；全局 README 短名单（否决：高 star 活跃库会挤掉新库与 G6 的 README
证据）；按 SQLite star 增量排序活跃库（暂缓：需要历史快照，首日无数据；当前按
规则分排序，后续可加快照差分）。

**Consequences**：每天 34 条查询 × 2 pass = 68 次 search 请求，2 秒间隔约 2–3 分钟。
这超过 spec 里“采集 30–90 秒”的目标，是有意偏差：68 次请求是 22+12 条查询与
30 次/分钟认证限速的直接结果，整体运行仍在 2–4 分钟内。README 最多 20 次 raw
读取，`found` 在截断与跨区块独占之前统计。阈值与星标是启发式，
“只改 README 的伪活跃”和“一天就弃坑的新库”仍要靠日报模型二次判断；G6 官方库的
release 跟踪与活跃库 star 增量排序分别留给后续 issue。

## Amendment 2026-10-22（Issue 06）

release 跟踪定案：关注库来自 `github.user` 的 starred 列表
（`GET /users/{user}/starred`，只取第一页 100 个），再逐库读
`GET /repos/{owner}/{repo}/releases?per_page=30`；G6 官方库是
`github.official`（有 G6 topic 时默认 `anthropics/claude-code`、`openai/codex`、
`deepseek-ai/deepseek-harness`；没有 G6 topic 时默认为空，与 `g6_queries` 同策略），
同样逐库读取。同一仓库同时在两个列表时只读一次，且只作为官方库出现在
`github.g6_releases`，避免同一 release 在两个区块重复。

窗口 `github.releases.days`（默认 7）含第一天；只认 `published_at`（缺失时不回退
`created_at`），draft 跳过，pre-release 保留并标记。每个仓库只保留窗口内最新的一条
release（关注库与官方库都一样），最新按完整发布时间比较，因此同一天发布多条时
取时间更晚的一条。关注库按发布日期降序、相关性降序、repo 名排序，最多
`github.releases.max_items`（默认 2）条；官方库按日期降序全部进入
`github.g6_releases`（每个官方库最多一条），与 `github.g6` 的 1–2 条生态 repo 并列，
不占关注库名额。相关性沿用 G1–G6 terms：仓库元数据命中每个 +3，仅 release
标题/notes 命中每个 +1；官方 release 归 G6 topic 并按标题与 notes 打分。无更新的
仓库不出现在列表里，不补空条目；`user` 与 `official` 都为空时不发 release 请求，
也不输出 release 区块；配置了跟踪但某一侧没有更新时该侧区块整体省略（没有关注库
更新就不出 `releases`，没有官方更新就不出 `g6_releases`），而不是输出空列表。

每条 release 含 `repo`、`tag`、`name`、本地日期 `date`、`highlights`（release notes；
正文为空时用 release 标题；按 CRLF 归一，含省略号最多 1000 字符，优先在空行段落处
截断，其次换行处）、`url`、`prerelease`、`group` 与 `relevance`。请求与搜索共用约
2 秒的串行节奏，任一次 release 请求失败即 GitHub 源失败（与搜索失败同策略），其余
论文源照常产出。`sources.github.count` 仍只统计 new / active / G6 仓库，release 数量
由 `releases.starred`、`releases.found.starred` 与 `g6_releases` 表达。

**Considered options**：`releases.atom`（否决：需要额外解析 XML，大库响应可达
1.4MB，且拿不到结构化的 draft/prerelease/发布时间；API 返回 JSON，与现有 fixture
模式一致）；把 starred 列表整份写进配置（否决：用户 star 会变化，配置会静默过期；
用户名本来就在 setup 访谈里提供）；一次 GraphQL 批量查询全部 repo（否决：引入
GraphQL 复杂度，11 个 repo 的 core 配额与限速完全够用）；关注库 release 按相关性
优先排序（否决：starred 仓库本身已是用户选择，时间新鲜度更重要；相关性只用于同一天
的排序）。

**Consequences**：每次采集多 1 次 starred 请求与最多 11 次 release 请求（8 个 starred
+ 3 个官方，重叠时更少），core 配额（5000/小时）远未用满，按 2 秒间隔增加约 20 秒。
starred 只取第一页，超过 100 个 star 时只跟踪最近 star 的前 100 个；release notes
只作为日报写作的素材，中文要点仍由会话模型生成。release 不写入 `papers`/`pushes`，
同一 release 在 7 天窗口内可能连续多天进入候选；跨天去重依赖 Issue 08/09 的
selection 与 pushes 记录，本 issue 只保证同一次运行内每个仓库最多一条。活跃库 star
增量排序仍留给后续 issue。
