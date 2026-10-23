# 自动学术速递 · Spec

Status: ready-for-agent

## Problem Statement

研究者每天要在 PubMed、预印本平台、期刊目次和 GitHub 之间来回切换，用一组横跨生物医学与 AI 的关键词找新论文、新仓库和新 release。现成的 alert 工具通常只覆盖单一来源，或者不支持中文摘要、GitHub 三种发现模式和微信推送，也无法复用已有的任务看板做定时与执行记录。结果是漏检、重复推送、以及因为手动操作太繁琐而无法坚持。

## Solution

做一个 DSH skill，配一张任务看板卡：每天 08:00 由看板启动一个会话，会话加载 skill，运行确定性的采集脚本，把候选交给会话模型筛选并写成中文日报，再由推送脚本通过 Server酱 发到微信。

日报分两级：**今日必读** 3 篇（尝试 OA 全文做方法与局限精读）和 **其它速览** 7 篇。论文四要素固定为标题、关键词标签、摘要、局限性。GitHub 覆盖**新库**、**活跃库**、**关注库**三种模式，并单独设 **AI 工具 / Agent Harness** 区块跟踪 Claude Code、Codex、DSH。采集、去重、打分、推送、状态记录都是确定性的；模型只负责语义筛选与写作，不额外调用 LLM API。

## User Stories

