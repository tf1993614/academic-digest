# 用 PubMed 做主源、Europe PMC 做补充，不用 OpenAlex / Semantic Scholar 做发现

每日增量学术速递需要一个能稳定回答“过去 48 小时新入库了什么”的检索层。2026-10 实测：PubMed 的 `datetype=edat` 是唯一可靠的“入库日期”，摘要免费且无需 key；Europe PMC 一次 `pageSize=1000` 能覆盖 MEDLINE + PMC + 预印本（含 bioRxiv/medRxiv/Research Square），适合补摘要与预印本；OpenAlex 已改为美元额度计费（无 key 每天 $0.10、同 IP 共享，cursor 翻页从第二页起要 key），Semantic Scholar 在本机匿名访问连续 429，Crossref 摘要覆盖率低且限速 1 req/s。因此决定：**PubMed 做发现主源，Europe PMC 做补充与预印本聚合，Crossref 仅补 DOI/期刊元数据，OpenAlex 仅按 DOI 补主题/引用，Semantic Scholar 仅作 TLDR 兜底且 429 即跳过。** 代价是 PubMed 摘要必须用 XML 解析（`efetch` 传 JSON 会静默降级为纯文本），且 Europe PMC 有 1–2 天索引延迟；换来的是不依赖付费额度、不被第三方限流卡住主流程。

**Considered options**：OpenAlex 做主源（否决：额度 + cursor 限制）；Semantic Scholar 做主源（否决：匿名 429）；Crossref 做主源（否决：无摘要）。

**Consequences**：每条论文需要按 DOI > PMID > arXiv ID > 标题哈希去重；Europe PMC 不能单独承担“今天”的新鲜度，必须与 PubMed / arXiv RSS / Research Square RSS 并用。

## Amendment 2026-10-22（Issue 02）

Europe PMC 仍是补充源：与 PubMed 并行查询，使用 `FIRST_PDATE` 短窗口 +
`SRC:MED`/`SRC:PPR`，不单独承担“今天”的新鲜度；合并同一论文时 PubMed 的摘要与
期刊优先，EPMC 只补缺失字段并保留预印本标记与来源。候选 `id` 仍按
DOI > PMID > arXiv ID > 标题哈希；跨源匹配时只要共享任一强标识就视为同一篇论文
（避免一侧缺 DOI 时重复），标题哈希仅在没有强标识时使用。这是对原 Consequences
的细化，不改变“PubMed 主源、EPMC 补充”的判断。

## Amendment 2026-10-22（Issue 03）

预印本来源定案：arXiv 每日新增只认 RSS 的 `announce_type=new`，`replace`（新版本）
与 `cross`（其他分类的重复公告）丢弃，`lookback.arxiv` 至少 4 天以覆盖周五到周一的
合并公告，并用 API 按分类与关键词回看该窗口补漏（跳过 `updated != published`）；
Research Square 只读公开 RSS（官方 API 需申请 token，且 `robots.txt`
禁止 `/api/`），直接使用 `<abstract>`、`<authors>`、`<doi>`；bioRxiv/medRxiv 默认
关闭，开启后按日期区间分页全量拉取并在本地按关键词组过滤。三者都产出预印本标记
（`is_preprint` + `预印本` 标签）并沿用 DOI > PMID > arXiv ID > 标题哈希去重；与
期刊版本共用 DOI 时合并为一条，以已发表版本的摘要与期刊优先且不再标记预印本。
Europe PMC 仍是预印本聚合的补充源，与这些源并行而不是替代它们。

## Amendment 2026-10-22（Issue 04）

候选池排序定案：规则分 = 相关性（组内命中词，标题 ×3、摘要 ×1）+ 新鲜度（运行日
当天 +2、前一天 +1，其余 +0）；按分数降序、日期降序、id 升序排列，固定 fixture 与
`--now` 每次得到相同顺序。截断时先按各组最高分的全局顺序为每个非空组保留一条，再
按全局顺序填充，每组不超过配置的 `max_items`（默认 6，示例配置里 G2 为 4），总数
不超过 `pool.max_items`（默认 30，且不得少于 topics 数量，否则配置校验失败）；
候选不足时不补空条目。日期只精确到年份时按无日期处理（+0，同分排在具体日期
之后）。期刊白名单加分暂缓：
当前没有 `journal_filter` 配置、默认不限期刊，等给出名单后再接入 PubMed/Europe PMC
的 `JOURNAL` 过滤并按白名单加分。这不改变数据源选择，只细化候选池的排序与配额。

## Amendment 2026-10-22（Issue 07）

OA 全文不改变“PubMed 主源、EPMC 补充”的发现策略，只作用于入选日报的论文。全文
解析顺序固定为 Europe PMC `fullTextXML` → arXiv HTML/PDF → bioRxiv/medRxiv/
Research Square 预印本 PDF → Unpaywall 最佳 OA 位置；每个来源一条 `attempt`，全部
失败返回 `no_oa` 而不是异常，日报降级为“仅基于摘要”。Unpaywall 需要联系邮箱，
配置留空时完全跳过该来源；邮箱与请求 URL 不进入候选池、日报或日志。全文只抽取
方法/结果/局限段落，按 4/3/4 段与 4000/3000/2000 字符截断（优先在句号处），
`length` 为保留段落的总字符数；没有显式 Limitations 小节时只从
Discussion/Conclusion 取作者声明的局限，Methods/Results 的顺带提及不提升为局限。
PDF 解析用 PyMuPDF（AGPL-3.0，仅本机自用；分发前需重新评估），HTML 用
beautifulsoup4 + lxml。按标题匹配预印本版本与 DOI→arXiv 交叉检索不在本 issue
内，留给日报契约阶段。

## Amendment 2026-10-22（Issue 08）

日报写作与校验定案：会话模型读候选池后写 `selection.json` 与 `digest.md`，
`digest check --candidates/--selection/--digest` 只读这三个文件并离线校验，不读
配置、不联网、不访问状态库，不合格时退出 1 且只报告第一条违规。selection 固定
`must_read` / `quick_scan` 两级：`must_read` 每条要求 `fulltext` 为 `oa` 或
`abstract_only`、`limitations_source` 含 `model`，`quick_scan` 只能
`abstract_only`；G2 最多 4 篇，除 G2/G6 外候选池中出现的组至少 1 篇，G6 论文最多
1 篇且只能进其它速览，GitHub/G6 不进入 selection。目标为 `must_read = min(3, n)`、
`quick_scan = min(7, n - must_read)`；只有 G2/G6 配额确实堵住剩余候选时才允许
少于目标。日报逐字使用候选 `title`，今日必读用四要素与方法精读（无 OA 时写
“无 OA 全文，仅基于摘要”），其它速览一行一条；`## GitHub` 只放
new/active/releases.starred，`## AI 工具 / Agent Harness` 放 g6 与 g6_releases，
均与 `candidates.github` 逐项对应、为空则省略，页脚覆盖来源状态与候选/入选计数。
全文侧为 Issue 07 补上标题匹配：`fulltext --title` 先对 arXiv API 做精确标题查询，
再查 Europe PMC 的 `TITLE:"…"`；`10.48550/arXiv.<id>` 直接映射 arXiv ID。匹配到的
预印本 DOI / arXiv ID 在 arXiv 与 Unpaywall 之间加入尝试，输出 key 不变，近似标题
一律忽略。契约与固定结构以 Issue 08 的 `## Contract` 为准；本 amendment 不改变
“PubMed 主源、EPMC 补充”的判断，也不新增 config key。
