# 自动学术速递 · 已确认需求（Decision Record）

> 状态：**需求已确认**。Issue 01（走通骨架：配置 + 状态 + PubMed → 候选池）已实现，
> 其余能力按 `.scratch/academic-digest/issues/` 推进。
> 记录时间：2026-10-22。

## 1. 已确认的决定

| # | 决定 | 内容 |
|---|---|---|
| 1 | 关键词 | 见 §2 的完整清单与分组草案；用户后续可增删 |
| 2 | 微信通道 | **Server酱**，用户已注册；SendKey 待放入本地 `secrets.env`，不进对话、不进 git |
| 3 | 日报结构 | 论文四要素：**标题、关键词标签、摘要、局限性**；两级：**今日必读** 与 **其它速览** |
| 4 | GitHub | **三种模式都要**：①新出现的相关 repo；②最近活跃/涨 star 的 repo；③已 star 的 repo 的新 release；阈值与查询见 §8 |
| 5 | 全文 | **今日必读的 top 3** 拉 OA 全文，做方法/局限精读；无 OA 全文时降级为摘要并明确标注 |
| 6 | 入选机制 | 脚本先给 **top 30 候选**；模型按“分组配额 + 语义相关性”选 3 篇必读 + 7 篇速览，并为每条写一句入选理由 |
| 7 | 分组配额 | G2（单细胞/空间）最多 4 席；G1/G3/G4/G5 只要有命中至少 1 席；剩余按分数补。G6 独立成区，不占论文席位 |
| 8 | 全文补全 | 先加 **Unpaywall + 预印本版本匹配**（bioRxiv/RS/arXiv），仍无全文则相关性优先、标“仅摘要”，不替换 |
| 9 | 失败与配额 | 单源失败继续发并标“X 源失败”；全部失败不推送、退出码非 0；Server酱失败重试 2 次，仍失败存 pending 次日优先重发；无新内容也推送一条“今日没有匹配的检索条目”（`send_empty: true` 默认）；补窗最多 7 天 |
| 10 | 局限性 | 作者 limitation（若有）+ 模型基于全文/摘要补 1 条独立批判（样本量、泛化性、基线），标注“模型判断” |
| 11 | 节奏与评估 | 每天 **08:00 Asia/Shanghai**；V1 不做反馈闭环；跑两周后人工看 10 期再调关键词/配额；可选每周日“本周回顾” |
| 12 | G6 AI 工具区 | **独立“AI 工具 / Agent Harness”区块**，跟踪 Claude Code / Codex / DSH 的官方 release + 新库/活跃库 1–2 条；arXiv 高相关论文可放 1 条到其它速览，不占 3+7 席位 |

## 2. 关键词完整清单（原文保留）

### 2.1 中文

老化、多组学、单细胞、零样本、扰动预测、基因调控网络、主调控因子、单细胞基础模型、向量量化、可解释性、批效应校正、细胞编码、图知识网络。

### 2.2 英文 / 混合

spatial transcriptomics、isoform-resolved、MERFISH、in situ amplification、single-cell、LLMs+Graphs: Toward Graph-Native, Synergistic AI Systems、LLM、multimodal foundation model、single-cell multi-omics、RNA-protein co-assay、protein imputation、cell type annotation、batch effect correction、cell-cell communication、CITE-seq、virtual cell、genetic perturbation、multimodal learning、knowledge graph、retrieval-augmented、reasoning、GNN、ESM-2、CellVQ、scRNA-seq。

### 2.3 分组与配额（已确认）

| 组 | 主题 | 中文词 | 英文 terms | 检索策略 |
|---|---|---|---|---|
| G1 | 老化 × 多组学 | 老化、多组学 | aging / ageing / senescence、multi-omics / multiomics、single-cell multi-omics | 老化词 AND 多组学/单细胞词；避免“aging”单独跑 |
| G2 | 单细胞与空间组学 | 单细胞 | single-cell、scRNA-seq、spatial transcriptomics、MERFISH、in situ amplification、isoform-resolved、CITE-seq、RNA-protein co-assay、cell-cell communication | OR 展开；空间组学单独成簇 |
| G3 | 单细胞基础模型与表征 | 单细胞基础模型、向量量化、细胞编码、批效应校正、可解释性 | single-cell foundation model、CellVQ、vector quantization、cell encoding、cell type annotation、protein imputation、virtual cell、batch effect correction、interpretability / explainability | 具体模型/方法名可单独跑；泛词与 single-cell 组合 |
| G4 | 扰动预测与基因调控 | 扰动预测、基因调控网络、主调控因子、零样本 | perturbation prediction、genetic perturbation、gene regulatory network / GRN、master regulator、zero-shot | 零样本必须与扰动/单细胞组合；GRN 单独可跑 |
| G5 | LLM / 图 / 多模态 | 图知识网络 | LLM / large language model、multimodal foundation model、multimodal learning、knowledge graph、graph knowledge network、retrieval-augmented、reasoning、GNN、ESM-2、CellVQ、LLMs+Graphs / Graph-Native | **泛词必须加生物锚点**（single-cell / genomics / protein / perturbation / cell）；`LLMs+Graphs` 作为精确短语单独监控 |
| G6 | AI 编程工具 / Agent Harness | — | Claude Code、Codex、DSH harness（DeepSeek Harness） | **独立“AI 工具 / Agent Harness”区块**；GitHub 官方 repo + 搜索为主；arXiv 高相关论文可进其它速览，不占论文席位 |

