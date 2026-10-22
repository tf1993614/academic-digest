# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

当前实现到 **Issue 07：OA 全文能力**（在 Issue 01–05 的采集、去重、排序与 GitHub 发现骨架上，加入 Europe PMC / arXiv / bioRxiv / Research Square / Unpaywall 的 OA 全文定位与方法/结果/局限段落抽取）。后续的 Issue 06 GitHub release 跟踪、日报契约与 Server酱 推送按 `.scratch/academic-digest/issues/` 逐个补齐。

- 需求与契约：[spec.md](.scratch/academic-digest/spec.md)
- 最近实现：[07-oa-fulltext.md](.scratch/academic-digest/issues/07-oa-fulltext.md)（前序：[05-github-discovery.md](.scratch/academic-digest/issues/05-github-discovery.md)、[04-ranking-quota.md](.scratch/academic-digest/issues/04-ranking-quota.md)、[03-preprints.md](.scratch/academic-digest/issues/03-preprints.md)、[02-europepmc-dedup.md](.scratch/academic-digest/issues/02-europepmc-dedup.md)、[01-walking-skeleton.md](.scratch/academic-digest/issues/01-walking-skeleton.md)）
- 术语：[GLOSSARY.md](GLOSSARY.md)
- 已确认决定：[docs/decisions.md](docs/decisions.md)

## 快速开始（离线 fixture）

```bash
# 1. 自检配置与录制的 PubMed 响应，不联网
python3 scripts/doctor.py \
  --config tests/fixtures/walking/config.yaml \
  --fixtures tests/fixtures/walking

# 2. 采集候选池；--now 固定逻辑时钟，输出可复现
python3 scripts/collect.py \
  --config tests/fixtures/walking/config.yaml \
  --fixtures tests/fixtures/walking \
  --now 2026-10-22T08:00:00+08:00 \
  --out /tmp/candidates.json \
  --state-db /tmp/state.sqlite3

# 3. 抓取并解析一篇 OA 全文；同样只读 fixture，不联网
python3 scripts/fulltext.py \
  --config tests/fixtures/fulltext/config.yaml \
  --fixtures tests/fixtures/fulltext/epmc \
  --doi 10.1000/oa-epmc.1 \
  --out /tmp/fulltext.json

# 4. 跑测试（全部通过 CLI 子进程，离线、固定 --now）
python3 -m pytest
```

含 Europe PMC 的离线样例在 `tests/fixtures/multisource/`，把上面命令里的
`walking` 换成 `multisource` 即可。预印本样例在
`tests/fixtures/preprints/`（arXiv + Research Square，bioRxiv/medRxiv 默认关闭）
与 `tests/fixtures/preprint-dedupe/`（预印本与期刊版本同 DOI 合并）。排序与分组
配额的样例在 `tests/fixtures/ranking-quota/`（G2 刷屏的小候选池）、
`tests/fixtures/ranking-cap/`（34 条候选、默认 30 条上限）、
`tests/fixtures/ranking-freshness/`（新鲜度与同分排序）与
`tests/fixtures/ranking-default-quota/`（每组默认 6 条）。

GitHub 发现样例在 `tests/fixtures/github/`（只开启 GitHub，不含论文），运行时需要
一个非空的 `GITHUB_TOKEN`；fixture 模式不会真的请求 GitHub：

```bash
GITHUB_TOKEN=test python3 scripts/collect.py \
  --config tests/fixtures/github/config.yaml \
  --fixtures tests/fixtures/github \
  --now 2026-10-22T08:00:00+08:00 \
  --out /tmp/github.json \
  --state-db /tmp/github.sqlite3
```

OA 全文样例在 `tests/fixtures/fulltext/`：`epmc/`（EPMC OA XML）、
`arxiv-html/`、`arxiv-pdf/`、`biorxiv/`、`researchsquare/`（PDF）、
`unpaywall/`（定位 OA 版本）与 `no-oa/`（Unpaywall 明确无 OA）。

