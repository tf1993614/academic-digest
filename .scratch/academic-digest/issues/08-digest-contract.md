# 08: 日报与 selection 契约：3+7、四要素、digest check

**What to build:** 模型从 30 条候选池选出 3 篇今日必读 + 7 篇其它速览，写成含四要素的中文日报；selection 校验配额与 id；`digest check` 能拒绝结构不合格的日报。

**Blocked by:** 04, 05, 06, 07.

**Status:** done

- [x] 给定 fixture 候选池，产出 3 篇今日必读 + 7 篇其它速览，每条含标题、标签、摘要、局限性。
- [x] 今日必读 top 3 含方法精读，或明确“无 OA 全文，仅基于摘要”。
- [x] 今日必读 top 3 调用 `fulltext`；除 DOI 前缀匹配外，按标题/DOI 匹配预印本版本（含 DOI→arXiv 交叉检索），以提高全文覆盖率。
- [x] selection 校验：id 存在、G2 ≤4、非空组 ≥1；不合格时失败并指出原因。
- [x] GitHub 区块含 3 种模式；G6 独立区块 1–2 条，不占 3+7。
- [x] 页脚含各源状态、候选/入选计数；不含密钥。
- [x] `digest check` 对合格/不合格 fixture 给出正确退出码与错误；测试离线。

## Contract

### 新增/变更的 key

**`selection.json`**（模型写，`digest check` 读）

```json
{
  "schema_version": 1,
  "date": "2026-10-22",
  "timezone": "Asia/Shanghai",
  "papers": [
    {
      "id": "doi:10.1000/example",
      "group": "G2",
      "section": "must_read",
      "reason": "一句入选理由",
      "fulltext": "oa",
      "limitations_source": ["author", "model"]
    }
  ]
}
```

- `section`：`must_read` / `quick_scan`。
- `fulltext`：`oa` / `abstract_only`；`quick_scan` 只能是 `abstract_only`。
- `limitations_source`：`author` / `model` 的非空子集；`must_read` 必须含 `model`。
- 写作流程只对 `must_read` 调用 `fulltext`；`quick_scan` 只用候选池摘要。
- 不记录 GitHub/G6 选择：它们由 `candidates.json` 的 `github.*` 决定，模型按原样写进日报。

**`digest.md`**（模型写，`digest check` 读）

固定结构（字段标签逐字匹配，供 `digest check` 解析）：

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
- **owner/repo** ⭐ N · 语言 · 最近更新 · 定位 · why · [链接]
### 活跃项目
- …
### 关注项目的新 release
- **owner/repo vX.Y** · 日期 · 更新要点 · [链接]

## AI 工具 / Agent Harness
- **owner/repo vX.Y**（官方 release，日期）· 更新要点 · [链接]
- **owner/repo** ⭐ N · 语言 · 最近更新 · 定位 · why · [链接]

---
来源：pubmed ok (2) ｜ europepmc failed (…)
候选：30 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00
```

- 今日必读每条必须有 `- 标签：`、`- 摘要：`、`- 局限性：`、`- 方法精读：`；无 OA 全文时写 `- 方法精读：无 OA 全文，仅基于摘要`。
- 其它速览每条一行，必须含 `摘要：`、`局限性：`、链接。
- `## GitHub` 放 `new`、`active`、`releases.starred`；`## AI 工具 / Agent Harness` 放 `g6` 与 `g6_releases`。`g6` 受 `github.g6.max_items`（默认 2）约束；`g6_releases` 每个官方库最多一条，不占这 2 条名额。每条含 owner/repo、stars、语言、最近更新、定位、why、链接；release 含 repo+tag、日期、更新要点、链接。
- 页脚必须有 `来源：`、`候选：N`、`入选：M`、`生成：`；不含 secrets。

**`digest check` CLI**

```text
digest check --candidates PATH --selection PATH --digest PATH
```

- 0：合格；1：内容不合格或文件不可读；2：缺参数/参数非法。
- 错误写 stderr：`[fail] selection: …` / `[fail] digest: …`，指出第一条违规。
- 不联网、不读状态库、不需要 config/secrets。

### 实现补充

- G6 论文只能进 `quick_scan`，所以 `must_read` 的目标 `min(3, n)` 以“可移动进
  `must_read` 的非 G6 候选数”为实际上限；如果所有非 G6 候选都已在 `must_read`，
  不能短缺，把非 G6 论文全塞进 `quick_scan` 仍判不合格。`quick_scan` 目标按实际
  `must_read` 数计算（`min(7, n - 实际 must_read)`）；G2 的 4 篇上限或 G6 的 1 篇
  上限导致无法达到目标时允许更短，其他短缺不合格。
