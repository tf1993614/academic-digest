# 04 · 竞品、摘要生成与相关性排序调研

> 调研日期：2026-10-22。star 数、最近提交时间均为当日通过 GitHub API 抓取；接口行为为当日实测。
> 标注「未验证」的结论没有拿到一手来源（页面为 JS 渲染或抓取失败），落地前需复核。
> 本文件不覆盖 PubMed / arXiv / GitHub API 的基础用法（由 02/03 号文档负责）。

---

## TL;DR

1. **"每天抓 → 排序 → LLM 摘要 → 推送"已有成熟开源范式**：`zotero-arxiv-daily`（6.1k star）、`daily-arXiv-ai-enhanced`（3.0k）、`cv-arxiv-daily`（1.5k）、`daily-paper-reader`（957）全部是 **GitHub Actions 定时 + 静态站/邮件**，零服务器，验证了"无后端也能每天跑"这条路。
2. **排序的主流做法不是"纯 embedding"，而是"规则召回 + 语义重排"两级**：规则层（关键词分档 + 负词 + 作者 + 分类）保证可解释、可调；embedding/reranker 只对候选池做重排。`arxiv-digest` 把权重写死在文档里，`paper-radar` 用关键词/MeSH 权重 + 90 天半衰期，`daily-paper-reader` 用 BM25 + 向量召回 + Qwen3-Reranker-0.6B。
3. **摘要有三种可靠供给**：Semantic Scholar `tldr`（一句话，免费但限流严重，实测无 key 频繁 429）；OpenAlex `abstract_inverted_index`（需自己还原、可能为 null）；Europe PMC `fullTextXML`（JATS 全文，仅 OA 子集）。三者可拼成"TLDR 兜底 + 摘要 + 可选全文"。
4. **只给 abstract 是默认，全文只给 top-K**：`zotero-arxiv-daily` 用 `pymupdf4llm` 抽全文再让 LLM 写 TLDR，但只对最终入选的 ≤100 篇做；这就是 token 成本可控的关键。
5. **PDF 工具链有许可证坑**：PyMuPDF 是 **AGPL-3.0**（商用需 Artifex 授权），marker 代码 Apache-2.0 但模型 OpenRAIL-M，GROBID 是 Java/Apache-2.0 且 CPU 可跑。中文环境无 GPU 时，`pymupdf4llm` 最省事，GROBID 最"学术结构化"，marker 最重。
6. **幻觉控制靠"引用约束 + 证据缺失即降级"**：要求每段结论附原文句子、字段缺失写 `null`、摘要缺失时明确输出"仅基于标题"。业界开源项目普遍**没有**做这层约束（只写 "AI-generated TL;DR"），这是我们可以差异化的点。
7. **去重与已推送状态几乎都用 SQLite**：`paper-radar` 用 DOI/标题去重，`auto-paper-digest` 用 SQLite 状态机 `NEW→PDF_OK→NBLM_OK→VIDEO_OK`，`daily-paper-reader` 的 README 直接记录了一次"跨日期重复推荐"的 bug 修复（2026-09-16）——这是该赛道最典型的坑。
8. **微信推送不要自己接公众号**：个人微信无法被程序直接推送，常见路径是 Server酱（`https://sctapi.ftqq.com/<SENDKEY>.send`，免费 5 条/天）、WxPusher、企业微信群机器人；公众号模板消息早已改为订阅消息（**未验证**，需查微信官方公告）。
9. **限流是系统性风险**：S2 无 key 实测 429；GitHub 代码搜索 10 req/min（cv-arxiv-daily 因此改为每周任务）；GitHub Actions 公共仓单次 6h、私有仓 2000 min/月（zotero-arxiv-daily 文档）。
10. **推荐架构**：抓取 → 规范化 ID → SQLite 去重 → 规则分 → （可选）向量重排 → top 20–30 → 结构化摘要（默认仅摘要，top 5–10 给全文）→ 渲染推送 → 写回 pushed 状态。每天 100–500 篇的量级，**不需要 GPU，也不需要向量数据库**。

---

## 1. 竞品与开源项目

### 1.1 总览表

