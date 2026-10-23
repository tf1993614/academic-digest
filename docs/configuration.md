# 配置参考

从 [`config.example.yaml`](../config.example.yaml) 复制一份到仓库根的 `config.yaml`
（已被 gitignore），再按需增删关键词组。示例已是生产默认：六组 G1–G6、PubMed /
Europe PMC / arXiv / Research Square / GitHub 打开，GitHub 用户为 `tf1993614`；
`config.yaml` 不提交。启用 `sources.github` 时先加载 `secrets.env`，否则配置校验会报
`github.token`。

配置校验在创建状态库、发起请求之前完成；未知字段会直接报错，避免拼写错误被静默忽略。
`paths` 里的相对路径按配置文件所在目录解析。

## 默认值一览

| 字段 | 默认值 | 说明 |
|---|---|---|
| `timezone` | 必填 | IANA 时区，例如 `Asia/Shanghai` |
| `lookback.<source>` | 必填（`github` 除外） | 每个启用源的回看天数，正整数 |
| `topics` | 必填 | 非空的关键词组列表 |
| `topics[].max_items` | `6` | 该组在候选池里的席位上限 |
| `journal_filter` | `[]` | 空列表 = 不限期刊 |
| `sources` | 必填 | 至少一个源为 `true`，且必须显式写出 `pubmed` |
| `arxiv.categories` | 启用 `arxiv` 时必填 | 每个分类读一个 RSS |
| `github.token_env` | `GITHUB_TOKEN` | 读取 GitHub token 的环境变量名 |
| `github.user` | 空 | 非空时跟踪该用户 starred 库的 release |
| `github.official` | 三个官方库（仅当有 G6 topic） | `anthropics/claude-code`、`openai/codex`、`deepseek-ai/deepseek-harness` |
| `github.new.days` | `7` | 新库发现窗口 |
| `github.new.min_stars` | `5` | 新库的 star 门槛 |
| `github.new.max_items` | `1` | 新库每天最多几条 |
| `github.active.days` | `7` | 活跃库发现窗口 |
| `github.active.min_stars` | `30` | 活跃库的 star 门槛 |
| `github.active.max_items` | `2` | 活跃库每天最多几条 |
| `github.g6.max_items` | `2` | G6 生态 repo 的条数上限 |
| `github.readme_limit` | `20` | 每次最多读多少个 README |
| `github.releases.days` | `7` | 关注库 release 的窗口 |
| `github.releases.max_items` | `2` | 关注库每天最多几条 release |
| `fulltext.unpaywall.email` | `""` | 留空时跳过 Unpaywall |
| `push.sendkey_env` | `SERVERCHAN_SENDKEY` | 读取 SendKey 的环境变量名 |
| `push.channel` | `serverchan` | V1 只接受 `serverchan` |
| `push.send_empty` | `true` | 空日报是否发送一条提示 |
| `push.split_bytes` | `30000` | 超过即按顶层 section 拆分 |
| `push.max_bytes` | `32768` | 单条消息的 UTF-8 字节上限，`split_bytes` 不得大于它 |
| `push.max_messages` | `2` | 拆分后的消息条数上限 |
| `push.title_max` | `32` | 标题的 Unicode 字符上限 |
| `push.retries` | `2` | 每条消息失败后的重试次数 |
| `push.backoff_seconds` | `1` | 指数退避的基数秒数 |
| `push.timeout` | `30` | 单次 HTTP 请求超时（秒） |
| `push.pending_days` | `2` | pending 消息的保留日历日数 |
| `pool.max_items` | `30` | 候选池总数上限，不得少于 `topics` 数量 |
| `paths.state_db` | `state/academic-digest.sqlite3` | SQLite 状态库 |
| `paths.candidates` | `out/candidates.json` | 候选池输出 |

## 顶层字段

### `timezone`

IANA 时区，例如 `Asia/Shanghai`。日报日期、新鲜度加分、运行窗口与 pending 年龄都按它计算。

### `lookback.<source>`

每个启用源的回看天数，正整数；启用某源时必须给出对应的 `lookback`（`github` 不需要，
它用自己的 `github.new.days` / `github.active.days`）。启用 `arxiv` 时
`lookback.arxiv` 至少 4 天，否则配置校验失败——周五到周一的投稿会合并成一批公告。
示例值：`pubmed: 2`、`europepmc: 2`、`arxiv: 4`、`researchsquare: 3`、
`biorxiv: 2`、`medrxiv: 2`。

### `topics`

非空列表；每项含 `name`、`label`、`terms`、可选 `exclude`、`max_items`。`name` 唯一，
`terms` 非空。`max_items` 是该组在候选池里的席位上限（默认 6，例如 G2 为 4）；每个有
候选的组仍至少保留其最高分的一条。`exclude` 里的词一旦命中，该论文就不会归入这一组。