1. 作为研究者，我希望每天 08:00 自动收到一份中文日报，以便不用手动刷多个网站。
2. 作为研究者，我希望用一组分组的关键词配置日报，以便覆盖老化、多组学、单细胞、扰动预测、LLM/图等多个方向。
3. 作为研究者，我希望 G2（单细胞/空间）每天最多占 4 个论文席位，以便宽泛方向不淹没其他组。
4. 作为研究者，我希望 G1/G3/G4/G5 只要有命中就至少占 1 席，以便小众方向不会整天消失。
5. 作为研究者，我希望日报固定为 3 篇今日必读 + 7 篇其它速览，以便每天阅读量稳定。
6. 作为研究者，我希望每篇论文都有标题、关键词标签、摘要、局限性四个字段，以便快速判断是否值得读。
7. 作为研究者，我希望关键词标签直接来自我的关键词组，以便一眼看出它为什么被选中。
8. 作为研究者，我希望今日必读的 top 3 尝试拉 OA 全文，做方法与局限精读，以便不只看摘要。
9. 作为研究者，我希望拿不到 OA 全文时明确标注“仅基于摘要”，以便知道精读的边界。
10. 作为研究者，我希望局限性由作者声明 + 一条标注“模型判断”的独立批判组成，以便既忠实又有判断。
11. 作为研究者，我希望每条入选都有一句入选理由，以便判断筛选是否符合预期。
12. 作为研究者，我希望摘要以中文为主、模型名和技术名保留英文，以便阅读。
13. 作为研究者，我希望 PubMed 覆盖 MEDLINE 的每日新增，以便不漏生物医学主库。
14. 作为研究者，我希望 Europe PMC 补充预印本与缺失摘要，以便覆盖 bioRxiv/medRxiv/Research Square 等。
15. 作为研究者，我希望 arXiv 的每日新增按公告类型判断，以便不把旧投稿当成今天的新论文。
16. 作为研究者，我希望 Research Square 的 RSS 直接提供摘要，以便不依赖它的官方 API。
17. 作为研究者，我希望 bioRxiv/medRxiv 可以按需开启全量抓取，以便在需要完整性时补漏。
18. 作为研究者，我希望按期刊白名单过滤时走 PubMed/Europe PMC，而不是爬期刊官网，以便稳定且合规。
19. 作为研究者，我希望 GitHub 能发现刚出现的新库，以便第一时间看到新工具。
20. 作为研究者，我希望 GitHub 能发现最近活跃/涨 star 的库，以便找到仍在维护的相关项目。
21. 作为研究者，我希望 GitHub 能跟踪我已 star 的 8 个 repo 的新 release，以便不错过关注项目的更新。
22. 作为研究者，我希望单独一个 AI 工具区块跟踪 Claude Code、Codex、DSH 的官方 release 与生态新库，以便跟上前沿工具。
23. 作为研究者，我希望 GitHub 摘要包含 stars、语言、最近更新、一句话定位和为什么相关，以便快速筛选。
24. 作为研究者，我希望同一篇论文/同一个 repo 不会跨天、跨组重复推送，以便日报不注水。
25. 作为研究者，我希望机器关机错过定时后，下次运行能补最近 2–7 天的内容，以便不漏。
26. 作为研究者，我希望某个数据源失败时日报继续发，并在页脚标明哪个源失败，以便不会整天收不到。
27. 作为研究者，我希望所有数据源都失败时不推送，并让任务看板显示失败，以便知道需要修。
28. 作为研究者，我希望没有新内容时也收到一条“今日没有匹配的检索条目”，并可配置关闭，以便确认检索确实跑过。
29. 作为研究者，我希望 Server酱 消息控制在 32KB 内，超长时按区块拆成最多 2 条，以便手机端可读。
30. 作为研究者，我希望 Server酱 发送失败时自动重试 2 次，仍失败则留到下次优先重发，以便不丢日报。
31. 作为研究者，我希望坏的配置（空关键词、缺 token、坏 YAML）在运行前就报错，以便不浪费一次定时。
32. 作为研究者，我希望有一个 dry-run 和测试推送，以便先看效果再接定时。
33. 作为研究者，我希望有一个 doctor 自检，检查网络、密钥、通道和配置，以便快速定位环境问题。
34. 作为研究者，我希望在任务看板里能看到每次执行的历史、失败原因和手动重跑入口，以便运维。
35. 作为研究者，我希望任务卡固定工作区和 workspace-write 权限，以便脚本能写状态文件。
36. 作为研究者，我希望 SendKey 和 GitHub token 不出现在 Prompt、日志或日报里，以便不泄露。
37. 作为研究者，我希望改关键词、配额、期刊白名单时只改配置，不改代码，以便长期维护。
38. 作为研究者，我希望所有“结论/数值”都能追溯到摘要或全文，模型不编造数字，以便可信。
39. 作为研究者，我希望日报正文控制在 5000–6000 汉字，以便微信里一次读完。
40. 作为研究者，我希望以后能加 Cursor/Windsurf/Aider 等工具，但 V1 先不加，以便先控制噪声。
41. 作为维护者，我希望采集、推送、自检都通过 CLI 边界测试，以便换内部实现不碎测试。
42. 作为维护者，我希望测试完全不碰网络，用录制的 HTTP fixture 和固定时间，以便稳定可重复。
43. 作为维护者，我希望依赖尽量少，只用 Python 3.11 + 已安装的 requests/PyYAML/bs4/lxml/PyMuPDF，以便部署简单。
44. 作为维护者，我希望 skill 的 setup 流程能生成配置、跑 doctor、发测试推送并创建任务卡，以便一次配置完。
45. 作为维护者，我希望运行日志和状态可审计，以便两周后判断推得准不准。

## Implementation Decisions

### 架构分层

- **Skill 层**：一份 `SKILL.md`，负责 setup 访谈、配置生成、doctor、dry-run、创建任务卡，以及每日运行的三步指令。skill 通过项目级 `.dsh/skills` 被发现，并软链到用户级 skills 以便任意工作区可用。
- **采集层**：`collect` CLI，负责多源抓取、归一化、去重、打分、分组配额，输出候选池。
- **写作层**：会话模型，读候选池，按配额与相关性选出 3+7，写日报与 selection 记录；不调用额外 LLM API。
- **推送层**：`push` CLI，负责校验 selection、排版、分条、Server酱 发送、状态记账与 pending 重试。
- **自检层**：`doctor` CLI，负责网络、密钥、通道、配置检查；支持 fixture 模式。
- **状态层**：SQLite，记录 papers、pushes、runs 三张表；pushes 以 `(item_id, topic, channel, digest_date)` 唯一。
- **调度层**：任务看板一张卡，cron `0 8 * * *`，`Asia/Shanghai`；不启用验收裁判，完成与否由 `push` 退出码与 runs 记录判断。