也可以使用模块入口：`python3 -m academic_digest collect ...`、
`python3 -m academic_digest fulltext ...` 与
`python3 -m academic_digest doctor ...`。

## 命令

### `collect`

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
（JSON 模式会静默丢掉摘要）。

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
  "url": "https://pubmed.ncbi.nlm.nih.gov/39000001/",
  "abstract": "…",
  "abstract_missing": false,
  "tags": ["aging", "senescence", "multi-omics"],
  "relevance": 7,
  "score": 7,
  "is_preprint": false,
  "oa_url": null
}
```

没有摘要的论文仍会进入候选池：`abstract` 为空、`abstract_missing` 为
`true`，`tags` 中带 `无摘要`。

### 排序与分组配额

`score` 是规则分，由两部分相加；`relevance` 单独保留相关性部分：

- **相关性**（`relevance`）：论文归入加权命中分最高的组；组内每个命中词，
  标题命中 +3、摘要命中 +1。
- **新鲜度**：发布日等于运行日（配置时区）当天 +2、前一天 +1，更早、更晚或
  日期缺失 +0。日期只精确到年份（例如 Europe PMC 的 `pubYear`）时按缺失处理：
  不加新鲜度分，并在同分时排在标了具体日期的论文之后。

候选池按 `score` 降序、`date` 降序、`id` 升序排列。同分同日时用 `id` 做稳定
tie-break，因此固定 fixture 与 `--now` 每次得到完全相同的顺序。

截断分两步，保证宽泛组不刷屏、窄组不会整天消失：

1. 先按各组最高分的全局顺序，为每个有候选的组保留一条；
2. 再按全局顺序填空位，但任何组都不超过配置的 `max_items`。

`max_items` 默认 6（示例配置里 G2 为 4），`pool.max_items`（默认 30）是总数上限；
两者都可按配置调整，候选不足时按实际数量输出，不补空条目。
`tags` 只列出实际命中的词（再追加 `预印本` / `无摘要` 标记），`group` 就是这些
词所属的组，所以每条候选都能解释自己为什么被选中。

期刊白名单加分尚未启用：当前配置没有 `journal_filter`，默认不限期刊；等给出名单
后再接入 PubMed/Europe PMC 的 `JOURNAL` 过滤并按白名单加分，见
[11-journal-whitelist.md](.scratch/academic-digest/issues/11-journal-whitelist.md)。

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

34 条查询各跑两遍 = 68 次搜索，按 2 秒间隔约 2–3 分钟。这会超过 spec 里
“采集 30–90 秒”的目标，是有意取舍：22+12 条查询与 30 次/分钟的认证限速决定了
请求数，整体运行仍在 2–4 分钟内。

G6 官方库（`anthropics/claude-code`、`openai/codex`、
`deepseek-ai/deepseek-harness`）的 release 跟踪在
[06-github-releases.md](.scratch/academic-digest/issues/06-github-releases.md)。活跃库
按 star 增量排序尚未实现，当前按上面的规则分排序。

### `fulltext`

```text
fulltext --config PATH [--fixtures DIR] (--doi DOI | --arxiv ID) [--out PATH]
```

给定 DOI 或 arXiv ID，按固定顺序找 OA 全文并抽取方法/结果/局限段落：

1. Europe PMC `fullTextXML`（先用 DOI 查 PMC id，再取 OA XML）；
2. arXiv HTML（`arxiv.org/html/<id>`），失败或没有可用章节时再试 arXiv PDF；
3. DOI 属于 bioRxiv/medRxiv（`10.1101/`）或 Research Square（`10.21203/`）时
   试对应预印本 PDF；
4. Unpaywall 的 `best_oa_location` / `oa_locations`（需要
   `fulltext.unpaywall.email`；留空时完全跳过这一步，不记为失败）。

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
调用（Issue 08）。本 ticket 的输入只有 DOI / arXiv ID；按标题匹配预印本版本与
DOI→arXiv 交叉检索留到日报契约阶段，当前只按 DOI 前缀匹配 bioRxiv/medRxiv/
Research Square 的预印本 PDF。

`length` 是三个段落数组的总字符数；方法、结果、局限分别最多 4/3/4 段，并按
4000/3000/2000 字符截断，截断点优先落在窗口后半段的句号处；句号不合适时退回词边界。PDF 用
PyMuPDF（AGPL-3.0，仅本机自用），HTML 用 beautifulsoup4 + lxml。

### `doctor`

```text
doctor --config PATH [--fixtures DIR] [--now ISO8601] [--out PATH] [--state-db PATH]
```

检查配置字段、时区、每个 topic、数据源、状态库与候选池路径：

- `--fixtures DIR`：解析 `DIR/pubmed/esearch.xml` + `DIR/pubmed/efetch.xml`、
  `DIR/europepmc/search.json`、`DIR/arxiv/rss/<category>.xml`、
  `DIR/researchsquare/rss.xml`，启用时的 `DIR/biorxiv/details-0.json` /
  `DIR/medrxiv/details-0.json`，以及启用 GitHub 时的
  `DIR/github/search/{new,active}/<index>.json`（README 可选，位于
  `DIR/github/readme/<owner>__<repo>.md`）；缺文件或内容损坏时非零退出。
- 不带 `--fixtures`：向每个启用源各发一个轻量请求检查连通性（PubMed
  E-utilities、Europe PMC REST API、arXiv RSS、Research Square RSS、
  bioRxiv/medRxiv API、GitHub `/rate_limit`，并报告剩余 search 配额）。

坏配置会以非零退出，并在 stderr 指出具体字段，例如
`[fail] topics: must be a non-empty list`。

### 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 源、状态库、输出文件或自检失败 |
| `2` | 配置或参数错误（尚未发起任何网络请求） |

## 配置

从 [`config.example.yaml`](config.example.yaml) 复制一份到仓库根的
`config.yaml`（已被 gitignore），再按需增删关键词组。

关键字段：

- `timezone`：IANA 时区，例如 `Asia/Shanghai`。
- `lookback.<source>`：每个启用源的回看天数，正整数；启用某源时必须给出对应的
  `lookback`。启用 `arxiv` 时 `lookback.arxiv` 至少 4 天，否则配置校验失败。
- `topics`：非空列表；每项含 `name`、`label`、`terms`、可选 `exclude`、
  `max_items`。`name` 唯一，`terms` 非空。`max_items` 是该组在候选池里的席位
  上限（例如 G2 为 4）；每个有候选的组仍至少保留其最高分的一条。
- `sources`：数据源开关；支持 `pubmed`、`europepmc`、`arxiv`、
  `researchsquare`、`biorxiv`、`medrxiv`、`github`。必须显式写出 `sources.pubmed`
  （可设 true/false），且至少要启用一个源；未写出的源视为关闭，
  因此 bioRxiv/medRxiv 默认关闭。GitHub 不需要 `lookback`，它用自己的
  `github.new.days` / `github.active.days`。
- `arxiv.categories`：启用 arXiv 时必填的非空分类列表（例如 `cs.LG`、
  `q-bio.QM`），每个分类读一个 RSS；不启用时可省略。
- `github.token_env`：读取 GitHub token 的环境变量名，默认 `GITHUB_TOKEN`；
  启用 `sources.github` 时必须能读到非空值，否则配置校验失败。token 不写入
  Prompt、日志或候选池。
- `github.queries`：组名到检索词的映射，默认是 22 条 G1–G5 发现查询，只保留配置
  里实际存在的组。`github.g6_queries` 是 G6 区块的 12 条生态查询，
  `github.g6_topic` 指定它们归入哪个组（默认 `G6`；没有该组时省略默认 G6 查询）。
- `github.new` / `github.active`：各含 `days`、`min_stars` 与 `max_items`（默认
  7 天 / 5 星 / 1 条，以及 7 天 / 30 星 / 2 条）；`github.g6.max_items` 默认 2。
- `github.readme_limit`：每次最多读多少个 README，默认 20；按 new / active / G6
  三个区块轮流分配，每个区块先取自己最好的 `max_items + 3` 个候选。
- `fulltext.unpaywall.email`：Unpaywall API 要求的联系邮箱；可留空。留空时
  `fulltext` 跳过 Unpaywall，仍会尝试 Europe PMC、arXiv 与预印本 PDF。邮箱只作为
  请求参数与 User-Agent 的一部分，不写入日报或日志。
- `pool.max_items`：候选池总数上限，默认 30，必须不少于 `topics` 数量
  （保证每个非空组至少 1 条）；候选不足时不补空条目。
- `paths.state_db` / `paths.candidates`：相对路径按配置文件所在目录解析。

配置校验在创建状态库、发起请求之前完成；未知字段会直接报错，避免拼写错误
被静默忽略。

## 测试 fixture 布局

```text
tests/fixtures/
├── walking/                 # 两篇论文：G1 与 G2
│   ├── config.yaml
│   └── pubmed/
│       ├── esearch.xml
│       └── efetch.xml
├── no-abstract/             # 一篇没有摘要的论文
│   ├── config.yaml
│   └── pubmed/
│       ├── esearch.xml
│       └── efetch.xml
├── multisource/             # PubMed + Europe PMC：重复 DOI/PMID、预印本、EPMC-only
│   ├── config.yaml
│   ├── pubmed/
│   │   ├── esearch.xml
│   │   └── efetch.xml
│   └── europepmc/
│       └── search.json
├── epmc-abstract/           # PubMed 缺摘要，由 EPMC 补上
│   ├── config.yaml
│   ├── pubmed/
│   │   ├── esearch.xml
│   │   └── efetch.xml
│   └── europepmc/
│       └── search.json
├── preprint-merge/          # PubMed 预印本与 EPMC PPR 共用同一 DOI
│   ├── config.yaml
│   ├── pubmed/
│   │   ├── esearch.xml
│   │   └── efetch.xml
│   └── europepmc/
│       └── search.json
├── preprints/               # arXiv RSS（new/replace/cross/过期）+ RS RSS
│   ├── config.yaml          # + 默认关闭的 bioRxiv/medRxiv 录制响应
│   ├── arxiv/rss/cs.LG.xml
│   ├── arxiv/query.atom
│   ├── researchsquare/rss.xml
│   ├── biorxiv/details-0.json
│   └── medrxiv/details-0.json
├── preprint-dedupe/         # RS/bioRxiv 与 EPMC 同 DOI：只保留一条
│   ├── config.yaml
│   ├── europepmc/search.json
│   ├── researchsquare/rss.xml
│   └── biorxiv/details-0.json
├── preprint-no-abstract/    # 预印本缺摘要：同时带“预印本”与“无摘要”
│   ├── config.yaml
│   ├── arxiv/rss/cs.LG.xml
│   └── arxiv/query.atom
├── ranking-quota/           # G2 刷屏的小候选池：G2 只留 4 条，G1 保留 1 条
│   ├── config.yaml          # Europe PMC only，pool.max_items: 6
│   └── europepmc/search.json
├── ranking-cap/             # 34 条候选：默认 30 条上限 + 每组配额
│   ├── config.yaml          # Europe PMC only，未写 pool（默认 30）
│   └── europepmc/search.json
├── ranking-freshness/       # 新鲜度 +2/+1/+0、摘要命中 +1 与同分排序
│   ├── config.yaml
│   └── europepmc/search.json
├── ranking-default-quota/   # 未写 max_items：默认每组 6 条
│   ├── config.yaml
│   └── europepmc/search.json
├── github/                  # GitHub 新库/活跃库/G6：录制搜索响应 + 可选 README
│   ├── config.yaml          # 仅 GitHub；2 条发现查询 + 2 条 G6 查询
│   ├── github/search/new/0.json … 3.json
│   ├── github/search/active/0.json … 3.json
│   └── github/readme/acme__cell-atlas.md
├── fulltext/                # OA 全文：五种来源 + no_oa
│   ├── config.yaml          # 共享配置；fixture 目录按场景分开
│   ├── config-no-email.yaml # 未配置 Unpaywall：不产生该来源的 attempt
│   ├── epmc/europepmc/
│   │   ├── doi-search.json
│   │   └── fulltext.xml
│   ├── arxiv-html/arxiv/fulltext.html
│   ├── arxiv-pdf/arxiv/fulltext.pdf
│   ├── biorxiv/biorxiv/fulltext.pdf
│   ├── medrxiv/medrxiv/fulltext.pdf
│   ├── researchsquare/researchsquare/fulltext.pdf
│   ├── unpaywall/unpaywall/
│   │   ├── location.json
│   │   └── fulltext.pdf
│   ├── unpaywall-html/unpaywall/
│   │   ├── location.json
│   │   └── fulltext.html
│   ├── truncation/europepmc/  # 段落数上限（4/3/4）
│   │   ├── doi-search.json
│   │   └── fulltext.xml
│   ├── truncation-chars/europepmc/  # 4000/3000/2000 字符句号截断
│   │   ├── doi-search.json
│   │   └── fulltext.xml
│   └── no-oa/
│       ├── europepmc/doi-search.json
│       └── unpaywall/location.json
└── configs/                 # 坏配置
    ├── arxiv-lookback.yaml       # lookback.arxiv < 4
    ├── arxiv-no-categories.yaml  # 启用 arxiv 但缺分类
    ├── bad-topics.yaml
    ├── bad-unpaywall-email.yaml  # fulltext.unpaywall.email 不是邮箱
    ├── broken.yaml
    ├── empty-terms.yaml
    ├── no-pubmed.yaml
    └── pool-too-small.yaml        # pool.max_items < topics 数量