### 2.4 泛词防噪规则（重要）

以下词单独检索会淹没日报，必须和“生物/单细胞/组学”锚点做 AND：

- `LLM`、`reasoning`、`GNN`、`retrieval-augmented`、`multimodal learning`
- `single-cell`、`zero-shot`
- `knowledge graph`（与 biology / cell / gene 组合）

锚点集合：`single-cell OR scRNA-seq OR genomics OR transcriptomics OR perturbation OR protein OR "cell type" OR CRISPR`。

### 2.5 特别监控

`LLMs+Graphs: Toward Graph-Native, Synergistic AI Systems` 看起来是一篇具体论文的标题。建议作为**精确短语监控**（PubMed/EPMC/arXiv 的 title/abstract 精确匹配），而不是当作主题词；抓到后单独标注。

## 3. 日报格式（已确认）

```markdown
# 学术速递 · YYYY-MM-DD
> 关键词：… ｜ 新论文 N 篇，精选 M 篇 ｜ GitHub K 个

## 今日必读（3 篇）
### 1. <标题>
- 标签：`single-cell` `perturbation` `foundation model`
- 摘要：3–5 句，只基于摘要/全文，不编造数字
- 局限性：1–3 条；来自全文讨论/限制段，或明确写“仅基于摘要”
- 方法精读：仅 top 3，基于 OA 全文，2–4 句
- [原文](DOI/URL) · [PDF](OA PDF)

## 其它速览（N 篇）
- **<标题>** — `tag1` `tag2`
  1–2 句摘要 + 1 句局限 · [链接]

## GitHub
### 新项目
- **owner/repo** ⭐ N · 语言 · 一句话定位 · 为什么相关 · [链接]
### 活跃项目
- …
### 关注项目的新 release
- **owner/repo vX.Y** · 日期 · 更新要点 · [链接]

## AI 工具 / Agent Harness（独立区块，不占论文席位）
- **Claude Code / Codex / DSH** 的官方 release（有更新才写）
- 或：新出现的相关工具 repo / 近期活跃 repo（1–2 条）
```

规则：

- 每篇论文必须有四要素；“其它速览”压缩为标题 + 标签 + 1–2 句摘要 + 1 句局限。
- 今日必读默认 3 篇，全部尝试 OA 全文；其它速览默认 7 篇。
- GitHub 默认 3–5 个，按三种模式各取 1–2 个。
- G6 独立区块默认 1–2 条，不占 3+7 的论文席位；arXiv 有高相关论文时最多放 1 条到其它速览。
- 中文为主，专有名词/模型名保留英文。
- 无新内容时默认发送一条提示（`send_empty: true`），设为 `false` 可静默。

## 4. 数据源（已确认方向）

- PubMed（主，`datetype=edat`，回看 2 天）
- Europe PMC（预印本/摘要补充，`SRC:PPR`，回看 2 天）
- arXiv RSS（`announce_type=new`）+ API（关键词，回溯 4 天）
- Research Square RSS（自带 `<abstract>`）
- 可选 bioRxiv/medRxiv（按日期全量）
- 期刊白名单走 PubMed/EPMC 的 `JOURNAL` 过滤；不爬期刊官网
- GitHub Search API（token）+ `releases.atom` / releases API
- OA 全文：Europe PMC `fullTextXML` / arXiv HTML/PDF / bioRxiv/RS PDF；无 OA 则降级

## 5. 运行方式

- 任务看板一张卡，cron 固定 `0 8 * * *`，`Asia/Shanghai`。
- 权限 `workspace-write`；首次需在看板 UI 确认（若高于部署默认）。
- 不启用看板验收裁判；以 `push.py` 退出码 + SQLite `runs` 为完成依据。
- 错过触发不补跑：按 `last_success` 回看 2–7 天。

## 6. 待补齐（实现前需要）