### 配置

- 配置为 YAML，包含：时区、各源 lookback、topics（name/terms/exclude/max_items）、sources 开关、journal_filter、GitHub 查询与阈值、summarize 上限、push 通道与长度、schedule。
- `topics` 默认六组：G1 老化×多组学、G2 单细胞/空间、G3 基础模型/表征、G4 扰动/调控、G5 LLM/图/多模态、G6 AI 工具/Agent Harness。
- G6 是独立区块，不占 3+7 的论文席位；G6 默认 1–2 条 GitHub，arXiv 高相关论文最多 1 条放入其它速览。
- 改动关键词、排除词、配额、期刊白名单、GitHub 阈值都只改配置，不改代码。
- 配置校验失败时，CLI 以非零退出并给出可操作的错误信息；不发起任何网络请求。

### 数据源与查询

- PubMed：`esearch` 用 `datetype=edat` + 2 天窗口；`efetch` 必须用 XML 解析摘要，绝不使用 JSON 模式。
- Europe PMC：`FIRST_PDATE` + `SRC:MED`/`SRC:PPR`，`resultType=core`，`pageSize` 不超过 1000，`sort=P_PDATE_D desc`。
- arXiv：每日新增用 RSS 的 `announce_type=new`（跳过 replace）；关键词/历史用 API，lookback 至少 4 天，遵守 1 请求/3 秒。
- Research Square：读 RSS，使用 `<abstract>`、`<authors>`、`<doi>`；不爬官方 API。
- bioRxiv/medRxiv：默认关闭；开启时按日期全量拉取（30 条/页），本地过滤。
- 期刊白名单：走 PubMed/Europe PMC 的 `JOURNAL` 过滤，不抓期刊官网；候选池按 `venue` 命中名单加分，因此其他来源中被合并为期刊版本的论文同样适用。
- GitHub：22 条发现查询 + G6 12 条，分“新库”（`created:>7天`、stars≥5）与“活跃库”（`pushed:>7天`、stars≥30）两遍；`sort=updated`，只取第一页。
- GitHub 官方关注库：`anthropics/claude-code`、`openai/codex`、`deepseek-ai/deepseek-harness`；关注库 release 看最近 7 天。
- GitHub 本地打分：对 name/description/topics/README 命中 G1–G6 terms；README 走 raw 域名，不占 API 配额。
- GitHub 请求必须带 User-Agent 与 token；search 请求按 30/min 限速，串行并留间隔。

### 归一化、去重与排序

- 去重键优先级：DOI（小写、去前缀）> PMID > arXiv ID（去版本号）> `normTitle+year` 哈希。
- 候选池按规则分排序：标题命中权重高于摘要；期刊白名单按 `venue` 命中 +2；新鲜度加分；GitHub 用 `log10(stars)` 与最近 push 加分。
- 候选池最多 30 条，按组保留足够样本：每组最多 6 条，且非空组至少保留其最高分的 1 条。
- 已推送条目不再进入候选池；`papers` 记录首次/最近出现，`pushes` 记录发送结果。

### 候选池与模型契约

- `collect` 输出 JSON：每条含 id、group、source、title、authors、venue、date、doi、pmid、arxiv_id、url、abstract、abstract_missing、tags、relevance、score、is_preprint、journal_match、oa_url（可空）。`journal_match` 仅在配置了非空 `journal_filter` 且 `venue` 命中时为 `true`。
- 模型读取候选池，选出 3 篇今日必读 + 7 篇其它速览，必须满足：G2 ≤ 4；G1/G3/G4/G5 只要有候选就至少 1 篇；不足 10 篇时不凑数。
- 模型同时输出 selection 记录：每条的被选 id、组、一句入选理由、全文状态（OA 全文/仅摘要）、局限性来源（作者/模型判断）。
- 模型只使用候选池中的摘要或已抓取全文，不得编造数字、样本量、期刊影响因子。
- 若 selection 不合法（缺 id、超配额、组别不符），`push` 拒绝发送并退出非零；不自动用脚本结果替代，避免把未经写作的内容推出去。

