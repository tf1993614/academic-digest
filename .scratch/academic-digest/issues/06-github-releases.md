# 06: GitHub release：8 个关注库 + 3 个 G6 官方库

**What to build:** 跟踪用户已 star 的 8 个 repo 与 Claude Code/Codex/DSH 三个官方库的新 release；每天最多 2 条，没有更新就不出现空区块。

**Blocked by:** 05.

**Status:** done

- [x] fixture starred 列表（8 个）与 7 天内 release 产出最多 2 条关注库 release。
- [x] 三个官方库在窗口内有 release 时进入 G6 数据；无更新时不生成条目。
- [x] 每条含 repo、tag、日期、更新要点、链接。
- [x] 多个 release 时按时间/相关性取前 2；不重复。
- [x] 测试覆盖无更新、多更新、官方库更新。

## Comments

- 2026-10-22：已实现 GitHub release 跟踪。关注库来自 `github.user` 的 starred
  列表（`GET /users/{user}/starred`，只取第一页），再逐库读
  `/repos/{owner}/{repo}/releases`；官方库由 `github.official` 指定（有 G6 topic 时
  默认 `anthropics/claude-code`、`openai/codex`、`deepseek-ai/deepseek-harness`，
  没有 G6 topic 时默认为空，与 `g6_queries` 同策略）。同一仓库同时在两个列表时只读
  一次、只作为官方库出现在 G6 数据里。
- 窗口 `github.releases.days`（默认 7，含第一天）；只认 `published_at`（缺失时不回退
  `created_at`），draft 跳过，pre-release 保留并标 `prerelease`。每个仓库只保留窗口
  内最新的一条 release（按完整发布时间比较，同一天取更晚的），避免同一项目重复。
  关注库按发布日期降序、相关性降序、repo 名排序，最多 `github.releases.max_items`
  （默认 2）条；官方库每个最多一条、按日期降序进入顶层 `github.g6_releases`，与
  `github.g6` 的 1–2 条生态 repo 并列，不占关注库名额。没有更新的仓库不出现在列表
  里，不补空条目；`user` 与 `official` 都为空时不发 release 请求；配置了跟踪但某
  一侧没有更新时该侧区块整体省略（没有关注库更新就不出 `releases`，没有官方更新就
  不出 `g6_releases`），不会出现空区块。
- 每条 release 含 `repo`、`tag`、`name`、本地日期 `date`、`highlights`（release
  notes；正文为空时用标题；含省略号最多 1000 字符，优先在空行段落处截断，其次
  换行处）、`url`、`prerelease`、`group` 与 `relevance`。相关性沿用 G1–G6 terms：
  仓库元数据命中每个 +3、仅标题/notes 命中每个 +1；官方 release 归 G6 topic。
  `sources.github.count` 仍只统计 new/active/G6 仓库；release 数量看
  `releases.starred`、`releases.found.starred` 与 `g6_releases`。
- 失败策略与搜索一致：任一 release 请求失败即 GitHub 源失败（保留 `passes` 审计），
  其余论文源照常产出；`doctor --fixtures` 会回放 starred 列表与每个 release feed。
- 配置：`github.user` 为空则跳过关注库区块；`github.official` 显式配置时必须
  `github.g6_topic` 存在于 `topics`，条目须为 `owner/repo`；没有 G6 topic 时默认
  官方库为空。
- 已知偏差：starred 只取第一页（100 个）；官方 release 不设每日上限（每个官方库
  最多一条）；release 不写入 `papers`/`pushes`，同一 release 在 7 天窗口内可能连续
  多天进入候选，跨天去重留给 Issue 08/09 的 selection 与 pushes 记录；活跃库 star
  增量排序仍未实现。
