# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

当前实现的是 **Issue 01：走通骨架**（配置 + 状态 + PubMed → 候选池）。后续的 Europe PMC、预印本、排序配额、GitHub、OA 全文、日报契约与 Server酱 推送按 `.scratch/academic-digest/issues/` 逐个补齐。

- 需求与契约：[spec.md](.scratch/academic-digest/spec.md)
- 本 issue：[01-walking-skeleton.md](.scratch/academic-digest/issues/01-walking-skeleton.md)
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

离开 `--fixtures` 时通过 PubMed E-utilities 的 `esearch` + `efetch` 抓取；
摘要只从 XML 解析（JSON 模式会静默丢掉摘要）。

`collect` 的 JSON 顶层包含 `schema_version`、`generated_at`、`date`、
`timezone`、`lookback_days`、`sources`、`candidate_count` 和 `papers`。
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

### `doctor`

```text
doctor --config PATH [--fixtures DIR] [--now ISO8601] [--out PATH] [--state-db PATH]
```

检查配置字段、时区、每个 topic、数据源、状态库与候选池路径：

- `--fixtures DIR`：解析 `DIR/pubmed/esearch.xml` 与 `DIR/pubmed/efetch.xml`；
  缺文件或 XML 损坏时非零退出。
- 不带 `--fixtures`：向 PubMed E-utilities 发一个轻量请求检查连通性。

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
- `lookback.<source>`：每个源的回看天数，正整数。
- `topics`：非空列表；每项含 `name`、`label`、`terms`、可选 `exclude`、
  `max_items`。`name` 唯一，`terms` 非空。
- `sources`：数据源开关；当前支持 `pubmed`。
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
└── configs/                 # 坏配置
    ├── bad-topics.yaml
    └── broken.yaml
```

后续源沿用同一约定：`<fixtures>/<source>/<recorded-response>`。

## 状态库

SQLite 位于 `paths.state_db`（默认 `state/academic-digest.sqlite3`）：

- `papers`：以候选 `id` 为主键，记录 DOI/PMID、标题、来源、分组与
  `first_seen` / `last_seen`。同一论文重跑只更新 `last_seen`，不会插入重复行。
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