| 项目 | 类型 | 数据源 | 排序 | 摘要 | 推送 | 定时 |
|---|---|---|---|---|---|---|
| [zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) | 开源 6.1k★ | arXiv/bioRxiv/medRxiv/ChemRxiv + 用户 Zotero 库 | 与 Zotero 库的 embedding 加权相似度 | LLM（全文经 pymupdf4llm） | SMTP 邮件 | GitHub Actions 22:00 UTC |
| [daily-arXiv-ai-enhanced](https://github.com/dw-dengwei/daily-arXiv-ai-enhanced) | 开源 3.0k★ | arXiv 8 个分类 | 前端按关键词/作者高亮（非排序） | DeepSeek 中文摘要 | GitHub Pages 静态站 | GitHub Actions |
| [cv-arxiv-daily](https://github.com/Vincentqyw/cv-arxiv-daily) | 开源 1.5k★ | arXiv（按 config 关键词） | 无，仅按关键词分组 | 无 | 仓库 README / Pages | GitHub Actions |
| [daily-paper-reader](https://github.com/ziwenhahaha/daily-paper-reader) | 开源 957★ | arXiv/OpenReview/会议/预印本 | BM25+exact+向量召回 → Qwen3-Reranker 重排 | DeepSeek 结构化总结 | Pages 站点 + Zotero | GitHub Actions |
| [auto-paper-digest](https://github.com/brianxiadong/auto-paper-digest) | 开源 584★ | HuggingFace 周榜 | 无 | NotebookLM 视频 | HF Dataset + 抖音 | 手动/脚本 |
| [paper-radar](https://github.com/drpwchen/paper-radar) | 开源 107★ | 期刊 RSS + PubMed E-utilities | 兴趣模型（关键词/MeSH 权重） | 无（下游 LLM） | ntfy | 自建 cron |
| [arxiv-digest](https://github.com/ibaaj/arxiv-digest) | 开源 4★ | arXiv | 规则分档 + 可选 LLM 二次打分 | 无 | 本地 HTML | 手动 |
| [arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite) | 开源 1.7k★（2023 后停更） | arXiv | 每 tag 一个 TF-IDF + SVM | 无 | SendGrid 邮件 | cron |
| [HuggingFace Daily Papers](https://huggingface.co/papers) | 产品 | arXiv + 社区投稿/投票 | 社区 upvote | 平台 AI 一句话摘要 + 关键词 | 每日邮件订阅 | 每日 |
| [Scholar Inbox](https://www.scholar-inbox.com/) | 产品 | arXiv/bioRxiv 等 OA | 用户评分训练 + 主动学习 | 视觉化论文摘要 | 每日推荐（站内/邮件） | 每日 |
| [ResearchRabbit](https://www.researchrabbit.ai/) | 产品（免费+RR+） | 引文图 | 相似/引用关系 | 无 | 站内 | 实时 |
| [Connected Papers](https://www.connectedpapers.com/) | 产品 | 引文图 | 图相似度 | 无 | 站内 | 实时 |
| [PubMed Alerts](https://pubmed.ncbi.nlm.nih.gov/help/#saved-search) | 官方功能 | PubMed | 检索式 | 无 | 邮件 | 日/周/月 |
| [Nature Briefing](https://www.nature.com/briefing/signup) | 编辑简报 | 人工挑选 | 编辑判断 | 编辑撰写 | 邮件 | 每日 |

### 1.2 开源实现逐个事实

#### zotero-arxiv-daily（6,074★，AGPL-3.0，最近提交 2026-10-01）

- 仓库：<https://github.com/TideDra/zotero-arxiv-daily>
- 架构（README "How it works" 原文）：拉取 Zotero 库全部论文 + 前一天新论文 → 用 embedding 模型算每篇摘要向量 → **"score = 对所有 Zotero 论文的加权平均相似度（越新加入库的权重越高）"** → 对入选论文用 LLM 生成 TLDR，"given the text extracted by pymupdf4llm"。
- 工程细节（可直接抄）：
  - 部署形态：**fork 仓库 + 填 GitHub Actions secrets**，默认 workflow 每天 22:00 UTC 跑；周末/假日无新论文时日志显示 "No new papers found"（README 明确写了）。
  - 多源：`arxiv / biorxiv / medrxiv / chemrxiv`，arXiv 支持 `include_cross_list`（是否含交叉列表）。
  - 排序模型二选一：本地 `jinaai/jina-embeddings-v5-text-nano`（sentence-transformers，CPU 可跑）或 OpenAI 兼容 embedding API。
  - 成本闸门：`executor.max_paper_num: 100` 限制邮件内论文数；文档直言调大后可能超过 Actions 配额（公共仓 6h/次、私有仓 2000 min/月）。
  - 推送：SMTP（示例 `smtp.qq.com:465`），`send_empty` 控制"今天没论文是否也发"。
  - 支持 `language: English/Chinese` 控制 TLDR 语言；`include_path` 用 glob 过滤 Zotero 分类；支持忽略不想要的 Zotero 条目。
- 局限（作者自述）："recommendation algorithm is very simple"。

#### daily-arXiv-ai-enhanced（3,024★，License 非标准，最近提交 2026-09-08）

- 仓库：<https://github.com/dw-dengwei/daily-arXiv-ai-enhanced>；在线版 <https://dw-dengwei.github.io/daily-arXiv-ai-enhanced/>
- 架构：GitHub Actions 每天抓 8 个 arXiv 分类（cs.CV/GR/CL/AI/CE/GT/IT/LG）→ DeepSeek 生成**中文**摘要 → 写静态 JSON → GitHub Pages 展示；前端按用户本地保存的关键词/作者做高亮，**偏好只存浏览器 localStorage**。
- 成本数据点（README 原文）：**约 0.2 元人民币/天**（8 个分类）。这是"每天几百篇 + 全量 LLM 摘要"的真实成本锚点。
- 工程细节：secrets 只放 `OPENAI_API_KEY/OPENAI_BASE_URL`，其余为变量（分类、语言、模型名）；可选 `ACCESS_PASSWORD` 保护页面；"SKILL 系统"用于自定义过滤模块。

#### cv-arxiv-daily（1,507★，Apache-2.0，最近提交 2026-10-21）

- 仓库：<https://github.com/Vincentqyw/cv-arxiv-daily>；使用说明 <https://github.com/Vincentqyw/cv-arxiv-daily/blob/main/docs/README.md>
- 架构：`daily_arxiv.py` + `config.yaml`（关键词列表）→ 每天抓 arXiv → 生成/更新 `README.md` 与 `docs/` 静态页；无摘要、无排序，纯"关键词过滤 + 列表"。
- 三个可复用的工程约束（docs/README.md 原文）：
  1. **GitHub 对超过 512 KB 的 markdown 停止渲染** → 因此 `max_papers_in_readme` 只保留最近若干篇，历史按年归档到 `docs/archive/<year>/<Keyword>.md`。
  2. **PapersWithCode 已下线** → 代码链接改为从摘要、HuggingFace papers、GitHub 代码搜索三处找。
  3. **GitHub 搜索 10 请求/分钟** → 代码链接检查拆成"每周一次"的独立 workflow，用 `docs/code-checks.json` 记录已查状态、按最久未查优先。

#### daily-paper-reader（957★，MIT，最近提交 2026-10-05）

- 仓库：<https://github.com/ziwenhahaha/daily-paper-reader>；文档 <https://ziwenhahaha.github.io/daily-paper-reader/#/tutorial/README>
- 架构（README "Workflow Architecture" + 更新日志）：arXiv/OpenReview/会议论文 → 多路召回（BM25、exact、向量）→ 统一候选池 → LLM refine 打分 → rerank（本地 `Qwen/Qwen3-Reranker-0.6B` 或硅基流动 API）→ 生成日报文档与阅读页；向量同步到 Supabase；前端在 GitHub Pages，后端全在 Actions。
- **最有价值的是一串"踩坑修复"记录**（README News）：
  - 2026-09-16：**修复日报跨日期重复推荐**——"同一专题次日不会重新生成相同论文，不同专题仍保持独立"；归一化用 canonical arXiv ID，历史推荐同时参考原始召回标签。
  - 2026-04-08：推荐状态**按 tag 独立维护**，`seen_ids` 不再跨词条污染。
  - 2026-09-09：长窗口（90/365 天）回溯改为分片召回 + 评分缓存，修 RPC 超时。
  - 2026-03-28：远程 embedding 首次失败即**熔断回退本地模型**，避免分片阶段反复超时。
  - 2026-05-30：每个并发线程用**独立 LLM client**，避免共享参数互相覆盖；结构化输出 `max_tokens` 提到 16k。
  - 2026-05-31：公式渲染保护（`\[...\]` 不被 Markdown 破坏）。

#### paper-radar（107★，MIT，最近提交 2026-08-05）

- 仓库：<https://github.com/drpwchen/paper-radar>
- 架构：`fetch_and_score.py` 抓几十个 source（期刊 RSS + `pubmed_search` 走 NCBI E-utilities）→ **SQLite 用 DOI/标题去重** → `interest_model.json`（关键词/MeSH 权重）打分 → `papers.json` → `enrich.py` 用 Unpaywall 标 OA/订阅/自取 → `notify_digest.py` 每日把"够新+够高分+没看过"的推 ntfy。
- 经验（README 注释级细节）：某些出版社 CDN 会挡自动请求（LWW）、部分 Springer 期刊的 `search.rss` XML 是坏的 → **一律改走 PubMed `[ta]` 更稳**。
- v2 推荐模型：D1 事件表 + 特征表 + `model_state.json`（decayed Beta 伪计数 + profile 向量）；**Thompson 采样**排序、**MMR** 打散同主题、固定位置探索槽、90 天半衰期；bge-small（384 维）做语义 profile；任一阶段失败回退到前一天的 keyword 排序。

#### auto-paper-digest（584★，最近提交 2026-02-25）

- 仓库：<https://github.com/brianxiadong/auto-paper-digest>
- 架构：HF 周榜 → 下载 arXiv PDF（**SHA256 校验、幂等**）→ NotebookLM 生成视频 → HF Dataset/抖音发布 → Gradio 门户。
- 可复用点：**SQLite 状态机** `NEW → PDF_OK → NBLM_OK → VIDEO_OK`，断点续传；`playwright install chromium` 复用登录态。说明"长流水线必须落状态，不能靠一次性脚本"。

#### arxiv-digest（4★，2026-05 新建，最近提交 2026-05-21）

- 仓库：<https://github.com/ibaaj/arxiv-digest>
- 价值不在流行度，而在**把打分公式写成了文档**：四档关键词（strong/medium/weak/negative）+ 作者偏好 + 分类调整，输出可解释的 `local_score` 与 reasons/tags，LLM 只做第二阶段的"再加一个相关性分"，输出本地 HTML。
- 公式（README 原文）：`local_score = 6*preferred_author + 4*strong + 2*medium + min(weak,4) - 4*negative + category_adjustment`；命中 blocked author 直接 `-999` 丢弃。

#### arxiv-sanity-lite（1,709★，最后提交 2023-06）

- 仓库：<https://github.com/karpathy/arxiv-sanity-lite>
- 架构：`arxiv_daemon.py` 拉新论文 → `compute.py` 算 TF-IDF → 每个 tag 用 **SVM over tfidf** 推荐 → Flask UI → `send_emails.py`（SendGrid）每日邮件；数据全在 `data/` 目录（sqlite）；作者跑在 1GB 内存 $5/月 的机器上，索引 3 万篇。
- 结论：**已停更，不作为竞品**，但"每个 tag 一个小模型 + 每日邮件"是后来所有项目的共同祖先。

#### agents-radar（1,139★，MIT，最近提交 2026-10-22）

- 仓库：<https://github.com/duanyytop/agents-radar>
- 定位：多源（GitHub、ArXiv、HN、HuggingFace、Product Hunt 等 10 个源）每日 AI 生态摘要，TypeScript。可作为"多源聚合 + 日报排版"的排版参考，非学术推送专用。

### 1.3 商业产品逐个事实

- **HuggingFace Daily Papers**（<https://huggingface.co/papers>）：每天约 30 篇，由社区投稿 + upvote 排序（页面署名 "Daily Papers by AK and the research community"），页面提供 "Get trending papers in your email inbox once a day" 的邮件订阅。API `GET https://huggingface.co/api/daily_papers?limit=N` 实测返回 `paper.upvotes`、`ai_summary`、`ai_keywords`、`ai_summary_model`、`githubRepo`、`organization`、`numComments`。**可直接当"高质量候选池 + 现成一句话摘要"用**。
- **Scholar Inbox**（<https://www.scholar-inbox.com/>）：论文 <https://arxiv.org/abs/2504.08385> 自述——个性化推荐**用用户评分训练**、持续更新 arXiv/bioRxiv 等 OA 源、提供视觉化论文摘要、语义搜索、用 "map of science" 解决冷启动，并用主动学习让用户快速打分；在 80 万条评分数据集上评估。其每日推荐邮件为核心形态（据 ML4Science 介绍 <https://www.machinelearningforscience.de/en/scholar-inbox-personalized-research-recommendations/>）。
- **ResearchRabbit**（<https://www.researchrabbit.ai/>）：免费层含"最多 50 篇起始文献"、引文/参考文献/相似文献浏览、引文图、Zotero 导入、共享收藏；RR+ 提升到 300 篇起始文献 + 多项目 + 高级检索（<https://learn.researchrabbit.ai/en/articles/12865509-researchrabbit-free-tier>，更新于 2026-05-13）。**核心是交互式发现，不是每日推送**（是否提供邮件 alert 未验证）。
- **Connected Papers**（<https://www.connectedpapers.com/>）：引文图可视化探索，定位"给一篇种子论文画出领域图"。定价页为 JS 渲染，**价格与免费额度未验证**。对我们是 UX 参考，不是推送竞品。
- **Papers with Code**：**已下线**。TIB 博客 2025-10-02 记录 "Papers with Code went offline"（<https://blog.tib.eu/2025/10/02/papers-with-code-went-offline-the-knowledge-doesnt-have-to/>）；cv-arxiv-daily 的文档也确认 "PapersWithCode is gone"，代码链接改由摘要 + HF papers + GitHub 搜索补齐。**教训：不要把自己的"代码链接"能力绑在单一第三方上。**
- **Researcher App**：2026-10-22 探测 `https://www.researcher-app.com/` 返回 502/连接失败，**疑似已停运（未验证）**，不建议作为对标。
- **PubMed Alerts**（My NCBI）：保存检索式后按日/周/月发邮件，是"关键词 + 邮件"最省事的官方基线（<https://pubmed.ncbi.nlm.nih.gov/help/#saved-search>）。无排序、无摘要、无去重语义。
- **Nature Briefing**（<https://www.nature.com/briefing/signup>）：编辑人工挑选，"curated by editors, not algorithms"（<https://www.springernature.com/jp/researchers/the-researchers-source/behind-our-brands-blogpost/nature-briefing-stay-informed-and-avoid-overwhelm/52496184>）。它证明"少而精 + 人味"是差异化方向，但无法个性化到个人关键词。

---

## 2. 可复用设计（按价值排序）

| # | 设计 | 来源 | 怎么用 |
|---|---|---|---|
| D1 | **两级排序**：确定性规则分（可解释）→ 语义重排（少量候选） | arxiv-digest、daily-paper-reader | 规则分写进日志/推送脚注，用户能看懂"为什么推这篇"；embedding 只处理 top 100–200 |
| D2 | **四档关键词 + 负词 + 作者黑白名单** | arxiv-digest | 直接照抄 6/4/2/-4 权重，先跑起来再调 |
| D3 | **per-tag 独立 seen 状态** | daily-paper-reader（2026-04-08 修复） | 多主题订阅时，`seen_ids` 必须按 tag 分表，否则 A 主题看过的论文在 B 主题永远不推 |
| D4 | **canonical ID 归一化**（arXiv ID / DOI / PMID 三选一主键） | daily-paper-reader、paper-radar | 同一论文的 v1/v2、arXiv+DOI 双身份要合并 |
| D5 | **SQLite 状态机 + 幂等** | auto-paper-digest、paper-radar | 每条流水线阶段落库，失败可重跑不重复推送 |
| D6 | **全文只给入选的 top-K** | zotero-arxiv-daily（`max_paper_num` + pymupdf4llm） | token 成本的分水岭 |
| D7 | **本地小 embedding 模型 + API 熔断回退** | zotero-arxiv-daily、paper-radar、daily-paper-reader | CPU 跑 bge-small/jina-nano；远端失败立即降级，不阻塞当日推送 |
| D8 | **静态站 + Actions 作为"零服务器"交付** | daily-arXiv-ai-enhanced、cv-arxiv-daily | 适合个人/小团队；缺点是仓库体积与 512KB markdown 限制，需要按年归档 |
| D9 | **推送内容长度硬上限** | zotero-arxiv-daily（100 篇）、daily-arXiv-ai-enhanced（按分类分页） | 微信/邮件都怕长；正文只放 top 5–10，其余折叠成列表 |
| D10 | **代码链接多源兜底** | cv-arxiv-daily（PWC 下线后） | 摘要正则 + HF papers `githubRepo` + GitHub 搜索（限速，放周任务） |

---

## 3. 摘要生成方案

### 3.1 只给 abstract vs 给全文 PDF

| 维度 | 仅摘要 | 全文 |
|---|---|---|
| 信息量 | 背景/方法/主要结论通常够；**缺局限、缺实验细节、缺数值** | 能写"局限"和"与关键词的相关性"的证据 |
| 成本 | 每篇 1.5k–3k tokens | 每篇 15k–60k tokens（解析后），贵 10–20 倍 |
| 幻觉风险 | 低（模型没东西可编），但"局限"段容易套话 | 高（长上下文里编造数字/对比） |
| 工程复杂度 | 低 | 需要 PDF 下载 + 解析 + 清洗 + 截断策略 |
| 适用 | 全部候选的初筛摘要 | 最终 top 5–10 的精读卡 |

**建议**：默认"仅摘要 + 明确标注"；对 top 5–10 且能合法拿到 OA 全文的，追加"方法/实验/局限"段落，并在字段里标 `source: fulltext|abstract`。zotero-arxiv-daily 的做法（全文 → TLDR）适合"篇数少、要质量"；daily-arXiv-ai-enhanced（纯摘要、0.2 元/天）适合"篇数多、要覆盖"。

### 3.2 PDF 解析工具（中文环境 / 无 GPU）

| 工具 | 许可证 | 运行要求 | 适用 | 备注 |
|---|---|---|---|---|
| **PyMuPDF / pymupdf4llm** | **AGPL-3.0**，商用需 Artifex 商业授权（<https://github.com/pymupdf/PyMuPDF>） | 纯 Python wheel，CPU，秒级 | 快速抽文本/markdown，arXiv 双栏效果尚可 | 许可最大的坑：闭源分发必须买授权或换库 |
| **pdfplumber** | MIT（<https://github.com/jsvine/pdfplumber>） | 纯 Python（pdfminer.six），CPU 但慢 | 表格、精确坐标 | 长论文慢，适合按页抽表格 |
| **GROBID** | Apache-2.0，Java（<https://github.com/grobidOrg/grobid>，5,188★，2026-10-21 仍在提交） | JVM + Docker，CPU 可跑，内存占用偏高（具体数值未验证） | 学术 PDF → TEI XML（标题/作者/摘要/参考文献结构化） | 中文论文支持一般；部署重，适合"要结构化元数据"而非"要一段文字" |
| **marker** | 代码 Apache-2.0，模型 OpenRAIL-M（<https://github.com/datalab-to/marker>） | 支持 GPU/CPU/MPS（README 明示），CPU 慢 | PDF→Markdown/JSON，表格/公式好 | 模型权重与商用条款要看 OpenRAIL-M；CPU 上批量不划算 |

**中文环境结论**：无 GPU、每天几十篇 → `pymupdf4llm` 足够；需要参考文献/作者结构化 → GROBID（Docker 一把梭）；要公式/表格高保真 → marker，但只在 top-K 上用。**许可证先定，再选工具**：如果产品闭源，PyMuPDF 要么买授权，要么换 pdfplumber/marker。

### 3.3 三方元数据/摘要源能提供什么

| 源 | 能给什么 | 限制（实测/文档） |
|---|---|---|
| **Semantic Scholar** `tldr` | 一句话 TLDR，字段 `tldr: {model, text}`，实测返回 `"model": "tldr@v2.0.0"`；还有 citationCount、externalIds | **无 key 限流极严**：本次调研连续两次 429（"Too Many Requests... apply for a key"）；论文覆盖偏 CS/生物医学 |
| **OpenAlex** `abstract_inverted_index` | 摘要的倒排索引 `{词: [位置...]}`，需按位置还原成句子；另有 cited_by_count、OA 链接 | 实测部分作品该字段为 `null`；还原要自己写；API 现在按"美元预算"计费：无 key 10 req/s、免费 key 30 req/s、免费账户约 $1/天（<https://help.openalex.org/api/authentication/>） |
| **Europe PMC** `fullTextXML` | JATS 全文 XML（`https://www.ebi.ac.uk/europepmc/webservices/rest/{PMCID}/fullTextXML`，实测 PMC5334499 返回 200、74 KB），另有 `search`/`abstract` | **仅 OA 子集**有全文；无全文时只能拿摘要；限流数值未验证 |
| **HuggingFace Daily Papers** | `ai_summary`（一句话）+ `ai_keywords`（10+ 个关键词） | 只覆盖当日 ~30 篇热门，不是全量 |

**组合策略**：arXiv 全量用官方 abstract；有 DOI/PMID 的补 OpenAlex 摘要（还原失败则跳过）；S2 TLDR 只对 top-K 查（省限流额度）；Europe PMC 全文只对 top 5–10 且 OA 的拉。

### 3.4 结构化摘要的 Prompt 设计要点

目标输出（JSON，便于渲染与入库）：

```json
{
  "background": "1-2 句：要解决什么问题",
  "method": "1-3 句：怎么做（模型/数据/实验设置）",
  "results": "1-2 句：关键结论，带数值（若原文有）",
  "limitations": "1-2 句：作者自述或可推断的局限；无证据则 null",
  "relevance": "1 句：与订阅关键词的关系，必须点名命中的关键词",
  "evidence": [{"field": "results", "quote": "原文句子"}],
  "source": "abstract",
  "confidence": "high|medium|low"
}
```

要点（按重要性）：

1. **角色 + 受众 + 长度**：写清"你是给忙碌研究者做每日筛选的助手，每段不超过 2 句，总长 ≤120 字"。
2. **只允许用给定文本**：`如果文中没有对应信息，填 null，不要推测`。这是抑制幻觉最有效的一条。
3. **强制引用**：每个非 null 字段附 1 条原文句子（`evidence`），长度 ≤ 原文 30 字；渲染时把引文放进折叠区或小字。
4. **相关性必须点名关键词**：`relevance` 里必须出现命中的 include 词，否则该篇降级为"弱相关"。
5. **标注来源边界**：`source: abstract` 时，`limitations` 允许为 null；推送里显示"仅基于摘要"角标。
6. **结构化输出 + 低温度**：`temperature 0–0.3`、`response_format: json_object`，失败重试 1 次后降级为纯文本三段。
7. **少样本 1–2 条**：给一条"摘要信息不足 → 大量 null"的正例，模型会照做。
8. **不要让它打分排序**：LLM 打分不稳定且贵；排序交给规则/向量，LLM 只做"改写与压缩"。
9. **语言**：中文输出但保留英文术语/模型名/数据集名原文，避免翻译失真。
10. **超长截断**：abstract 超过 3k tokens 时保留"首 1.5k + 尾 1k"（结论常在尾部），并在 prompt 里说明"文本已截断"。

### 3.5 幻觉控制清单

- 证据约束（上节第 3 条）+ 字段级 null。
- **数值白名单**：results 里的数字必须能在原文中字符串匹配到，否则删掉该数字（后处理正则校验，成本几乎为零）。
- **不要生成"局限"除非有信号**：摘要里出现 "however/limitation/future work" 才允许填；否则 null + 前端显示"—"。
- **交叉校验**：同一篇用两次不同温度生成，字段不一致时取交集/标 low confidence（只对 top 5 做，成本可控）。
- **推送脚注**：固定一行"摘要由 AI 基于摘要文本生成，可能存在偏差，点击原文核对"。
- **不要用 LLM 生成"引用数/期刊影响因子"**：这些从元数据取，避免模型编造。

### 3.6 Token 成本控制

- 量级估算：500 篇 × 2k tokens ≈ **1M input tokens/天**；只总结 top 30 ≈ **60k tokens/天**，差 16 倍。
- 真实锚点：daily-arXiv-ai-enhanced 全量 8 分类 + DeepSeek 中文摘要 ≈ **0.2 元/天**（README）；说明"全量摘要"在国产模型价位下也可承受，贵的是 GPT-4 级模型。
- 手段：① 只总结 top-K；② 摘要截断到 3k tokens；③ 批量请求（同一天同一 prompt 前缀，命中 caching）；④ 缓存 `(paper_id, prompt_version)` 的结果，重跑不重复花钱；⑤ 失败重试上限 2 次，避免坏样本烧钱。

---

## 4. 相关性排序建议

### 4.1 规则打分（第一层，必做）

参考 arxiv-digest 的显式公式，落到我们的字段：

```text
score = 4.0 * strong_hits
      + 2.0 * medium_hits
      + 0.5 * min(weak_hits, 6)
      - 4.0 * negative_hits
      + 6.0 * author_hit
      + journal_weight        # 白名单 1.0 / 默认 0 / 黑名单 -3
      + recency_bonus         # 24h 内 +1.0，48h 内 +0.5
      + citation_bonus        # log1p(cited_by) * 0.3，仅对老论文有意义
```

- 命中位置加权：标题命中 ×1.5，摘要命中 ×1，关键词字段 ×0.8。
- 归一化到 0–100 再展示，方便用户理解"78 分"。
- 负词命中直接降到阈值以下（类似 `-999`），避免"大模型+医学"这种跨领域误召。
- **可解释性**：把命中的词、作者、期刊写进推送的一行小字（"命中：robot learning, VLA"）。

### 4.2 需不需要 embedding

- 每天 100–500 篇的量级：
  - 本地 `bge-small-zh/en`（384 维）CPU 编码 500 篇 × 512 tokens ≈ 几十秒到几分钟，**完全可接受**；无需 GPU、无需向量数据库（<10 万条用 numpy/faiss-cpu 甚至 SQLite 存 blob 都行）。
  - API embedding 成本：按 500 篇 × 400 tokens ≈ 200k tokens/天，text-embedding 级模型约 $0.004/天（按官方价目换算，**单价未在本次核实**）。
- 结论：**规则分负责"召回与可解释"，embedding 只做"top 100–200 的重排"**。daily-paper-reader 在 957★ 的实战里也是"BM25/exact/向量三路召回 + reranker"，不是纯向量。
- 什么时候值得上 embedding：用户有 Zotero 库/历史点赞（冷启动有信号）、关键词难以枚举（跨领域方法迁移）、多用户个性化。只有关键词订阅时，先别上。

### 4.3 关键词太宽 / 太窄怎么办

| 症状 | 处方 |
|---|---|
| 太宽（每天 300+ 命中，噪声多） | 加 `exclude` 负词（先看一周误推的高频词）；加分类限制（`cs.CL` 而不是 `cs`）；加期刊/会议白名单；把宽词降级为 weak |
| 太窄（每天 0–3 篇） | 把强词拆成同义词组（`VLA / vision-language-action / robot policy`）；开 `include_cross_list`；用 arXiv 分类 + 关键词 OR 而不是 AND；把作者设为 strong |
| 时好时坏 | 分档：strong 必须命中其一才入选（硬门槛），medium/weak 只加分；每周让用户看一次"落选 top 20"校准 |
| 生物医学场景 | 用 **MeSH 词**（PubMed `[MeSH Terms]`）替代自由词，paper-radar 的 `interest_model.json` 就是关键词/MeSH 权重表；再加期刊 `[ta]` 限定 |
| 多主题 | 每个主题独立配置 + 独立 `seen` 状态（D3），推送按主题分组，不混排 |

配置建议模板（YAML）：

```yaml
topics:
  - name: "机器人与VLA"
    arxiv_categories: ["cs.RO", "cs.CV", "cs.LG"]
    strong: ["vision-language-action", "VLA", "robot policy", "dexterous manipulation"]
    medium: ["imitation learning", "diffusion policy", "sim-to-real"]
    weak: ["robot", "manipulation", "embodied"]
    exclude: ["surgical robot", "industrial robot arm control"]
    authors: ["Sergey Levine", "Chelsea Finn"]
    journals: []          # 预印本为主时留空
    max_per_day: 15
```

---

## 5. 去重与"已推送"状态存储

### 5.1 键的设计

- 主键优先级：`arxiv_id`（去掉版本号 `vN`；`2601.01234`）> `doi`（小写、去 `https://doi.org/`）> `pmid` > `normalized_title_hash`（标题去标点/小写后 sha1）。
- 同时存 `aliases` 表：`(paper_id, id_type, id_value)`，解决"arXiv 版 + 期刊版"是同一篇的问题。
- 版本更新：`arxiv_id` 相同但 `version` 变大 → 不算新论文，但如果分数显著升高可"重推一次"，且文案标"更新版"。

### 5.2 表结构（SQLite，够用到几万篇）

```sql
CREATE TABLE papers (
  id            INTEGER PRIMARY KEY,
  arxiv_id      TEXT UNIQUE,
  doi           TEXT,
  pmid          TEXT,
  title         TEXT NOT NULL,
  title_hash    TEXT NOT NULL,
  abstract      TEXT,
  published_at  TEXT,          -- ISO8601
  updated_at    TEXT,
  source        TEXT,          -- arxiv/pubmed/biorxiv/...
  raw_json      TEXT
);
CREATE INDEX idx_papers_pub ON papers(published_at);

CREATE TABLE scores (
  paper_id   INTEGER, topic TEXT, score REAL, detail_json TEXT,
  scored_at  TEXT, PRIMARY KEY (paper_id, topic)
);

CREATE TABLE pushes (
  paper_id    INTEGER,
  topic       TEXT,
  channel     TEXT,            -- email / wechat / site
  pushed_at   TEXT,
  digest_date TEXT,            -- YYYY-MM-DD，按天幂等
  status      TEXT,            -- sent / failed / skipped
  PRIMARY KEY (paper_id, topic, channel)
);

CREATE TABLE summaries (
  paper_id INTEGER, prompt_version TEXT, lang TEXT,
  json TEXT, source TEXT, model TEXT, created_at TEXT,
  PRIMARY KEY (paper_id, prompt_version, lang)
);
```

### 5.3 时间窗口与幂等

- **抓取窗口**：按 `published_at` 取 `[today-48h, now]`，而不是"昨天 00:00–24:00"——arXiv 公告时区（美东）与本地日期错位是重复/漏推的头号原因。
- **推送幂等**：`INSERT OR IGNORE INTO pushes(... digest_date=今天)`；发送前查 `(paper_id, topic, channel)` 是否已存在。
- **回补**：允许"补发昨天失败的那批"，但 `digest_date` 用原日期，避免用户看到"今天又推一遍"。
- **保留窗口**：`pushes` 永久保留（很小）；`papers` 保留 2 年，超期归档到冷表。
- **多通道**：同一篇可同时进邮件和微信，但 `channel` 维度独立去重，避免"邮件发过就不发微信"。

---

## 6. 常见坑（按出现频率）

1. **重复推送**：跨日期、跨主题、arXiv 版本更新、时区错位。daily-paper-reader 2026-09-16 专门修过（同一专题次日重复推荐）；对策见 §5。
2. **摘要幻觉**：编造数值、编造"局限"、把相关工作写成自己的方法。对策：证据引用 + 数值白名单 + null。
3. **限流**：S2 无 key 实测 429；GitHub 搜索 10 req/min；OpenAlex semantic search 1 req/s；Actions 配额。对策：top-K 查询 + 缓存 + 指数退避 + 每周任务。
4. **推送太长**：100 篇 × 200 字 = 2 万字，微信/邮件没人看。对策：正文 top 5–10，其余只列标题+链接；`max_per_day` 硬上限。
5. **空日报**：周末/假日 arXiv 不更新（zotero-arxiv-daily 文档明说），要么 `send_empty=false` 静默，要么发"今日无新论文 + 本周回顾"。
6. **markdown 体积**：GitHub 不渲染 >512 KB 的 README（cv-arxiv-daily 文档），静态站方案要按年归档。
7. **微信通道**：个人微信不能被程序直接推送；Server酱免费仅 **5 条/天**（<https://sct.ftqq.com/docs/>），超量需付费（档位未验证）；公众号模板消息已改订阅消息（**未验证**）。对策：Server酱/WxPusher/企业微信机器人三选一，做成可插拔 channel。
8. **许可证**：PyMuPDF AGPL、marker 模型 OpenRAIL-M、S2/OpenAlex 数据条款；闭源商用前必须过一遍。
9. **全文版权**：只对 OA（Unpaywall/Europe PMC OA/arXiv）拉全文，不要把订阅全文落库再分发。
10. **解析失败静默**：PDF 解析失败要落 `status=failed` 并降级为"仅摘要"，不能整批中断。
11. **模型漂移/成本漂移**：模型名写死在配置里，记录 `model` 与 `prompt_version`，便于回溯"上周摘要为什么变差了"。
12. **第三方依赖消失**：Papers with Code 下线就是活例子，代码链接、引用数都要有兜底源。

---

## 7. 推荐做法（本项目的落地蓝图）

**MVP（1–2 天可跑）**

1. 数据：arXiv（按分类 + 关键词）+ PubMed（MeSH/检索式），抓 `[now-48h, now]`。
2. 归一化 + SQLite 去重（§5）。
3. 规则打分（§4.1），阈值 + 每主题 `max_per_day`。
4. 摘要：仅 abstract，JSON 结构化（§3.4），top 20–30。
5. 推送：邮件（SMTP）+ 微信（Server酱），正文 top 5–10，其余折叠。
6. 状态：`pushes` 幂等，失败重试。

**V1（一周内）**

- 加 embedding 重排（bge-small，本地 CPU），只对 top 100。
- 加"仅基于摘要/全文"角标 + evidence 引用折叠。
- 加每周回补任务（补失败、补代码链接、补 citation 数）。
- 加配置校验（关键词为空/全被 exclude 时启动即报错）。

**V2（可选）**

- top 5 全文精读（pymupdf4llm → 方法/实验/局限）。
- 用户反馈（👍/👎/已读）回流，调关键词权重（paper-radar 的 Beta/半衰期方案）。
- 多用户：per-user profile + 共享论文池，避免重复抓取与重复摘要。

**明确不建议**：自建向量数据库、用 LLM 做排序、给全部 500 篇生成全文级摘要、把公众号当唯一通道。

---

## 8. 待确认问题

1. **推送主通道**：邮件 / 微信（Server酱 vs WxPusher vs 企业微信机器人）/ 静态站，优先级与预算？（Server酱免费 5 条/天是否够，取决于是否合并成一条日报）
2. **用户规模**：单人自用还是要多用户？多用户会显著改变去重、摘要缓存与成本模型。
3. **全文边界**：只做 OA 全文，还是允许用户上传 PDF？后者涉及版权与存储。
4. **摘要语言**：中文为主还是中英双语？双语会让 token 翻倍。
5. **领域范围**：只做 CS/arXiv，还是含 PubMed/生物医学？后者需要 MeSH 词表与期刊白名单。
6. **许可证路线**：产品是否闭源？决定 PyMuPDF 能不能用。
7. **成本上限**：每天可接受的 LLM 预算是多少（0.2 元/天 vs 几美元/天）？
8. **评测方式**：如何定义"推得准"？建议先人工标注 2 周（每天 top 20 的 relevant/irrelevant），再谈自动调参。
9. **数据合规**：是否需要遵守 GDPR/机构订阅条款（尤其全文与作者信息）。
10. **未验证项复核**：Connected Papers 价格、Researcher App 状态、微信公众号订阅消息政策、GROBID 内存需求、Europe PMC 限流、Server酱付费档位。

---

## 附：本次调研的抓取方式

- GitHub star/最近提交：`https://api.github.com/repos/{owner}/{repo}`（2026-10-22）。
- 接口实测：S2 `graph/v1/paper/DOI:...?fields=title,tldr`（含 429）、OpenAlex `works/doi:...?select=abstract_inverted_index`、Europe PMC `fullTextXML`、HF `api/daily_papers`。
- 未能抓取（JS 渲染/防护）：Connected Papers 定价页、Scholar Inbox 首页正文（改用其 arXiv 论文）、ReadTheDocs 上的 GROBID 文档（改用 GitHub 仓库）。
