# 日报写入契约

每日运行的第二步只写两个文件：`out/selection.json` 与 `out/digest.md`。输入是
`collect` 写出的 `out/candidates.json`。写完后必须用 `<skill>/scripts/digest.py check`
校验；校验不过就不能推送。

## 输入

`out/candidates.json` 的关键字段：

- `date` / `timezone`：当天日期与配置时区，日报标题和页脚要与之一致。
- `candidate_count`：页脚 `候选：N` 的来源。
- `sources`：每个源的名字与 `status`（`ok` / `failed`），页脚逐项照写。
- `papers[]`：每条含 `id`、`group`、`source`、`title`、`authors`、`venue`、`date`、
  `doi`、`pmid`、`arxiv_id`、`url`、`abstract`、`tags`、`relevance`、`score`、
  `is_preprint`、`oa_url`。
- `github`：`new`、`active`、`g6`、`releases`（`starred`）、`g6_releases`，
  外加 `limits` / `found` 等审计字段。是否写出区块由这些列表决定，不由 selection 决定。

## selection.json

```json
{
  "schema_version": 1,
  "date": "<candidates.date>",
  "timezone": "<candidates.timezone>",
  "papers": [
    {
      "id": "<candidates.papers[].id>",
      "group": "<与候选一致的 group>",
      "section": "must_read",
      "reason": "一句入选理由",
      "fulltext": "oa",
      "limitations_source": ["author", "model"]
    }
  ]
}
```

- `section` 只能是 `must_read` / `quick_scan`；`id` 必须存在且不重复；`group` 与候选一致。
- `reason` 非空，写清为什么选它（相关性、方法价值、组别覆盖等）。
- `fulltext`：`oa` / `abstract_only`。`quick_scan` 只能 `abstract_only`。
- `limitations_source`：`author` / `model` 的非空子集；`must_read` 必须含 `model`
  （作者声明之外，至少一条标注为模型判断的局限）。

## 配额

设候选池论文数为 `n`：

- `must_read = min(3, 非 G6 且可用的候选数)`。G6 论文不能进 `must_read`。
- `quick_scan = min(7, n - 实际 must_read)`；总数 `min(10, n)`，不补空。
- G2 最多 4 篇。
- 除 G2 / G6 外，候选池里出现的每个组至少入选 1 篇。
- G6 论文最多 1 篇，且只能进 `quick_scan`（不强制）。
- 因 G2 的 4 篇上限或 G6 的 1 篇上限导致无法达到目标时，允许少于目标；其他短缺
  不合格。不要为了凑数选不相关的论文。

## 全文

只对 `must_read` 的每篇调用 `fulltext`。`quick_scan` 只用候选摘要。

```bash
python3 "<skill>/scripts/fulltext.py" --config config.yaml \
  --doi "<候选 doi>" --arxiv "<候选 arxiv_id>" --title "<候选 title>" \
  --out out/fulltext-1.json
```

- 候选没有 DOI / arXiv ID 时，至少给 `--title`。
- 读输出的 `status`、`methods`、`results`、`limitations`。
- `status=oa`：把方法/结果写进 `- 方法精读：`，selection 的 `fulltext` 写 `oa`。
- `status=no_oa`：selection 写 `abstract_only`，日报的 `- 方法精读：` 必须逐字写
  `无 OA 全文，仅基于摘要`，不替换这篇论文。

## digest.md

固定结构；`digest check` 按字面标签解析，不要改字段名：

```markdown
# 学术速递 · <candidates.date>
> 关键词：<本次关键词> ｜ 新论文 N 篇，精选 M 篇 ｜ GitHub K 个

## 今日必读
### 1. <候选 title 逐字>
- 标签：`tag1` `tag2`
- 摘要：3–5 句
- 局限性：1–3 条
- 方法精读：2–4 句
- [原文](url) · [PDF](oa_url)

### 2. ...
### 3. ...

## 其它速览
- **<候选 title 逐字>** — `tag1` `tag2` · 摘要：1–2 句 · 局限性：1 句 · [链接](url)

## GitHub
### 新项目
- **owner/repo** ⭐ N · 语言 · 最近更新 · 定位 · why · [链接](url)
### 活跃项目
- ...
### 关注项目的新 release
- **owner/repo vX.Y** · 日期 · 更新要点 · [链接](url)

## AI 工具 / Agent Harness
- **owner/repo vX.Y**（官方 release，日期）· 更新要点 · [链接](url)
- **owner/repo** ⭐ N · 语言 · 最近更新 · 定位 · why · [链接](url)

---
来源：pubmed ok (2) ｜ europepmc failed (timeout) ｜ github ok (5)
候选：30 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00
```

规则：

- 标题日期与 `candidates.date` 一致；论文标题逐字照抄，不翻译，同一标题只出现一次。
- 今日必读每条有 `- 标签：`、`- 摘要：`、`- 局限性：`、`- 方法精读：` 与
  `[原文]` 链接。四要素缺一不可。
- 其它速览每条一行，至少含标签、`摘要：`、`局限性：`、链接。
- 摘要/局限性只基于候选摘要或 `fulltext` 输出；数字、样本量、期刊影响因子必须能在
  证据里找到。模型自己的批判归入局限性，并让 selection 的 `limitations_source`
  含 `model`。
- 中文为主；模型名（scGPT/Geneformer 等）、方法名、工具名保留英文。
- GitHub 区块只写 `candidates.github` 里的条目：`new` → 新项目，`active` → 活跃项目，
  `releases.starred` → 关注项目的新 release。每条 repo 写 owner/repo、stars、语言、
  最近更新（`pushed_at` 的本地日期）、一句话定位、为什么相关、链接；语言为空时写
  `未知`。release 写 repo+tag、日期、更新要点、链接。
- `## AI 工具 / Agent Harness` 只写 `g6` 与 `g6_releases`。`g6` 条数不超过
  `candidates.github.limits.g6`（默认 2）；`g6_releases` 每个官方库最多一条，不占
  这 2 条名额，有更新才写。区块为空就整节省略。
- 页脚 `来源：` 到 `候选：` 之间逐项覆盖 `candidates.sources` 的每个源与状态；
  `候选：N` = `candidate_count`；`入选：M` = selection 论文数；`生成：` 是 ISO8601
  时间。页脚不得出现 `sctp`、`SendKey`、`GITHUB_TOKEN`、`Authorization` 等密钥模式。
- 正文目标 5000–6000 汉字；`push` 负责 32KB 拆分与 `未推送数`，日报里不写这两项。

## 空与失败

- `papers` 为空且 GitHub/G6 各列表也为空：允许只写标题 + `---` 页脚的空日报；
  `digest check` 退出 0，`push` 按 `send_empty` 发提示或跳过。
- 某源 `failed`：照实写进页脚，不伪造该源条目；日报继续写。
- 没有 GitHub 数据：省略 `## GitHub` 与 `## AI 工具 / Agent Harness` 两个区块。
- 校验失败：按 stderr 的第一条 `[fail]` 修；不要绕过 `digest check` 直接 `push`。