| 项 | 说明 |
|---|---|
| Server酱 SendKey | 放到本地 `secrets.env`，权限 600；不要在对话里贴 |
| GitHub token | fine-grained public read-only 或 classic 零 scope；放 `secrets.env` |
| 期刊白名单 | 默认不限期刊；要限定再给名单 |

## 7. GitHub 发现（已确认）

- GitHub 用户名：`tf1993614`；当前 starred 只有 **8 个 repo**，全部跟踪没有配额压力。
- 新库：`created:>7天` + `stars:>=5`，每天最多 1 条。
- 活跃库：`pushed:>7天` + `stars:>=30`，按 SQLite 里的 star 增量排序，每天最多 2 条。
- 关注库：全部 starred repo，release 最近 7 天，每天最多 2 条。
- 服务端发现查询（**22 条**）：`topic:single-cell`、`topic:spatial-transcriptomics`、`topic:single-cell-analysis`、`topic:multi-omics`、`topic:gene-regulatory-network`、`topic:knowledge-graph`、`topic:graph-neural-network`、`"single-cell foundation model" in:name,description,readme`、`"spatial transcriptomics" in:name,description,readme`、`"perturbation prediction" in:name,description,readme`、`"virtual cell" in:name,description,readme`、`"cell type annotation" in:name,description,readme`、`"batch effect correction" in:name,description,readme`、`MERFISH in:name,description,readme`、`CITE-seq in:name,description,readme`、`CellVQ in:name,description,readme`、`ESM-2 in:name,description,readme`、`LLM single-cell in:name,description,readme`、`topic:aging`、`"cell-cell communication" in:name,description,readme`、`GraphRAG in:name,description,readme`、`"protein imputation" in:name,description,readme`。
- 本地打分词：见 §2.3 的 G1–G5 terms；模型名 `scGPT`、`Geneformer`、`scFoundation`、`CellPLM`、`scVI`、`Tangram`、`CellChat`、`CellPhoneDB`、`Squidpy`、`Scanpy`、`AnnData`、`Perturb-seq` 作为**可选**，默认不加。
- G6 官方关注库：`anthropics/claude-code`、`openai/codex`、`deepseek-ai/deepseek-harness`。
- G6 发现查询（12 条）：`topic:claude-code`、`"claude code" in:name,description,readme`、`topic:codex`、`"codex cli" in:name,description,readme`、`"openai codex" in:name,description,readme`、`topic:deepseek-harness`、`"deepseek harness" in:name,description,readme`、`"DSH harness" in:name,description,readme`、`topic:ai-coding-agent`、`topic:coding-agent`、`"agent harness" in:name,description,readme`、`"terminal agent" in:name,description,readme`。
- G6 arXiv 查询：`all:"Claude Code" OR all:"Codex CLI" OR all:"DeepSeek Harness" OR all:"coding agent" OR all:"agent harness"`，限定 `cs.SE` / `cs.AI` / `cs.CL` / `cs.LG`，回溯 4 天。

## 8. 明确不做

- 不爬期刊官网（反爬/ToS/改版风险）。
- 不爬 Research Square 官方 API（要 token，robots 禁止）。
- 不自建公众号、不做个人微信协议逆向。
- 不启用看板 coding 验收裁判（每天 6 次调用不划算）。
- 不把 SendKey/GitHub token 写进任务卡 Prompt 或代码。

## Amendment 2026-10-22（Issue 09）

Server酱 推送定案：V1 只走 ServerChan 的 `POST`（`title` + Markdown `desp`），成功
条件是 HTTP 2xx 且 `code` 为整数 0；SendKey 只从 `push.sendkey_env` 指向的环境变量
读取，`--dry-run` 与 fixture 回放都不读它，key 与含 key 的 URL 不进入 stdout /
stderr、状态库或日报。正文按顶层 `## ` 区块拆分（默认超过 30000 字节才拆，单条
≤32768 字节、最多 2 条），绝不从论文中间截断；拆条标题加 `（i/n）`，最后一条页脚
在有未送达消息时追加 `未推送数：P`。每条消息最多重试 2 次（指数退避）；仍失败则把
该条及其后未发送的消息写入 SQLite `pending`，下次 live 运行先丢弃 `created_at` 超过 2 个日历日的
整组，再按 part 顺序各重试一次，整组成功后按 `items_json` 补写 `pushes`。空日报
默认发一条提示（`send_empty` 默认 `true`），关闭时记
`runs(status='skipped_empty')` 并退出 0；若同一轮 pending 重试失败，则退出 1、
状态 `failed`。`runs` 增加 `selected_count` /
`pushed_count` / `pending_count` 三列（Schema v3）；真实连通性与测试推送留给
Issue 10 的 setup 流程。
