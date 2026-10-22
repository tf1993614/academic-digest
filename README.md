# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

当前实现到 **Issue 04：相关性排序 + 分组配额 + top 30 候选池**（在 Issue 01/02/03 的采集骨架上，把候选池从骨架排序换成完整的规则打分、分组配额与总上限）。后续的 GitHub、OA 全文、日报契约与 Server酱 推送按 `.scratch/academic-digest/issues/` 逐个补齐。

- 需求与契约：[spec.md](.scratch/academic-digest/spec.md)
- 最近实现：[04-ranking-quota.md](.scratch/academic-digest/issues/04-ranking-quota.md)（前序：[03-preprints.md](.scratch/academic-digest/issues/03-preprints.md)、[02-europepmc-dedup.md](.scratch/academic-digest/issues/02-europepmc-dedup.md)、[01-walking-skeleton.md](.scratch/academic-digest/issues/01-walking-skeleton.md)）
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

# 3. 跑测试（全部通过 CLI 子进程，离线、固定 --now）
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

也可以使用模块入口：`python3 -m academic_digest collect ...` 与
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
`timezone`、`lookback_days`、`sources`、`candidate_count` 和 `papers`。
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

### `doctor`

```text
doctor --config PATH [--fixtures DIR] [--now ISO8601] [--out PATH] [--state-db PATH]
```

检查配置字段、时区、每个 topic、数据源、状态库与候选池路径：

- `--fixtures DIR`：解析 `DIR/pubmed/esearch.xml` + `DIR/pubmed/efetch.xml`、
  `DIR/europepmc/search.json`、`DIR/arxiv/rss/<category>.xml`、
  `DIR/researchsquare/rss.xml`，以及启用时的 `DIR/biorxiv/details-0.json` /
  `DIR/medrxiv/details-0.json`；缺文件或内容损坏时非零退出。
- 不带 `--fixtures`：向每个启用源各发一个轻量请求检查连通性（PubMed
  E-utilities、Europe PMC REST API、arXiv RSS、Research Square RSS、
  bioRxiv/medRxiv API）。

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
  `researchsquare`、`biorxiv`、`medrxiv`。必须显式写出 `sources.pubmed`
  （可设 true/false），且至少要启用一个源；未写出的源视为关闭，
  因此 bioRxiv/medRxiv 默认关闭。
- `arxiv.categories`：启用 arXiv 时必填的非空分类列表（例如 `cs.LG`、
  `q-bio.QM`），每个分类读一个 RSS；不启用时可省略。
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
└── configs/                 # 坏配置
    ├── arxiv-lookback.yaml       # lookback.arxiv < 4
    ├── arxiv-no-categories.yaml  # 启用 arxiv 但缺分类
    ├── bad-topics.yaml
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

唯一的测试 seam 是 CLI：测试用 `subprocess` 运行 `collect` / `doctor`，
断言退出码、stderr 与输出文件，不导入内部实现。所有测试离线且固定
`--now`。

`push` 命令（Issue 09）落地前，“已推送”状态由测试直接向 SQLite `pushes`
表写入一行作为前置数据；断言仍只来自 CLI 输出，不导入内部实现。