- 候选池本身不可读、JSON 损坏或结构不符合 `candidates.json` 契约时，`digest check`
  额外用 `[fail] candidates: …` 报告并退出 1；selection/digest 内容违规仍分别用
  `[fail] selection:` / `[fail] digest:`。
- DOI 形如 `10.48550/arXiv.<id>` 时，无论是否给出 `--title`，`fulltext` 都按 DOI
  前缀直接映射到 arXiv ID；`--title` 负责额外的标题精确匹配与预印本版本发现。
  输出 key 不变。

### 旧 key 不能变

- `candidates.json` 的 `schema_version`、`generated_at`、`date`、`timezone`、`lookback_days`、`sources`、`candidate_count`、`papers`、`github`（`passes`/`limits`/`found`/`new`/`active`/`g6`/`releases`/`g6_releases`）原样读取，不改含义/形状。
- `fulltext` 输出的 `status`/`oa`/`source`/`format`/`doi`/`arxiv_id`/`url`/`length`/`methods`/`results`/`limitations`/`reason`/`attempts` 不变；新增可选的 `--title` 输入用于按标题匹配预印本版本与 DOI→arXiv 交叉检索，不改输出 key。
- 不新增 config key；`selection`/`digest` 路径由 CLI 参数给出（Issue 09 的 `push` 复用）。

### 空/缺省行为

- 候选 `papers` 为 `n` 篇时：目标 `must_read = min(3, n)`，`quick_scan = min(7, n - must_read)`，总数 `min(10, n)`，不补空；G2 配额（≤4）优先，配额导致无法达到目标时允许少于目标。
- `n = 0` 且 `github` 为空：允许空日报（标题 + 页脚），`digest check` 退出 0；是否发送由 Issue 09 的 `send_empty` 决定。
- 某个 GitHub 子区块为空：日报省略该子区块；`github.g6` 与 `github.g6_releases` 都为空时省略 G6 区块。
- 源失败：`sources.<name>.status = failed` 原样进页脚，不伪造该源条目。
- 无 OA 全文：保留今日必读，写 `无 OA 全文，仅基于摘要`，不替换论文。
- 不合格 selection：`digest check` 退出 1，不自动修复。

### 校验规则

- `selection.date`/`timezone` 与 `candidates.json` 一致；`schema_version` 为 1；`reason` 非空。
- 日报标题 `# 学术速递 · <date>` 的日期与 `candidates.date` 一致；页脚 `生成：` 是 ISO8601 时间。
- `id` 必须存在于 `candidates.papers`，`group` 与候选一致；不得重复。
- `must_read` / `quick_scan` 数量符合上面的目标；G2 配额导致不足时允许 `quick_scan` 少于目标，但不得补空/重复。`must_read` 每条 `fulltext` 为 `oa` 或 `abstract_only`，且与日报的方法精读/“无 OA 全文”标记一致；`quick_scan` 只能 `abstract_only`；`must_read` 的 `limitations_source` 含 `model`。
- G2 入选 ≤ 4；除 G2/G6 外，每个在候选池出现的组在 selection 至少 1 篇；G6 论文最多 1 篇且只能进 `quick_scan`（不强制）。
- 日报中每篇论文标题与候选 `title` 一致（不翻译），且每个候选标题只出现一次。
- GitHub/G6：日报逐项包含 `candidates.github` 的 `new`、`active`、`releases.starred`、`g6`、`g6_releases`（为空则省略对应子区块），不得增删。
- 页脚 `候选：N` = `candidate_count`，`入选：M` = selection 论文数；`来源：` 覆盖所有 `candidates.sources`；不含 `sctp`/`SendKey`/`GITHUB_TOKEN`/`Authorization` 等密钥模式。`未推送数`/pending 由 Issue 09 追加，本 issue 不要求、不校验。
- `digest check` 不检查正文长度/32KB 拆分（Issue 09）。

### 未配置时

- 没有 GitHub 数据（`github` 缺失或各列表为空）：日报省略 GitHub/G6 区块，`digest check` 不要求。
- 没有 OA 全文（`fulltext.status = no_oa` 或未调用）：今日必读写“无 OA 全文，仅基于摘要”，不阻塞。
- `digest check` 不依赖 config/网络/状态库；只读三个文件。

## Comments