### 全文抓取

- 只对今日必读 top 3 尝试全文；顺序为：Europe PMC `fullTextXML`（OA）→ arXiv HTML/PDF → bioRxiv/medRxiv/Research Square PDF → Unpaywall 最佳 OA 位置。
- 同时用标题/DOI 匹配预印本版本（bioRxiv/medRxiv/Research Square/arXiv），以提高全文覆盖率。
- 全文解析后只提取方法/结果/局限相关段落，作为精读与局限性的证据；引用原文句子时标注来源。
- 全部失败时标注“无 OA 全文，仅基于摘要”，不替换该论文；相关性优先于全文可得性。

### 日报格式

- 标题、关键词标签、摘要、局限性四要素必须齐全；今日必读每条 3–5 句摘要 + 1–3 条局限 + 2–4 句方法精读。
- 其它速览压缩为标题 + 标签 + 1–2 句摘要 + 1 句局限。
- GitHub 每条含 owner/repo、stars、语言、最近更新、一句话定位、为什么相关、链接。
- G6 区块独立，含官方 release（有更新才写）与 1–2 条生态 repo。
- 页脚标明：各源状态、候选数、入选数、未推送数、生成时间；不写密钥。
- 正文目标 5000–6000 汉字；Server酱 单条上限 32KB，超过时按区块拆成最多 2 条，并带“（1/2）”后缀；绝不从一条论文中间截断。

### 推送与状态

- Server酱：POST 到 `sctapi.ftqq.com`；`sctp` 开头的 key 走对应的 `push.ft07.com` 端点；`title` 不含换行且不超过 32 字符。
- 成功条件：HTTP 2xx 且返回 `code=0`；失败重试 2 次（指数退避），仍失败写入 pending 并退出非零。
- pending 在下次运行优先重试一次；超过 2 天仍失败则丢弃并在 runs 中记录。
- 无新内容且 `send_empty=true`（默认）时发送一条“今日没有匹配的检索条目”的提示，退出 0；`send_empty=false` 时不发送、退出 0，并记录“无新内容”。
- 部分源失败：继续发送，页脚标“X 源失败”；全部源失败：不发送、退出非零。
- 状态库记录 runs：开始/结束时间、各源计数、候选数、入选数、推送结果、错误摘要；不记录密钥。

### 任务看板与 skill

- 任务卡固定工作区为本仓库、权限 `workspace-write`；Prompt 明确“加载 academic-digest skill，运行 collect → 写日报 → push；只有 push 退出 0 才视为完成”。
- 看板不启用验收裁判；`goalRun` 默认关闭。若用户开启 `/goal`，卡片勾选跳过验收，避免每天 6 次裁判调用。
- skill 的 setup 流程：访谈关键词/通道 → 写配置 → doctor → dry-run → 测试推送 → 创建任务卡与 cron。
- Host 必须在线；错过触发不补跑，采集按 `last_success` 回看 2–7 天。
- 首次运行前需要用户提供 Server酱 SendKey、GitHub token、GitHub 用户名 `tf1993614`；密钥只存本地 secrets 文件（600 权限，gitignore），不进入 Prompt、日志、日报。

### 依赖与运行

- Python 3.11；使用已安装的 requests、PyYAML、beautifulsoup4、lxml、PyMuPDF；不引入 feedparser。
- PyMuPDF 是 AGPL-3.0，仅本机自用；如未来分发需重新评估。
- 单次运行目标 2–4 分钟；采集 30–90 秒，写作 1–2 分钟，推送 1 秒。
- Server酱 免费 5 条/天；一天 1 条日报 + 最多 1 次重试/拆分，额度可控。

## Testing Decisions

