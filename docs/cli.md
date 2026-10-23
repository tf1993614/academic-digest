# 命令参考

入口脚本在 `skills/academic-digest/scripts/`，从仓库根执行；也可以
`pip install -e ".[dev]"` 后用 `academic-digest <command>`。所有命令都在发起网络请求前
完成配置校验。

运行数据（`config.yaml`、`secrets.env`、`out/`、`state/`）始终留在仓库根，不跟着 skill 走。
需要 secrets 的命令先加载 `secrets.env`：

```bash
set -a; . ./secrets.env; set +a
```

`--fixtures DIR` 只读录制响应、绝不联网，给出时应同时固定 `--now`，这样同一次运行可复现。
配置项的默认值见 [configuration.md](configuration.md)。

| 命令 | 用途 |
|---|---|
| [`collect`](#collect) | 抓取各源，写出候选池 |
| [`fulltext`](#fulltext) | 取单篇 OA 全文并抽取方法 / 结果 / 局限 |
| [`digest check`](#digest-check) | 校验模型写的 selection 与日报 |
| [`push`](#push) | 把校验过的日报推到微信 |
| [`doctor`](#doctor) | 检查配置、源连通性与状态库路径 |

## `collect`

```text
collect --config PATH [--fixtures DIR] [--now ISO8601] [--out PATH] [--state-db PATH]
```

- `--config`：YAML 配置，默认 `config.yaml`。
- `--fixtures`：录制响应目录。给出时绝不发起网络请求。
- `--now`：逻辑时钟；包含 `--fixtures` 的测试必须固定它。
- `--out`：候选池 JSON；默认取配置 `paths.candidates`。
- `--state-db`：SQLite 状态库；默认取配置 `paths.state_db`。

离开 `--fixtures` 时通过 PubMed E-utilities 的 `esearch` + `efetch`、Europe PMC
的 `search`（`resultType=core`）、arXiv 的 RSS 与 API、Research Square 的 RSS，以及按需
开启的 bioRxiv/medRxiv `details` API 抓取。PubMed 摘要只从 XML 解析
（JSON 模式会静默丢掉摘要）。每个 live GET 在连接错误、5xx 或 429 时最多 3 次尝试
（2 次重试，1s/2s 退避；429 至少等 2s，避免绕过 GitHub 的 30 次/分钟节奏）；读超时
与其它 4xx 不重试。仍失败才把该源标为 `failed`，不会因为一次掉线丢掉整天的
GitHub/G6 区块。`--fixtures` 直接读录制文件，不经过这个重试层。

启用 `sources.github` 时还会调用 GitHub Search API 抓取新库、活跃库与 G6 区块
（AI 工具 / Agent Harness）的仓库；搜索请求串行、约 2 秒一次，带 User-Agent 与
token。仓库不进入 `papers`，而是写入顶层 `github` 区块（见“GitHub 发现”）。

PubMed 仍是主源，Europe PMC 用来补充预印本与缺失摘要。跨源去重按
DOI > PMID > arXiv ID 匹配：任一强标识相同就合并为一条，PubMed 的摘要与
期刊优先，其余字段只补空；没有强标识时才退回“标题 + 年份”哈希。同一预印本
同时出现在 PubMed 与 EPMC 时保留 `is_preprint: true`；合并组里只要有一个已发表
版本，就不再标记为预印本。Europe PMC 的预印本保留 `source: europepmc`。
状态库 `pushes` 表里的条目不会再进入候选池（跨天去重）。

### 预印本

- **arXiv**：每个配置分类读 `rss.arxiv.org/rss/<cat>`，只保留
  `announce_type=new`；`replace`（新版本）与 `cross`（其他分类的重复公告）丢弃。
  RSS 的 `dc:creator` 提供作者，`oa_url` 直接给 PDF。另用 API 按配置分类与
  `topics` 关键词回看 `lookback` 窗口，跳过 `updated != published` 的新版本，
  用于补上错过的公告批次；同一 arXiv ID 只保留一条，API 补 DOI/期刊信息。
  `lookback.arxiv` 必须 ≥ 4 天（周五到周一的投稿合并公告），窗口外的条目不会入选。
- **Research Square**：读公开 RSS，使用 `<abstract>`、`<authors>`、`<doi>`，
  从 `<description>` 的 `created on` 解析日期；不调用需要申请 token 的官方 API。
- **bioRxiv / medRxiv**：默认关闭。开启后按 `lookback` 日期区间分页拉取
  （30 条/页），只保留窗口内的记录，再由关键词组在本地过滤。
- 所有预印本的 `is_preprint` 为 `true`，`tags` 中含 `预印本`（无摘要时再追加
  `无摘要`）；与期刊版本共用 DOI 时只保留一条，并以已发表版本的字段和摘要优先。

单个源失败时其余源继续产出候选，退出码仍为 0；失败原因写进
`sources.<name>.error` 和 stderr。只有全部启用源都失败才退出 1。

`collect` 的 JSON 顶层包含 `schema_version`、`generated_at`、`date`、
`timezone`、`lookback_days`、`sources`、`candidate_count` 和 `papers`；启用
GitHub 时还有一个 `github` 区块。
`sources` 逐源给出计数与失败状态：

```json
"sources": {
  "pubmed": {"status": "ok", "count": 2},
  "europepmc": {"status": "failed", "count": 0, "error": "invalid Europe PMC JSON: …"}
}
```

每篇论文至少包含：

```json
{
  "id": "doi:10.1000/aging-omics.1",
  "group": "G1",
  "source": "pubmed",
  "title": "…",
  "authors": ["Wei Zhang"],
  "venue": "Nature Aging",
  "date": "2026-10-20",
  "doi": "10.1000/aging-omics.1",
  "pmid": "39000001",
  "arxiv_id": "",
  "url": "https://pubmed.ncbi.nlm.nih.gov/39000001/",
  "abstract": "…",
  "abstract_missing": false,
  "tags": ["aging", "senescence", "multi-omics"],
  "relevance": 7,
  "score": 7,
  "is_preprint": false,
  "journal_match": false,
  "oa_url": null
}
```

没有摘要的论文仍会进入候选池：`abstract` 为空、`abstract_missing` 为
`true`，`tags` 中带 `无摘要`。

### 排序与分组配额

`score` 是规则分，由三部分相加；`relevance` 单独保留相关性部分：

- **相关性**（`relevance`）：论文归入加权命中分最高的组；组内每个命中词，
  标题命中 +3、摘要命中 +1。
- **新鲜度**：发布日等于运行日（配置时区）当天 +2、前一天 +1，更早、更晚或
  日期缺失 +0。日期只精确到年份（例如 Europe PMC 的 `pubYear`）时按缺失处理：
  不加新鲜度分，并在同分时排在标了具体日期的论文之后。
- **期刊白名单**：`journal_filter` 非空且论文 `venue` 命中名单时 +2，并把
  `journal_match` 置为 `true`；名单为空（默认）时所有论文都不加分。

候选池按 `score` 降序、`date` 降序、`id` 升序排列。同分同日时用 `id` 做稳定
tie-break，因此固定 fixture 与 `--now` 每次得到完全相同的顺序。

截断分两步，保证宽泛组不刷屏、窄组不会整天消失：

1. 先按各组最高分的全局顺序，为每个有候选的组保留一条；
2. 再按全局顺序填空位，但任何组都不超过配置的 `max_items`。

`max_items` 默认 6（示例配置里 G2 为 4），`pool.max_items`（默认 30）是总数上限；
两者都可按配置调整，候选不足时按实际数量输出，不补空条目。
`tags` 只列出实际命中的词（再追加 `预印本` / `无摘要` 标记），`group` 就是这些
词所属的组，所以每条候选都能解释自己为什么被选中。

### 期刊白名单

`journal_filter` 是可选的期刊白名单，默认 `[]`（或省略）= 不限期刊：

- 非空时只改 **PubMed** 与 **Europe PMC** 的查询：PubMed 追加
  `("Nature Aging"[Journal] OR "Cell"[Journal])`，Europe PMC 追加
  `(JOURNAL:"Nature Aging" OR JOURNAL:"Cell")`；arXiv、Research Square、
  bioRxiv/medRxiv 与 GitHub 的查询不变，也不抓期刊官网。
- 名称按来源报告的完整期刊名匹配，大小写不敏感、内部空白折叠；命中时候选池
  的 `journal_match` 为 `true`，`score` 额外 +2。
- 名单里的名称应与来源实际报告的标题一致。PubMed 的 `[Journal]` 对含括号、方括号、
  `&` 等特殊字符的刊名可能要求去掉这些字符后再检索；若某一条没有命中，按 PubMed
  帮助调整该条即可，不影响其它条目。
- 名单为空时查询语义与分数保持原样，不影响 3 + 7 的入选逻辑。
- 名单由用户提供，本仓库不内置；[Nature Index 的期刊列表](https://www.nature.com/nature-index/faq)
  可作为参考，把其中的期刊全名逐条写进 `journal_filter`。

`doctor` 会打印 `journal filter: …`，空名单显示 `unrestricted`，便于确认当前是否
启用了白名单。实现与验收见
[11-journal-whitelist.md](../.scratch/academic-digest/issues/11-journal-whitelist.md)。

### GitHub 发现

`sources.github: true` 时，`collect` 用 22 条发现查询（G1–G5）与 12 条 G6 查询
各跑两遍 GitHub Search：

- **新库**：`created:>7天前` + `stars:>=5`，每天最多 1 条；
- **活跃库**：`pushed:>7天前` + `stars:>=30`，每天最多 2 条；
- **G6 区块（AI 工具 / Agent Harness）**：Claude Code / Codex / DeepSeek Harness
  等 12 条查询，最多 2 条，单独成块，不占论文席位。

两遍都用 `sort=updated&order=desc`，只取第一页（`per_page=100`）；`sort=updated`
翻页会错乱，增量场景只看第一页。搜索请求串行、间隔约 2 秒（认证后 30 次/分钟），
每次带 User-Agent 与 token。token 从 `github.token_env`（默认 `GITHUB_TOKEN`）
读取；启用 GitHub 却没有该环境变量时，配置校验在发请求前失败（退出码 2）。

查询结果在本地过滤：fork、archived、stars 不足、`created` / `pushed` 落在窗口
外的仓库都丢弃。仓库的分组来自返回它的查询，因此不会因为“没命中关键词”被丢掉。
本地打分：

- **相关性**（`relevance`）：该组关键词命中 full name / description / topics
  每个 +3，只命中 README 的每个 +1。README 从 `raw.githubusercontent.com` 读取，
  不占 API 配额；三个区块先各取自己最好的几个候选，再按 `github.readme_limit`
  （默认 20）的总额度轮流分配读取，避免高分活跃库把新库/G6 的 README 挤掉。
  没进入预算的候选仍参与选择，只是没有 README 加分。
- **分数**（`score`）：相关性 + `round(2 × log10(stars))` + 最近 push 加分
  （当天 +2、昨天 +1）。排序依次按 `score`、`stars`、`pushed_at`、`full_name`。

每条仓库含 `full_name`、`url`、`description`、`positioning`（一句话定位；描述为空
时取 README 首段）、`why`（命中的查询与关键词）、`stars`、`language`、
`created_at`、`pushed_at`、`topics`、`group`、`query`、`tags`、`relevance`、
`score` 与 `readme_url`。`new` / `active` / `g6` 三个区块都受上限约束，不足时不补
空条目；已经作为新库出现的仓库不会重复占用活跃库席位，被 G6 查询命中的仓库
只进 G6 区块（`found` 仍按各区块的合格候选数统计）。`positioning` 依次取仓库
描述、README 首段，两者都没有时写成 `owner/repo（无描述）`，保证字段非空。

启用 GitHub 时，`collect` 的顶层多一个 `github` 区块：

```json
"github": {
  "passes": {
    "new": {
      "since": "2026-10-15",
      "min_stars": 5,
      "params": {"sort": "updated", "order": "desc", "per_page": 100},
      "queries": ["topic:single-cell created:>2026-10-15 stars:>=5", "…"],
      "results": 12
    },
    "active": {"since": "2026-10-15", "min_stars": 30, "queries": ["…"], "results": 9}
  },
  "limits": {"new": 1, "active": 2, "g6": 2},
  "found": {"new": 2, "active": 5, "g6": 3},
  "new": [{"full_name": "acme/cell-atlas"}],
  "active": [],
  "g6": []
}
```

`passes.<pass>.queries` 是本次实际构造的完整查询（含日期与 star 门槛），用于审计；
`found` 是上限截断前、也早于跨区块独占的合格仓库数（被 G6 命中的仓库仍计入
new/active 的 `found`）。状态库不记录仓库，`sources.github` 只给 `status` 与入选
总数；搜索失败时其余源照常产出候选。

34 条查询各跑两遍 = 68 次搜索，按 2 秒间隔约 2–3 分钟。整体运行目标 2–4 分钟；
某个源不可达时会超过这个目标，失败源照实写进页脚，不阻塞其它源。活跃库按 star
增量排序尚未实现，当前按上面的规则分排序。

### GitHub release 跟踪

`github.user`（GitHub 登录名）非空时，`collect` 读该用户的 starred 列表
（`GET /users/{user}/starred`，只取第一页 100 个），再逐库读
`GET /repos/{owner}/{repo}/releases?per_page=30`。`github.official` 是 G6 官方库
列表（默认 `anthropics/claude-code`、`openai/codex`、
`deepseek-ai/deepseek-harness`），同样逐库读取；同一仓库同时出现在两个列表时只
作为官方库读一次、只出现一次。

- **关注库 release**（`releases.starred`）：`github.releases.days`（默认 7 天，
  含窗口第一天）内、`published_at` 落在窗口里且非 draft 的 release；每个仓库只保留
  发布日期最新的一条（同一天按完整发布时间比较），按发布日期降序、相关性降序、
  repo 名排序，最多 `github.releases.max_items`（默认 2）条。相关性沿用 G1–G6
  terms：命中仓库名/描述/topics 每个 +3，只命中 release 标题/notes 每个 +1。没有
  新 release 的仓库不出现，也不补空条目。
- **官方库 release**（`g6_releases`）：每个官方库最多一条窗口内最新 release，按
  日期降序进入 G6 数据，与 `github.g6` 的生态 repo 并列（`group` 为 G6 topic）；
  某个官方库没有更新时它不出现在列表里。官方 release 不占关注库的 2 条名额，也
  不占 1–2 条生态 repo 的名额。

每条 release 含 `repo`、`tag`、`name`、`date`（配置时区的本地日期）、
`highlights`（release notes；正文为空时退回 release 标题；最多 1000 字符，含
省略号，优先在段落或换行处截断）、`url`、`prerelease`、`group` 与 `relevance`。
draft 跳过，缺少 `published_at` 的条目不参与（不回退 `created_at`）；pre-release
保留并标 `prerelease: true`。release 请求与搜索请求共用串行节奏（约 2 秒一次）；
任一 release 请求失败时 GitHub 源整体失败（`sources.github.status: failed`），
其余论文源照常产出。`github.user` 与 `github.official` 都为空时不读取 release，
也不输出 release 区块；配置了跟踪但一侧没有更新时该侧区块整体省略（没有 starred
更新就不出 `releases`，没有官方更新就不出 `g6_releases`），不会出现空列表组成的
空区块。

```json
"github": {
  "...": "passes / limits / found / new / active / g6 见上",
  "releases": {
    "since": "2026-10-15",
    "days": 7,
    "limits": {"starred": 2},
    "found": {"starred": 4},
    "starred": [
      {
        "repo": "acme/aging-atlas",
        "tag": "v0.3.0",
        "name": "Aging Atlas 0.3.0",
        "date": "2026-10-22",
        "highlights": "- Faster cell-type annotation\n- Fix batch effect edges",
        "url": "https://github.com/acme/aging-atlas/releases/tag/v0.3.0",
        "prerelease": false,
        "group": "G1",
        "relevance": 6
      }
    ]
  },
  "g6_releases": [
    {
      "repo": "anthropics/claude-code",
      "tag": "v2.0.0",
      "date": "2026-10-21",
      "group": "G6",
      "...": "其余字段与 starred 相同"
    }
  ]
}
```

`releases.found.starred` 是上限截断前的关注库候选数（含没有进入前 2 的仓库）；
官方 release 的条数就是 `g6_releases` 的长度。`sources.github.count` 仍只统计
new / active / G6 仓库，release 的入选数看 `releases.starred` 与 `g6_releases`。

## `fulltext`

```text
fulltext --config PATH [--fixtures DIR] (--doi DOI | --arxiv ID | --title TITLE) [--out PATH]
```

给定 DOI、arXiv ID 或标题，按固定顺序找 OA 全文并抽取方法/结果/局限段落：

1. Europe PMC `fullTextXML`（先用 DOI 查 PMC id，再取 OA XML）；
2. arXiv HTML（`arxiv.org/html/<id>`），失败或没有可用章节时再试 arXiv PDF；
3. DOI 属于 bioRxiv/medRxiv（`10.1101/`）或 Research Square（`10.21203/`）时
   试对应预印本 PDF；
4. Unpaywall 的 `best_oa_location` / `oa_locations`（需要
   `fulltext.unpaywall.email`；留空时完全跳过这一步，不记为失败）。

`--title` 是可选的补充输入，用来提高今日必读的全文覆盖率，不改变输出 key：

- 无论是否给出 `--title`，DOI 形如 `10.48550/arXiv.<id>` 时都直接映射到 arXiv ID，
  无需额外请求；
- 给出 `--title` 时，先用标题对 arXiv API 做精确匹配（`ti:"<title>"`），再按
  标题查 Europe PMC 的 `TITLE:"<title>"`；只有规范化后标题完全一致的记录才会被
  接受，近似标题会被忽略。由此得到的 arXiv ID / 预印本 DOI（bioRxiv、medRxiv、
  Research Square、arXiv DOI）会在 arXiv 与 Unpaywall 之间尝试，因此期刊 DOI
  也能找到对应的预印本全文。匹配失败只是少一条候选路径，不新增 `attempts`，
  也不影响 `no_oa` 的退出码 0。

`--fixtures DIR` 下按 `<source>/...` 读取录制响应：
`europepmc/doi-search.json` + `europepmc/fulltext.xml`、`arxiv/fulltext.html` 或
`arxiv/fulltext.pdf`、`biorxiv|medrxiv|researchsquare/fulltext.pdf`、
`unpaywall/location.json` + `unpaywall/fulltext.pdf|html`。fixture 模式下绝不联网。

输出 JSON 含 `status`（`oa` / `no_oa`）、`oa`、`source`、`format`、`doi`、
`arxiv_id`、`url`、`length`、`methods`、`results`、`limitations`、`reason` 与
`attempts`。`attempts` 按来源记录：同一来源内部的 HTML→PDF 回退或多条 OA 候选只
产生一条记录；`no_oa` 的 `reason` 汇总各来源的 miss 原因。找不到全文时退出码仍为
0，日报据此标注“无 OA 全文，仅基于摘要”。只有配置/参数错误（2）或输出写入失败
（1）才非零退出。

`fulltext` 是单篇命令；`collect` 不调用它。日报写入阶段只对“今日必读”top 3 逐篇
调用，并传入候选的 `title`，让预印本版本匹配生效；`quick_scan` 只使用候选池摘要，
不再调用全文。`--title` 可由已有 `--doi` / `--arxiv` 补充，也可以单独给出（例如
候选只有标题时）。

`length` 是三个段落数组的总字符数；方法、结果、局限分别最多 4/3/4 段，并按
4000/3000/2000 字符截断，截断点优先落在窗口后半段的句号处；句号不合适时退回词边界。PDF 用
PyMuPDF（AGPL-3.0，仅本机自用），HTML 用 beautifulsoup4 + lxml。

## `digest check`

```text
digest check --candidates PATH --selection PATH --digest PATH
```

写作阶段由会话模型读 `candidates.json`，写出 `selection.json` 与 `digest.md`；
`digest check` 只读这三个文件，拒绝结构或配额不合格的结果。它不读配置、不联网、
不访问状态库，也不需要 secrets，因此可以在 `push` 之前独立运行。

退出码：`0` 合格；`1` 内容不合格、JSON/Markdown 无法解析或文件不可读；`2` 缺参数
或参数非法。第一条违规写到 stderr，前缀是 `[fail] selection: …`、
`[fail] digest: …` 或（候选池本身损坏时）`[fail] candidates: …`。

**`selection.json`**（模型写，`digest check` 读）：

```json
{
  "schema_version": 1,
  "date": "2026-10-22",
  "timezone": "Asia/Shanghai",
  "papers": [
    {
      "id": "doi:10.1000/digest-g1-1",
      "group": "G1",
      "section": "must_read",
      "reason": "一句入选理由",
      "fulltext": "oa",
      "limitations_source": ["author", "model"]
    }
  ]
}
```

- `section`：`must_read` / `quick_scan`；`fulltext`：`oa` / `abstract_only`。
- `quick_scan` 只能是 `abstract_only`；`must_read` 的 `limitations_source` 必须含
  `model`，且整个列表是 `author` / `model` 的非空子集。
- `id` 必须存在于 `candidates.papers`，`group` 必须与候选一致；同一 id 不能重复。
- 目标数量：`must_read = min(3, n)`、`quick_scan = min(7, n - 实际 must_read)`，
  总数 `min(10, n)`，不补空。G2 最多 4 篇；除 G2/G6 外，候选池里出现的每个组至少
  要有一篇入选。G6 论文最多 1 篇且只能进 `quick_scan`，所以当候选池里少于 3 篇
  非 G6 论文时，`must_read` 允许少于 `min(3, n)`。G2 的 4 篇上限或 G6 的 1 篇
  上限导致无法达到 `quick_scan` 目标时，也允许少于目标；除此之外必须补齐。
- GitHub/G6 的选择不写进 `selection.json`：它们由 `candidates.json` 的 `github.*`
  决定，模型原样写进日报。

**`digest.md`** 的固定结构：

```markdown
# 学术速递 · 2026-10-22
> 关键词：… ｜ 新论文 N 篇，精选 M 篇 ｜ GitHub K 个

## 今日必读
### 1. <标题>
- 标签：`tag1` `tag2`
- 摘要：3–5 句
- 局限性：1–3 条
- 方法精读：2–4 句
- [原文](url) · [PDF](oa_url)

## 其它速览
- **<标题>** — `tag1` `tag2` · 摘要：1–2 句 · 局限性：1 句 · [链接](url)

## GitHub
### 新项目
- **owner/repo** ⭐ N · 语言 · 最近更新 · 定位 · why · [链接](url)
### 活跃项目
- …
### 关注项目的新 release
- **owner/repo vX.Y** · 日期 · 更新要点 · [链接](url)

## AI 工具 / Agent Harness
- **owner/repo vX.Y**（官方 release，日期）· 更新要点 · [链接](url)
- **owner/repo** ⭐ N · 语言 · 最近更新 · 定位 · why · [链接](url)

---
来源：pubmed ok (2) ｜ europepmc failed (…)
候选：30 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00
```

`digest check` 的校验要点：

- 标题日期与 `candidates.date` 一致；`来源：` 覆盖 `candidates.sources` 的每个源与
  状态，且源名/状态必须出现在 `来源：` 到 `候选：` 之间；`候选：N` 等于
  `candidate_count`，`入选：M` 等于 selection 的论文数，`生成：` 是可解析的
  ISO8601 时间；页脚不得出现 `sctp` / `SendKey` / `GITHUB_TOKEN` /
  `Authorization` 等密钥模式。
- 今日必读每条必须有 `- 标签：`、`- 摘要：`、`- 局限性：`、`- 方法精读：` 与
  `[原文]` 链接；其它速览每条一行，必须含 `摘要：`、`局限性：`、标签与链接。
- `fulltext: oa` 的今日必读，方法精读不得写“无 OA 全文，仅基于摘要”；`fulltext:
  abstract_only` 的今日必读必须写 `- 方法精读：无 OA 全文，仅基于摘要`。
- 日报里的论文标题必须与候选 `title` 逐字一致（不翻译），同一标题只出现一次；
  今日必读 / 其它速览的标题集合必须分别等于 selection 的两个分组。
- `## GitHub` 逐项包含 `candidates.github` 的 `new`、`active`、
  `releases.starred`，`## AI 工具 / Agent Harness` 包含 `g6` 与 `g6_releases`；
  为空时省略对应区块。`g6` 的条数受 `candidates.github.limits.g6`（默认 2）约束，
  `g6_releases` 每个官方库最多一条且不占这 2 条名额。每条 repo 必须写出
  owner/repo、stars、语言、最近更新（`pushed_at` 的本地日期）、定位、why 与链接；
  `language` 允许为空（GitHub 未识别语言时 `collect` 输出空串），此时语言一栏可写
  占位符。release 必须写出 repo+tag、日期、更新要点与链接。

`digest check` 不检查正文长度、32KB 拆分或 pending/未推送数；这些属于 `push`。

## `push`

```text
push --config PATH [--fixtures DIR] [--now ISO8601] \
     --candidates PATH --selection PATH --digest PATH \
     [--state-db PATH] [--dry-run] [--out PATH]
```

把校验过的日报推到微信（V1 只有 Server酱）。它先复用 `digest check` 的校验：
不合格时输出同样的 `[fail] selection:` / `[fail] digest:` 前缀并退出 1，不发送、
不写状态。`--candidates` / `--selection` / `--digest` 必填；`--state-db` 默认取
`paths.state_db`。

- `--dry-run`：只构建 payload。不联网、不读 SendKey、不打开状态库、不写
  `runs` / `pushes` / `pending`。payload 打到 stdout，或写到 `--out`（只能与
  `--dry-run` 一起用）：

  ```json
  {
    "schema_version": 1,
    "messages": [
      {"part": 1, "parts": 1, "title": "学术速递 · 2026-10-22", "desp": "…"}
    ]
  }
  ```

  空日报且 `push.send_empty: false` 时输出
  `{"schema_version":1,"messages":[],"skipped":"empty"}`。
- `--fixtures DIR`：回放 `DIR/serverchan/send-<n>.json`，第 n 次请求（跨本次运行的
  所有消息与重试计数）读第 n 个文件；文件缺失或内容不是 JSON 视为一次传输失败。
  fixture 模式不联网、不 sleep，也不读 SendKey。测试可在响应文件里加
  `"http_status": 500` 模拟非 2xx。
- `--now`：固定本次运行时间与 pending 年龄。

标题固定为 `学术速递 · <candidates.date>`，拆条时追加 `（1/n）`…`（n/n）`；按
Unicode 字符计数，超过 `push.title_max` 退出 2，不截断。`desp` 是 `digest.md`
去掉标题行后的全文（LF 换行）。正文超过 `push.split_bytes` 时只在顶层 `## ` 区块
边界拆分，每条不超过 `push.max_bytes`，最多 `push.max_messages` 条；单个 section
超过 `max_bytes`、或需要更多消息时退出 1，不发送部分日报，也绝不从论文中间截断。
没有可切分的顶层边界时（例如只有一个 section 且正文没有 `> 关键词…` 前言）按
“拆分不可能”退出 1（不发送部分日报，也不从论文中间截断）。
拆分后第 1 条带 `> 关键词…` 前言，最后一条带 `---` 页脚；本次运行还有未送达的
旧消息时，在最后一条页脚追加 `未推送数：P`（`--dry-run` 不追加）。

发送为 `POST` 表单 `title` + `desp`，成功条件是 HTTP 2xx 且响应 JSON 的 `code`
为整数 0。每条消息最多尝试 `1 + retries` 次，第 k 次失败后等待
`backoff_seconds × 2^(k-1)` 秒（fixture 模式不等待）。仍失败时把该条及之后未发送
的消息写入 `pending` 并退出 1；整份逻辑日报（含拆分后的所有消息）全部送达后才写
`pushes`。下次 live 运行先按配置时区、从 `created_at` 起算，丢弃超过
`pending_days` 个日历日的 pending 组（整组按 `digest_date` 删除），再按 `part`
顺序对最早的一组各重试一次；该组全部成功时按保存的 `items_json` 补写
`pushes`。pending 重试失败不阻塞当天的日报，但会写进 `runs.error`。

空日报（`selection.papers` 为空且 `candidates.github` 的 `new`/`active`/`g6`/
`releases.starred`/`g6_releases` 都为空）默认发送一条“今日没有匹配的检索条目”的
提示；`push.send_empty: false` 时不发 HTTP、不写 pending，记
`runs(status='skipped_empty')` 并退出 0；但若同一轮 pending 重试失败，则退出 1、
记 `runs(status='failed')`（pending 失败同时写进 `runs.error`）。空提示发送失败按
普通失败处理，但不写 `pending`。

退出码：`0` 已发送 / 空日报按配置发送或跳过 / dry-run 成功；`1` 日报校验失败、
重试后仍失败、拆分不可能、状态库打开或写入失败；`2` 参数或配置错误、缺少 SendKey。
成功时 stdout 一行 `[ok] push: sent N message(s), recorded M paper(s)`；空日报被跳过
且本轮没有补发 pending 时为 `[ok] push: skipped empty digest`（若同一轮补发了
pending，则仍是 sent 行）；失败写 stderr `[fail] push: …`。

SendKey 从 `push.sendkey_env`（默认 `SERVERCHAN_SENDKEY`）指向的环境变量读取，
为空时 live 退出 2。`sctp<uid>t…` 形式的 key 发到
`https://<uid>.push.ft07.com/send/<key>.send`，其余发到
`https://sctapi.ftqq.com/<key>.send`。key 与含 key 的 URL 不写 stdout、stderr、
状态库或日报；错误信息会先脱敏。真实测试推送需要人工确认本地 SendKey，自动化测试
只用 fixture。

## `doctor`

```text
doctor --config PATH [--fixtures DIR] [--now ISO8601] [--out PATH] [--state-db PATH]
```

检查配置字段、时区、每个 topic、期刊白名单、数据源、状态库与候选池路径。
`journal filter:` 行在空名单时显示 `unrestricted`，非空时列出启用的期刊名。

- `--fixtures DIR`：解析 `DIR/pubmed/esearch.xml` + `DIR/pubmed/efetch.xml`、
  `DIR/europepmc/search.json`、`DIR/arxiv/rss/<category>.xml`、
  `DIR/researchsquare/rss.xml`，启用时的 `DIR/biorxiv/details-0.json` /
  `DIR/medrxiv/details-0.json`，以及启用 GitHub 时的
  `DIR/github/search/{new,active}/<index>.json`、配置了 `github.user` 时的
  `DIR/github/starred.json`，以及每个要跟踪的 release feed
  `DIR/github/releases/<owner>__<repo>.json`（README 可选，位于
  `DIR/github/readme/<owner>__<repo>.md`）；缺文件或内容损坏时非零退出。
- 不带 `--fixtures`：向每个启用源各发一个轻量请求检查连通性（PubMed
  E-utilities、Europe PMC REST API、arXiv RSS、Research Square RSS、
  bioRxiv/medRxiv API、GitHub `/rate_limit`，并报告剩余 search 配额）。

坏配置会以非零退出，并在 stderr 指出具体字段，例如
`[fail] topics: must be a non-empty list`。

## 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 成功（含空日报按 `send_empty` 发送或跳过、`push --dry-run`） |
| `1` | 源、状态库、输出文件、自检、日报校验或推送失败 |
| `2` | 配置或参数错误、缺少 SendKey（尚未发起任何网络请求） |