- 2026-10-22：Issue 07 已提供 `fulltext` 单篇 CLI（DOI/arXiv ID 输入、
  `--fixtures` 离线、`no_oa` 不抛异常、不阻塞日报）。本 issue 接它时只对今日必读
  top 3 调用；Issue 07 明确把“按标题匹配预印本版本与 DOI→arXiv 交叉检索”留给本
  issue（见 07 的 comments 与 ADR amendment），需要在这里补上。
- 2026-10-22：按 `docs/agents/issue-tracker.md` 的新约定补 `## Contract`：固定
  `selection.json` / `digest.md` 的 key、旧 key 不变、空/缺省行为与 `digest check`
  的退出码/校验规则；GitHub/G6 由 `candidates.json` 驱动，不进入 selection。
  `must_read` 调用 `fulltext`，`quick_scan` 只用摘要；`--title` 是新增的可选
  `fulltext` 输入，输出 key 不变。实现时以 Contract 为准。

- 2026-10-22：已实现。新增 `academic_digest/digest.py` 与
  `digest check --candidates/--selection/--digest`（`scripts/digest.py` 为同一入口
  的包装），只读三个文件，不读配置、不联网、不访问状态库；合格退出 0，内容或
  可读性问题退出 1，参数问题仍由 argparse 退出 2。校验顺序为 candidates 结构 →
  selection（schema/日期/时区、id 与组存在性、section/fulltext/limitations_source、
  3 + 7 目标、G2 ≤ 4、G6 ≤ 1 且仅 quick_scan、非空组覆盖）→ digest（固定标题与
  `##` 区块、四要素字面标签、标题逐字且不重复、方法精读与 fulltext 标记一致、
  GitHub/G6 逐项对应且为空省略、页脚来源/计数/ISO 时间/密钥模式）。`quick_scan`
  少于目标只在 G2 配额或 G6 上限确实堵住全部剩余候选时放行；否则报告第一条违规，
  不做自动修复。
  全文侧按约定补上 `fulltext --title`：`10.48550/arXiv.<id>` 直接映射 arXiv ID；
  标题先按规范化后完全一致匹配 arXiv API，再查 Europe PMC `TITLE:"…"`，得到的
  预印本 DOI / arXiv ID 在 arXiv 与 Unpaywall 之间尝试；近似标题忽略，解析失败
  只少一条路径、不新增 `attempts`，输出 key 不变。`quick_scan` 仍只用摘要，
  `--title` 由日报写作阶段对今日必读 top 3 传入。
  新增 `tests/fixtures/digest/{valid,empty}/`（合格 3 + 7 与空日报）以及
  `fulltext/{title-match,title-mismatch,arxiv-title}/` 录制响应；`tests/test_digest.py`
  覆盖合格、空池、坏 id、日期、G2 超配额、组缺失、must_read 的 model 局限、
  quick_scan 全文声明、数量不足、G2/G6 配额导致的允许/不允许短缺、G6 论文位置、
  OA 标记一致性、翻译/重复标题、GitHub 缺项/多项/空区块、G6 上限、页脚计数/来源/
  密钥、不可读文件与缺参数；`tests/test_fulltext.py` 覆盖标题匹配、近似标题、
  DOI→arXiv 交叉检索、`10.48550` DOI 直映与纯标题无命中。README、
  `docs/adr/0001-literature-source-strategy.md` 与 `CODING_STANDARDS.md` 已同步；
  未新增 config key。
- 2026-10-22：按 code review 的意见补了两处边界，并加强了实现：
  (1) G6 论文只能进 `quick_scan`，因此当候选池里少于 3 篇非 G6 论文时
  `must_read` 允许短于 `min(3, n)`；`quick_scan` 的目标按实际 `must_read` 数计算
  （`min(7, n - 实际 must_read)`），G2 的 4 篇上限与 G6 的 1 篇上限都能解释合法
  短缺，其他短缺仍然失败。
  (2) `10.48550/arXiv.<id>` 作为 DOI 前缀规则，无论是否传 `--title` 都直接映射到
  arXiv ID；`--title` 仍是可选的补充输入，用于按标题匹配其他预印本版本。
  另外：candidate 里 `language` 可以为空（GitHub 未识别语言时 `collect` 会输出空
  串），不再把它当作候选池损坏；repo 的“最近更新”只认 `pushed_at` 的本地日期，
  release 必须写出更新要点，页脚源名/状态必须落在 `来源：` 到 `候选：` 之间。
  新增 G6 短候选池 fixture、G6 数量上限/短路允许、`limits` 缺省值、空语言、
  release 更新要点、活跃库日期与 `来源：` 行归属的测试；Contracts 本身未改。