- **唯一 seam：CLI 边界。** 测试通过子进程运行 collect、push、doctor，断言输出文件、退出码与 stderr；不导入内部函数、不测私有实现。
- **测试不碰网络。** collect 支持 `--fixtures`，从录制的 HTTP 响应目录读取 PubMed XML、EPMC JSON、arXiv RSS/Atom、Research Square RSS、GitHub JSON、README、PDF/XML 全文；`--now` 固定时间，避免时区与日期漂移。
- **collect 测试**：给定 fixture 配置，断言候选池的 id 集合、跨源去重（同一 DOI 只出现一次）、G2 ≤4、非空组至少 1 条、arXiv 只取 `announce_type=new`、Research Square 摘要被读入。
- **push 测试**：`--dry-run` 输出 ServerChan payload；断言 title 长度、markdown 内容、超长拆分、密钥脱敏、pending 写入、无新内容时默认发送提示且 `send_empty=false` 时跳过。
- **doctor 测试**：`--fixtures` 下所有检查通过时退出 0；缺 key/坏配置/通道 4xx 时退出非零并给出具体项。
- **config 测试**：空 topics、坏 YAML、缺 GitHub token 时，CLI 在发请求前失败。
- **测试工具**：pytest；fixture 文件按源分目录；断言 JSON 字段而不是整段字符串。
- **Prior art**：仓库目前没有代码，无既有测试范式；沿用 Python CLI 的 subprocess + fixture 模式，保持一个 seam。
- **完成标准**：`pytest` 全绿；`collect --fixtures` 产出符合契约的候选池；`push --dry-run` 产出可读的 ServerChan payload；`doctor` 在缺凭据时明确报错。

## Out of Scope

- 订阅/付费全文的抓取与分发；只做 OA 全文。
- 爬期刊官网、Research Square 官方 API 或其他反爬站点。
- 个人微信协议逆向、公众号模板消息、企微应用消息（V1 只做 Server酱）。
- 多用户、账号体系、Web UI、移动端 App。
- 额外的 LLM API、embedding、向量数据库、语义重排。
- V1 的反馈闭环、每周回顾、用户评分学习。
- Cursor、Windsurf、Aider、OpenHands 等其他 AI 编程工具的发现（先观察一周再决定）。
- G6 占用 3+7 的论文席位。
- 自动修改任务卡 cron 之外的看板配置。
- 非中文日报、非 Server酱 的推送通道。

## Further Notes

- 数据源选择的原因见 `docs/adr/0001-literature-source-strategy.md`：PubMed 主源、Europe PMC 补充、OpenAlex/S2 不做发现主源。
- 完整决定见 `docs/decisions.md`；术语见 `GLOSSARY.md`；调研证据见 `docs/research/`。
- 实现前仍缺：Server酱 SendKey、GitHub token。SendKey 与 token 只放本地 secrets 文件，不要贴进对话。
- 首轮验收建议先跑 `doctor` + `collect --fixtures` + 一次真实 dry-run，再接任务卡定时。
- 运行两周后人工看 10 期，再决定是否加 Cursor/Windsurf/Aider、是否加模型名（scGPT/Geneformer 等）、是否调整 G2 配额。

## Amendment 2026-10-23（Issue 11）

- 测试 seam 增加一个窄例外：`tests/test_journal_filter.py` 直接断言 PubMed 的
  `[Journal]` 与 Europe PMC 的 `JOURNAL:` 查询串，因为 fixture 回放不会构造 live
  查询；其余行为仍通过 CLI 子进程测试。`journal_match` 作为候选池新键记录在
  “候选池与模型契约”中；空名单时它为 `false`，`score` 不变。
- 白名单名称按来源报告的 `venue` 做大小写不敏感的完整匹配；PubMed 的 `[Journal]`
  对含括号、方括号、`&` 等特殊字符的期刊名可能需要去掉这些字符后再检索，因此
  配置里的名称应与来源实际报告的标题一致，必要时按 PubMed 的帮助调整。