### `journal_filter`

可选的期刊白名单，默认 `[]`（不限期刊）。非空时 PubMed 用 `"期刊名"[Journal]`、
Europe PMC 用 `JOURNAL:"期刊名"` 过滤查询，命中名单的候选在排序时 +2。期刊名必须是
来源报告的完整名称（大小写不敏感、内部空白折叠），不能含双引号。名单由用户提供，可参考
[Nature Index 期刊列表](https://www.nature.com/nature-index/faq)。

### `sources`

数据源开关；支持 `pubmed`、`europepmc`、`arxiv`、`researchsquare`、`biorxiv`、
`medrxiv`、`github`。必须显式写出 `sources.pubmed`（可设 true/false），且至少要启用
一个源；未写出的源视为关闭，因此 bioRxiv / medRxiv 默认关闭。启用 `github` 时，
`github.token_env` 指向的环境变量必须非空。

### `arxiv`

`arxiv.categories` 是启用 arXiv 时必填的非空分类列表（例如 `cs.LG`、`q-bio.QM`），
每个分类读一个 RSS；不启用时可省略。

### `github`

- `token_env`：读取 GitHub token 的环境变量名，默认 `GITHUB_TOKEN`。token 不写入
  Prompt、日志或候选池。
- `user`：GitHub 登录名。非空时读该用户的 starred 列表并跟踪其 release；留空则跳过
  关注库 release 区块（不影响新库/活跃库/G6 发现）。
- `official`：G6 官方库列表，默认 `anthropics/claude-code`、`openai/codex`、
  `deepseek-ai/deepseek-harness`；配置里没有 G6 topic 时默认为空，显式配置则要求
  `github.g6_topic` 存在。与 starred 列表重叠的仓库只作为官方库出现一次。
- `releases`：`days`（默认 7，窗口含第一天）与 `max_items`（关注库最多几条，默认 2）。
  官方库不设额外上限，每个官方库最多一条。
- `new` / `active`：各含 `days`、`min_stars` 与 `max_items`（默认 7 天 / 5 星 / 1 条，
  以及 7 天 / 30 星 / 2 条）。
- `g6.max_items`：G6 生态 repo 的条数上限，默认 2。
- `readme_limit`：每次最多读多少个 README，默认 20；按 new / active / G6 三个区块轮流
  分配，每个区块先取自己最好的 `max_items + 3` 个候选。
- `queries`：组名到检索词的映射，默认是 22 条 G1–G5 发现查询，只保留配置里实际存在的组。
- `g6_queries`：G6 区块的 12 条生态查询；`g6_topic` 指定它们归入哪个组（默认 `G6`；
  没有该组时省略默认 G6 查询）。

### `fulltext`

`fulltext.unpaywall.email`：Unpaywall API 要求的联系邮箱；可留空。留空时 `fulltext`
跳过 Unpaywall，仍会尝试 Europe PMC、arXiv 与预印本 PDF。邮箱只作为请求参数与
User-Agent 的一部分，不写入日报或日志。

### `push`

全部可省略：`sendkey_env`（默认 `SERVERCHAN_SENDKEY`）、`channel`（V1 只接受
`serverchan`）、`send_empty`（默认 `true`）、`split_bytes`（默认 30000）、`max_bytes`
（默认 32768，且 `split_bytes` 不得大于它）、`max_messages`（默认 2）、`title_max`
（默认 32）、`retries`（默认 2）、`backoff_seconds`（默认 1）、`timeout`（默认 30 秒）、
`pending_days`（默认 2）。`retries` 与 `backoff_seconds` 为非负整数，其余数值为正整数。
SendKey 本身不写进配置，只从 `sendkey_env` 指向的环境变量读取。

### `pool`

`pool.max_items`：候选池总数上限，默认 30，必须不少于 `topics` 数量（保证每个非空组
至少 1 条）；候选不足时不补空条目。

### `paths`

`paths.state_db` / `paths.candidates`：相对路径按配置文件所在目录解析。

## 校验规则

- 未知字段直接报错，不静默忽略。
- `topics[].name` 不得重复，`terms` 不得为空。
- `lookback` 覆盖每个启用源；`arxiv` 的窗口至少 4 天。
- `pool.max_items` 不少于 `topics` 数量。
- `push.split_bytes` 不大于 `push.max_bytes`；`push.channel` 只接受 `serverchan`。
- 启用 `sources.github` 时必须能读到 `GITHUB_TOKEN`（或 `token_env` 指定的变量）。

坏配置会让命令以退出码 2 结束，并在 stderr 指出具体字段，例如
`[fail] topics: must be a non-empty list`。命令与退出码见 [cli.md](cli.md)。
