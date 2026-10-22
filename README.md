# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

当前实现到 **Issue 02：Europe PMC + 跨源/跨天去重**（在 Issue 01 的配置 + 状态 + PubMed 骨架上，加入 Europe PMC、跨源合并与已推送排除）。后续的预印本源、排序配额、GitHub、OA 全文、日报契约与 Server酱 推送按 `.scratch/academic-digest/issues/` 逐个补齐。

- 需求与契约：[spec.md](.scratch/academic-digest/spec.md)
- 最近实现：[02-europepmc-dedup.md](.scratch/academic-digest/issues/02-europepmc-dedup.md)（骨架见 [01-walking-skeleton.md](.scratch/academic-digest/issues/01-walking-skeleton.md)）
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
`walking` 换成 `multisource` 即可。

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

离开 `--fixtures` 时通过 PubMed E-utilities 的 `esearch` + `efetch` 以及
Europe PMC 的 `search`（`resultType=core`）抓取。PubMed 摘要只从 XML 解析
（JSON 模式会静默丢掉摘要）。

跨源去重按 DOI > PMID > arXiv ID 匹配：任一强标识相同就合并为一条，
PubMed 的摘要与期刊优先，其余字段只补空；没有强标识时才退回“标题 + 年份”
哈希。Europe PMC 的预印本保留 `is_preprint: true` 与 `source: europepmc`。
状态库 `pushes` 表里的条目不会再进入候选池（跨天去重）。

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
  "tags": ["aging", "multi-omics"],
  "score": 7,
  "is_preprint": false,
  "oa_url": null
}
```

没有摘要的论文仍会进入候选池：`abstract` 为空、`abstract_missing` 为
`true`，`tags` 末尾带 `无摘要`。

`score` 与排序目前是骨架级规则（标题命中权重高于摘要，日期与 id 做稳定
tie-break）；Issue 04 会替换为完整的相关性排序与分组配额。

### `doctor`

```text
doctor --config PATH [--fixtures DIR] [--now ISO8601] [--out PATH] [--state-db PATH]
```

检查配置字段、时区、每个 topic、数据源、状态库与候选池路径：

- `--fixtures DIR`：解析 `DIR/pubmed/esearch.xml` + `DIR/pubmed/efetch.xml`
  与 `DIR/europepmc/search.json`；缺文件或内容损坏时非零退出。
- 不带 `--fixtures`：向每个启用源各发一个轻量请求检查连通性（PubMed
  E-utilities、Europe PMC REST API）。

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
  `lookback`。
- `topics`：非空列表；每项含 `name`、`label`、`terms`、可选 `exclude`、
  `max_items`。`name` 唯一，`terms` 非空。`max_items` 在当前骨架中只做校验与
  doctor 展示，分组配额在 Issue 04 才真正生效。
- `sources`：数据源开关；当前支持 `pubmed` 与 `europepmc`，至少要启用一个。
- `pool.max_items`：候选池上限，默认 30。
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
└── configs/                 # 坏配置
    ├── bad-topics.yaml
    ├── broken.yaml
    └── empty-terms.yaml
```

后续源沿用同一约定：`<fixtures>/<source>/<recorded-response>`。

## 状态库

SQLite 位于 `paths.state_db`（默认 `state/academic-digest.sqlite3`）：

- `papers`：以候选 `id` 为主键，记录 DOI/PMID、标题、来源、分组与
  `first_seen` / `last_seen`。同一论文重跑只更新 `last_seen`，不会插入重复行。
- `pushes`：成功推送的条目，主键为 `(item_id, topic, channel, digest_date)`。
  `collect` 在排名与截断之前用它排除已推送条目；同一篇论文后续换用另一种
  标识（例如从 PMID 变成 DOI）也能通过 `papers` 行展开匹配。
- `runs`：每次 `collect` 一行，记录起止时间、状态、各源结果、候选数与错误摘要。

## 开发

```bash
python3 -m pytest
python3 -m pyflakes academic_digest scripts tests
python3 -m mypy academic_digest
```

唯一的测试 seam 是 CLI：测试用 `subprocess` 运行 `collect` / `doctor`，
断言退出码、stderr 与输出文件，不导入内部实现。所有测试离线且固定
`--now`。