```

后续源沿用同一约定：`<fixtures>/<source>/<recorded-response>`。

## 状态库

SQLite 位于 `paths.state_db`（默认 `state/academic-digest.sqlite3`）：

- `papers`：以候选 `id` 为主键，记录 DOI/PMID、标题、来源、分组与
  `first_seen` / `last_seen`。同一论文重跑只更新 `last_seen`，不会插入重复行。
- `pushes`：成功推送的条目，主键为 `(item_id, topic, channel, digest_date)`。
  `collect` 在排名与截断之前用它排除已推送条目；同一篇论文后续换用另一种
  标识（例如从 PMID 变成 DOI，或从标题哈希变成 DOI）也能匹配。
- `runs`：每次 `collect` 一行，记录起止时间、状态、各源结果、候选数与错误摘要。

## 开发

一次跑完全部检查（mypy、pyflakes、pytest）：

```bash
scripts/check.sh
```

启用本地 pre-commit hook，每个 clone 执行一次：

```bash
git config core.hooksPath .githooks
```

之后每次 `git commit` 都会跑同一个脚本；`.github/workflows/ci.yml` 在推送时跑同一份检查。

审查前先把工作树冻结成补丁，避免 reviewer 在变动中的 diff 上反复重读：

```bash
scripts/review-patch.sh   # -> out/review/current.diff 等
```

规则见 `docs/agents/code-review.md`，审查侧的判断标准见 `CODING_STANDARDS.md`。

唯一的测试 seam 是 CLI：测试用 `subprocess` 运行 `collect` / `fulltext` /
`doctor`，断言退出码、stderr 与输出文件，不导入内部实现。所有测试离线且固定
`--now`。

`push` 命令（Issue 09）落地前，“已推送”状态由测试直接向 SQLite `pushes`
表写入一行作为前置数据；断言仍只来自 CLI 输出，不导入内部实现。
