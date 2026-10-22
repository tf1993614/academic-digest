# 预印本平台与期刊官网：可编程检索 / RSS / API 能力调研

- 调研日期：2026-10-22（Asia/Shanghai）
- 实测环境：本机（中国大陆网络），Linux + curl 8.x，无代理。所有 HTTP 状态码、响应片段、耗时均为本次真实抓取结果。
- 目标：为"每日学术论文自动推送"系统判断每个来源能否做**每日增量抓取**，以及是否需要 key / 付费 / 是否只能本地过滤。

---

## TL;DR

1. **只有 3 个来源真正支持"服务端关键词 + 日期"双过滤**：arXiv API、Europe PMC REST、ScienceDirect/Springer/IEEE 这类需 key 的商业 API。其余绝大多数只能"按日期/目次拉全量 → 本地关键词过滤"。
2. **Europe PMC 是预印本聚合的最优解**：`SRC:PPR` 一个查询覆盖 bioRxiv、medRxiv、Research Square、ChemRxiv、SSRN、Preprints.org（合计 126.8 万条），支持 `PUBLISHER:` 精确限定、`FIRST_PDATE:` 日期区间、`sort=P_PDATE_D desc`，返回摘要，无需 key，实测 2.4 秒响应，索引延迟仅 1–2 天。**ChemRxiv / SSRN / Preprints.org / TechRxiv 官网在本机被 Cloudflare 全站 403，只能走 Europe PMC。**
3. **arXiv 的"新论文"判定要小心**：API 的 `<published>` 是 v1 投稿时间（UTC），不是公告时间；公告按美东 14:00 截断、20:00 发布，周五~周一合并。若只要"本次公告新增"，用 `https://rss.arxiv.org/rss/<cat>` 更准——`<description>` 里直接写着 `Announce Type: new`。
4. **期刊 RSS 几乎都不含摘要**：Nature（RSS1.0）的 `<content:encoded>` 只有"引用行+标题"；Science/NEJM/PNAS 的 `<description>` 只有卷期页码；只有 Lancet（135–955 字符）和 Cell Press（约 347 字符）带正文摘要节选。要摘要必须回抓落地页或走付费 API。
5. **需要 key 的**：Elsevier ScienceDirect API（无 key 401）、Springer Nature API（无 key 401）、IEEE Xplore API（无 key 403 `Developer Inactive`）、Wiley TDM（无 token 400）。四者都需要注册审批，且多为机构订阅绑定。
6. **明确不可用（付费/审批/反爬）**：Research Square 官方 JSON API 要填表申请 token（官方自己建议改用 Europe PMC/Crossref）；ChemRxiv、SSRN、Preprints.org、TechRxiv 在本机直接 403；Wiley 官网页面级抓取也被 Cloudflare 挡。
7. **意外收获**：Research Square 的 `https://www.researchsquare.com/rss.xml` 是一个**含完整 `<abstract>` 和创建时间戳**的全站 RSS（1000 条 ≈ 最近 3 天），可作免费增量源。

---

## 逐源事实

### 1. arXiv API ✅ 完全可用（推荐指数 ★★★★★）

**端点**：`https://export.arxiv.org/api/query`
注意：`http://` 会 **301 跳转**到 https，脚本必须跟随重定向（实测 `HTTP:301 size:0` → 跟随成功后 `HTTP:200`）。

**query 语法（字段前缀）** —— 官方 `user-manual` 原文表格：

| prefix | explanation |
|:--|:--|
| `ti` | Title |
| `au` | Author |
| `abs` | Abstract |
| `co` | Comment |
| `jr` | Journal Reference |
| `cat` | Subject Category |
| `rn` | Report Number |
| `id` | Id（推荐改用 `id_list`） |
| `all` | All of the above |

布尔运算符只有三个：`AND`、`OR`、`ANDNOT`（没有 `NOT`，也没有括号分组保证；`ANDNOT` 用于排除）。

**submittedDate 日期过滤** —— 官方格式 `[YYYYMMDDTTTT+TO+YYYYMMDDTTTT]`，`TTTT` 是 **GMT 的 24 小时制到分钟**。
实测请求：

```
https://export.arxiv.org/api/query?search_query=cat:cs.LG+AND+submittedDate:%5B202610150000+TO+202610220000%5D&sortBy=submittedDate&sortOrder=descending&start=0&max_results=3
```

真实返回（节选）：

```xml
<title>arXiv Query: search_query=cat:cs.LG AND submittedDate:"202610150000 TO 202610220000"&amp;id_list=&amp;start=0&amp;max_results=3</title>
<updated>2026-10-22T04:58:54Z</updated>
<opensearch:itemsPerPage>3</opensearch:itemsPerPage>
<opensearch:totalResults>1373</opensearch:totalResults>
```

→ cs.LG 一周 1373 篇，说明**不做关键词收窄的话每日约 200 篇/大类**，必须先按 `abs:`/`all:` 收窄或本地过滤。

**sortBy**：官方支持 `relevance` / `lastUpdatedDate` / `submittedDate`，配 `sortOrder=ascending|descending`。实测 `sortBy=submittedDate&sortOrder=descending` 返回结果按 `2026-10-21T17:59:14Z → 17:58:06Z → 17:57:19Z` 严格降序，可用。

**分页**：`start`（0 基）+ `max_results`。官方限制：**单次最多 2000 条，总量上限 30000 条**，超过返回 HTTP 400；建议 >1000 条就收窄查询。实测 `start=100&max_results=2` 正确返回 `startIndex=100`、`totalResults=294832`（cs.LG 全量），无截断。

**速率限制（官方 Terms of Use 原文）**：

> "When using the legacy APIs (including OAI-PMH, RSS, and the arXiv API), make no more than one request every three seconds, and limit requests to a single connection at a time."

即 **1 请求 / 3 秒、单连接串行**，不是"建议"而是 ToU 条款；同时 ToU 明确允许"build notification services"，本项目用途合规。

**Atom 字段**（实测一条完整 entry）：

```xml
<entry>
  <id>http://arxiv.org/abs/2610.30132v1</id>
  <title>LongZero: Enhancing Long-Context Reasoning in LLMs from Zero Data</title>
  <updated>2026-10-21T17:59:14Z</updated>
  <link href="https://arxiv.org/abs/2610.30132v1" rel="alternate" type="text/html"/>
  <link href="https://arxiv.org/pdf/2610.30132v1" rel="related" type="application/pdf" title="pdf"/>
  <summary>Reinforcement learning (RL) is an effective way ...</summary>
  <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
  <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  <published>2026-10-21T17:59:14Z</published>
  <arxiv:comment>Code and data are available at https://github.com/zhennan1/LongZero</arxiv:comment>
  <arxiv:primary_category term="cs.CL"/>
  <author><name>Zhennan Wan</name></author>
  ...
</entry>
```

可稳定拿到：`title`、`summary`（=摘要全文）、`author/name`（多作者）、`category`（**全部**交叉分类）、`arxiv:primary_category`（主分类）、`arxiv:comment`、`arxiv:journal_ref`、`arxiv:doi`、`published`、`updated`、abs/pdf 链接。**没有** DOI 强制字段、没有引用数、没有公告时间戳。

**公告时间 vs 提交时间（关键坑）**
- `<published>` = **v1 投稿时间（UTC）**；`<updated>` = 最后一次版本时间。二者都不是"公告时间"。
- 官方 availability 页的公告时刻表（美东时间）：

| Submissions received between (Eastern US) | Will be announced (Eastern US) |
|:--|:--|
| Mon 14:00 – Tue 14:00 | Tue 20:00 |
| Tue 14:00 – Wed 14:00 | Wed 20:00 |
| Wed 14:00 – Thu 14:00 | Thu 20:00 |
| Thu 14:00 – Fri 14:00 | **Sun 20:00** |
| Fri 14:00 – Mon 14:00 | **Mon 20:00** |

  且"typically posted publicly Sunday through Thursday, with no announcements Friday or Saturday"，另有 2026 年节假日 defer 列表。
- 官方手册："new articles are only available to the API on the midnight *after* the articles were processed"，`<updated>` 反映查询当天午夜，**同一 query 一天调一次就够，必须缓存**。
- 推论：周五~周日投稿的论文会在周一 20:00 一起公告，但 `published` 仍显示周五/周六的日期 → **按 `submittedDate` 回溯必须至少回看 3–4 天**，否则周一漏采。

**"只要新论文"的正确做法（两条路）**
1. API 路：`search_query=cat:cs.LG+AND+submittedDate:[T-4d+TO+T]`，再用本地 DB 按 `id`（去掉版本号）去重；注意会同时带出 `replace`（新版本），只能用 `updated != published` 判定"这次是新版本"。
2. RSS 路（更准）：`https://rss.arxiv.org/rss/cs.LG` 实测 `HTTP:200 size:809924`，379 个 `<item>`：

```xml
<lastBuildDate>Thu, 22 Oct 2026 04:00:11 +0000</lastBuildDate>
<pubDate>Thu, 22 Oct 2026 00:00:00 -0400</pubDate>
<skipDays><day>Saturday</day><day>Sunday</day></skipDays>
<item>
  <title>To Keep or Not to Keep: Learning KV Cache Retention in Disaggregated LLM Serving Systems</title>
  <link>https://arxiv.org/abs/2610.28637</link>
  <description>arXiv:2610.28637v1 Announce Type: new
Abstract: Disaggregated \textsc{LLM} serving separates prefill and decode ...</description>
</item>
```

`Announce Type:` 取值 `new` / `cross` / `replace`，**可在 feed 层直接筛掉 replace**，且 `<description>` 自带摘要全文。缺点：一个 feed 只覆盖一个分类，cs.LG 单日 379 条（含 cross-list），要精确按关键词还得本地过滤。

---

### 2. bioRxiv / medRxiv API ✅ 可用，但**没有关键词检索**

**端点格式（官方 api.biorxiv.org 原文）**：
`https://api.biorxiv.org/details/[server]/[interval]/[cursor]/[format]`
其中 `interval` 三选一：
1. 两个 `YYYY-MM-DD` 日期用 `/` 分隔（+ 可选 `cursor`，默认 0）；
2. 一个数字 N = 最近 N 篇；
3. 数字 + `d` = 最近 N 天。

**单次条数上限**：`/details` **每页 30 篇**（`/pubs` 与 `/pub` 每页 100 篇）。**分页**靠 `cursor` 累加 30。

**实测：单日 bioRxiv**

```
GET https://api.biorxiv.org/details/biorxiv/2026-10-20/2026-10-20/0
HTTP:200 size:62695 time:8.36s
messages: [{"status":"ok","category":"all","interval":"2026-10-20:2026-10-20","cursor":0,
            "count":30,"count_new_papers":"221","total":"237"}]
collection len: 30
```

字段键：`title, authors, author_corresponding, author_corresponding_institution, doi, date, version, type, license, category, jatsxml, abstract, published, server`
样例值：`{"doi":"10.64898/2026.10.16.759679","date":"2026-10-20","version":"1","type":"new results","category":"neuroscience","published":"NA","server":"bioRxiv"}`

**每日量级（实测，非估算）**：

| 区间 | count_new_papers | total |
|:--|--:|--:|
| bioRxiv 2026-10-19 单日 | 233 | 285 |
| bioRxiv 2026-10-20 单日 | 221 | 237 |
| bioRxiv 2026-10-19 → 10-21 | 638 | 763 |
| bioRxiv 2026-10-18 → 10-22 | 708 | 866 |
| **medRxiv 2026-10-20 单日** | **57** | **71** |

月度口径（`https://api.biorxiv.org/sum/m`，注意 JSON 顶层键是 `"bioRxiv content statistics"` 而不是 `collection`）：

```json
{"month":"2026-09","new_papers":5049,"new_papers_cumulative":352769,"revised_papers":1825,...}
```

→ bioRxiv **约 200–290 篇/工作日（含修订）**，月均新增 4 300–5 200 篇 ≈ 150 篇/日；medRxiv 约 60–90 篇/日。
抓全量成本：bioRxiv 237/30 ≈ **8 次请求/天**，medRxiv 71/30 ≈ **3 次请求/天**，完全可接受。

**是否有官方关键词检索？没有。** `api.biorxiv.org` 只提供：
- `/details`、`/pubs`、`/pub`、`/publisher/[prefix]`、`/funder/[server]/[interval]/[ROR]`、`/sum/[m|y]`、`/usage/[m|y]/[server]`；
- 唯一的筛选参数是 **`?category=cell_biology`**（受试学科分类，可用下划线或 URL 编码），这是**学科枚举**，不是自由文本检索。

官方原文：`"These date range endpoints will also accept a querystring paramater for subject category... e.g. ...?category=cell_biology"`。

→ **只能"按日期拉全量 → 本地对 title+abstract 做关键词/正则/向量过滤"**。`abstract` 字段是全文摘要，本地过滤质量足够。

**/pubs 端点**（预印本→正式发表映射，可用于"已发表"标记）：`https://api.biorxiv.org/pubs/[server]/[interval]/[cursor]`，每页 100，字段含 `biorxiv_doi, published_doi, published_journal, preprint_title, preprint_category, preprint_date, published_date, ...`。

---

### 2b. Europe PMC ✅ 预印本关键词检索的唯一免费正解（推荐指数 ★★★★★）

**端点**：`https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=...&format=json&pageSize=...&resultType=core`

**关键：`SRC:PPR` 限定预印本 + `PUBLISHER:"<平台名>"` 限定平台 + 自由文本关键词**。实测（`--data-urlencode` 传 query）：

```bash
curl -s "https://www.ebi.ac.uk/europepmc/webservices/rest/search" \
  --get --data-urlencode 'query=SRC:PPR AND PUBLISHER:"bioRxiv" AND FIRST_PDATE:[2026-10-18 TO 2026-10-22]' \
  --data 'format=json&pageSize=5&sort=P_PDATE_D desc&resultType=lite'
```

返回：

```
HTTP:200
hitCount: 667
2026-10-20 | preprint | Design of synthetic activators for programmable gene express
2026-10-20 | preprint | PDGFRα-directed fibroblast-homing peptides for targeted deli
...
```

**各平台收录量（实测 hitCount）**：

| 查询 | hitCount |
|:--|--:|
| `SRC:PPR`（全部预印本） | **1 267 834** |
| `SRC:PPR AND PUBLISHER:"Research Square"` | 487 481 |
| `SRC:PPR AND PUBLISHER:"Preprints.org"` | 132 512 |
| `SRC:PPR AND PUBLISHER:"medRxiv"` | 90 706 |
| `SRC:PPR AND PUBLISHER:"SSRN"` | 17 659 |
| `SRC:PPR AND PUBLISHER:"ChemRxiv"` | 8 952 |
| `SRC:PPR AND PUBLISHER:"arXiv"` | 7 866 |
| `SRC:PPR AND PUBLISHER:"bioRxiv"`（10-18~10-22 区间） | 667（区间内） |

**关键词 + 平台 组合实测**：`("graph neural network") AND SRC:PPR` → `hitCount: 1083`，返回 `source: "PPR"`，`bookOrReportDetails.publisher: "bioRxiv"`，含 `abstractText`、`firstPublicationDate`、`doi`、`fullTextUrlList`。

**时效性实测**：`SRC:PPR` 按 `P_PDATE_D desc` 排序，最新记录 `firstPublicationDate = 2026-10-20`（今天是 10-22）→ **索引延迟约 1–2 天**。做"每日推送"需接受 T-2 的延迟，或用 bioRxiv 官方 API 补当天。

**其他要点**：无 key、无需注册；`resultType=core` 才带 `abstractText`；分页用 `cursorMark`（响应里有 `nextCursorMark`）而非 page 参数翻深页；`DOI:10.21203*` 这种前缀通配可用但只对 DOI 字段生效。

---

### 3. Research Square ⚠️ 官方 API 需申请，但 RSS 意外好用

**官方口径（来自 `https://www.researchsquare.com/request-api` 页面正文，实测 HTTP 200）**：

> "Request unrestricted access to our API. Research Square preprints are published under a CC-BY 4.0 license... Our preprints are also available at **Europe PMC and Crossref under DOI prefix 10.21203**. Researchers looking to analyze our preprints would be best served using one of those sources. We also provide a JSON API of the content on our platform with additional metadata if the Crossref or Europe PMC APIs do not satisfy your needs. Please fill out the below form to be granted an access token that will allow you to bypass our rate-limits..."

→ **官方明确建议第三方改用 Europe PMC / Crossref**；自带 API 要填表拿 token，不是公开可编程接口。

**反爬声明（`robots.txt` 实测）**：`Disallow: /api/`，并且对 `GPTBot / ClaudeBot / anthropic-ai / CCBot / Bytespider / PerplexityBot / Google-Extended` 等一律 `Disallow: /`。**不要爬 `/api/`**。

**可用替代 1：全站 RSS（实测非常好用）**

```
GET https://www.researchsquare.com/rss.xml
HTTP:200 type:text/xml;charset=UTF-8 size:2448813
```

- 共 **1000 个 `<item>`**，文件 2.45 MB；
- 时间跨度：`created on 2026-10-21 23:03:00`（最新）→ `created on 2026-10-19 09:55:14`（最旧）≈ **最近 3 天、约 330 篇/天**；
- 每条含 `<title> <link> <description> <doi> <abstract>`：

```xml
<item>
  <title>Rethinking University Admission: Students&amp;rsquo; Perceptions of ...</title>
  <link>https://www.researchsquare.com/article/rs-11101782/latest</link>
  <description>An article created on 2026-10-21 23:03:00</description>
  <doi>https://doi.org/10.21203/rs.3.rs-11101782/v1</doi>
  <abstract>The study examines students&amp;rsquo; perceptions of the General, Science &amp; Technology (GST)
  integrated admission system ...</abstract>
</item>
```

→ **`<abstract>` 是摘要全文，`<description>` 里的 `created on` 可解析成日期做增量**。这是"无 key、有摘要、可增量"的稀有组合，缺点是只有时间窗（滚动 3 天），必须每天跑。

**可用替代 2：sitemap**。`https://www.researchsquare.com/sitemap.xml`（HTTP 200）是 sitemapindex，指向 `sitemap0.xml ... sitemapN.xml`；实测 `sitemap0.xml` 只有 25 个 URL 且全是静态页（`lastmod 2020-05-04`）。**文章级 sitemap 分布在后面的分片里，本次未逐个核实**（标注：未验证）。

**结论**：Research Square 做"官方 API"路线 = 需申请 + 可能限流；做"RSS 路线" = 立刻可用且带摘要；做"Europe PMC 路线" = 官方推荐，可关键词检索但延迟 1–2 天。**推荐 RSS + Europe PMC 双轨**。

---

### 4. ChemRxiv / SSRN / Preprints.org / TechRxiv / EarthArXiv

四个站点的官网在本机**全部被 Cloudflare "Just a moment..." 挑战页拦死**（HTTP 403，body 为 `<title>Just a moment...</title>`，带 `challenges.cloudflare.com` 的 CSP）。已试过浏览器 UA，无效。

| 站点 | 实测结果 | 结论 |
|:--|:--|:--|
| **ChemRxiv** | `/engage/chemrxiv/rss`、`/engage/chemrxiv/public-api/v1/items?limit=2`、`/engage/chemrxiv/public-api/v1/items?term=graphene` 全部 `HTTP:403 size:5xxx` Cloudflare；`chemrxiv.org/rss` → `HTTP:404 size:21` | 官网不可编程访问。ChemRxiv 平台确实有 `public-api/v1` 风格接口（路径存在但被 CF 挡），**是否有官方文档页面：未验证**（页面同样 403）。→ 走 Europe PMC `PUBLISHER:"ChemRxiv"`（8 952 条） |
| **SSRN** | `https://www.ssrn.com/` `HTTP:000`（连接超时/被重置，time 25s）；`https://papers.ssrn.com/sol3/papers.cfm?abstract_id=...` `HTTP:403` Cloudflare；`https://api.ssrn.com/` `HTTP:403` Cloudflare | **不可用**。无公开 API、无 RSS。→ Europe PMC `PUBLISHER:"SSRN"`（17 659 条） |
| **Preprints.org** | `/`、`/rss`、`/rss/all` 全部 `HTTP:403`（body 374–382 字节，CF 拦截） | 官网不可用；EPMC 收录 132 512 条，量最大 |
| **TechRxiv** | `/rss` → `HTTP:404 size:21`（`Not Found`）；`/` → `HTTP:403` Cloudflare | 无 RSS 路径；站点被 CF 挡。IEEE 系，本机基本不可用 |
| **EarthArXiv** | `https://eartharxiv.org/` `HTTP:200 size:11109`；首页含 `<a href="/rss/">` 与 `https://eartharxiv.org/rss/preprints/`；**OSF API 已失效**：`https://api.osf.io/v2/preprints/eartharxiv/?page[size]=2` → `HTTP:404`，body `{"errors":...}` | 有 RSS（`/rss/preprints/`，**内容本次未抓取，标注未验证**）；EarthArXiv 已迁出 OSF，老的 OSF API 路线作废 |

> 备注：以上 403 是 Cloudflare 的 bot/地域判定结果，**不排除**换出口 IP 或加浏览器指纹后可用；但在"本机每日自动跑"的前提下应当视为不可用，并准备 Europe PMC 作为唯一通道。

---

### 5. 期刊官网 RSS 与商业 API

#### 5.1 能直接用的 RSS（全部实测 HTTP 200）

| 期刊 | Feed URL | 格式 | 条数 | 摘要 |
|:--|:--|:--|--:|:--|
| **Nature** | `https://www.nature.com/nature.rss` | RSS 1.0 / RDF | 75 | ❌ `<content:encoded>` 仅"引用行+标题"（88–424 字符） |
| **Science**（新闻） | `https://www.science.org/rss/news_current.xml` | RSS 1.0 | 10 | 仅导语（57–149 字符） |
| **Science**（目次） | `https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science` | RSS 1.0 | 39 | ❌ 仅卷期页码 |
| **Cell Press** | `https://www.cell.com/cell/current.rss` | RSS 1.0 | 22 | ⚠️ 约 347 字符的编辑导读 |
| **NEJM** | `https://www.nejm.org/action/showFeed?type=etoc&feed=rss&jc=nejm` | RSS 1.0 | 51 | ❌ 仅卷期页码（48–88 字符） |
| **Lancet** | `https://www.thelancet.com/rssfeed/lancet_current.xml` | RSS 1.0 | 34 | ✅ `<description>` 135–955 字符，正文摘要节选 |
| **PNAS** | `https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas` | RSS 1.0 | 97 | ❌ 仅卷期引用（84–344 字符） |

实测细节：

```xml
<!-- nature.rss 单条：content:encoded = 引用 + 标题，无摘要 -->
<item rdf:about="...">
  <title>&lt;i&gt;De novo&lt;/i&gt; design of enantioselective artificial metallo...</title>
  <content:encoded>Nature, Published online: 21 October 2026; doi:10.1038/s41586-026-11317-6
  De novo design of enantioselective artificial metalloenzyme photocatalysts</content:encoded>
  <prism:doi>10.1038/s41586-026-11317-6</prism:doi>
  <dc:date>2026-10-21</dc:date>
</item>
```

```xml
<!-- Lancet 单条：description 是真摘要节选 -->
<title>[Editorial] Rethinking threats to human survival</title>
<description>Much health advocacy is driven by single-issue activism. Communities with a common
interest—from AIDS to child health, climate to tobacco control—focus intensely on their own domain...</description>
```

```xml
<!-- Science 目次单条：只有卷期页码 -->
<title>An elegy for the unsung world-builders</title>
<description>Science, Volume 394, Issue 6821, Page 278-278, October 2026.</description>
```

**更新节奏**：
- Nature：75 条覆盖 `2026-10-16` → `2026-10-21`，即**连续在线发布**（Published online），每日多次，适合日更。
- Science 目次 feed：39 条 `pubDate` **全部等于 `2026-10-15T06:00:12Z`** → 这是**期次级 ETOC（周更）**，不是逐篇发布，做每日增量会漏掉 First Release。
- NEJM：`pubDate` 2026-10-14 → 10-17，周更目次。
- Lancet：2026-10-10 / 10-11，周更。
- PNAS：2026-10-05 → 10-13，周更（周一发布）。
- Cell：22 条，item 内**无 `pubDate`**（实测为空），只有 `prism` 相关字段，且实测 `publicationDate` 未取到值 → 日期要靠落地页或 `dc:date` 兜底（**未逐条验证**）。

**能否"按关键词"检索？** 上述 RSS **全部不支持**关键词参数，只能订阅目次后本地过滤。期刊站内的 `?q=` 搜索是 HTML 页面（如 `https://www.nature.com/search?q=...`），可抓但无稳定契约，且多数站点有反爬。

**Feed URL 踩坑记录**：
- `https://www.science.org/action/showFeed?...&jc=science_first_release` → **HTTP 404**（First Release 独立 feed 路径本次未找到，标注未验证；Science RSS 索引页 `https://www.science.org/content/page/science-journals-rss-feeds` 返回 `HTTP:403` 被 CF 挡，无法确认完整清单）。
- `https://www.cell.com/cell/rss` → 403；正确路径是 `/cell/current.rss`。
- Wiley：见下。

#### 5.2 需要 key / 审批的商业 API（全部实测无凭证时的状态码）

| 服务 | 端点 | 无凭证实测 | 说明 |
|:--|:--|:--|:--|
| **Elsevier ScienceDirect API** | `https://api.elsevier.com/content/search/sciencedirect?query=graphene&count=1` | `HTTP:401 size:97` | 需 API key + 机构订阅（ entitlement），**支持服务端关键词与日期** |
| **Springer Nature API** | `https://api.springernature.com/meta/v2/json?q=graph%20neural%20network&p=1` | `HTTP:401 size:234` | 需 api_key；含 Nature 系列元数据；有免费额度 |
| **IEEE Xplore API** | `https://ieeexploreapi.ieee.org/api/v1/search/articles?queryText=graphene&max_records=1` | `HTTP:403`，body `<h1>Developer Inactive</h1>` | 需 `apikey=`，免费注册即可，有日配额 |
| **Wiley TDM** | `https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1002%2Fadv.202501234` | `HTTP:400 size:0` | 需 `Wiley-TDM-Client-Token` 头（机构 TDM 协议）；无 token 直接 400 |

> 四个 API 的**配额、审批时长、是否要求机构 IP**：本次**未验证**（需登录门户才能看，标注为待确认）。

#### 5.3 Wiley / ACM

- **Wiley**：`https://onlinelibrary.wiley.com/journal/10974636` → `HTTP:403`（Cloudflare）；`https://onlinelibrary.wiley.com/library-info/resources/rss-feeds` → `HTTP:403`；`/feed/10.1002/(ISSN)1097-4636/toc` → `HTTP:404 "Missing resource /feed/..."`；`/feed/10.1002/(ISSN)1097-4636` → `404`；`/action/showFeed?jc=1097-4636&type=etoc&feed=rss` → `404`（空 body）；`?ui=0&mi=0&ai=0&jc=...` 亦 404。→ **Wiley 正确的 RSS 路径本次未找到（标注未验证）**，且域名本身被 CF 拦。**结论：Wiley 每日抓取暂不可行**，除非走 TDM token。
- **ACM**：`https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=cacm` → `HTTP:404`，但 body 返回了一个**合法的空 RDF channel**（`<rdf:RDF ...><channel rdf:about=...`，`items=0`）。说明该路径被识别但 `jc=cacm` 参数不对；**正确 ACM feed 参数未验证**。

---

## 覆盖矩阵

| 来源 | 类型 | 服务端关键词 | 服务端日期过滤 | 含摘要 | 鉴权 | 速率限制 | 每日增量可行性 | 优先级 |
|:--|:--|:--:|:--:|:--:|:--|:--|:--|:--:|
| **arXiv API** | Atom API | ✅ `all:/ti:/abs:` | ✅ `submittedDate` | ✅ `<summary>` 全文 | 无 | **1 req/3s，单连接**（ToU） | ✅ 优（注意公告时区/回看 4 天） | **P0** |
| **arXiv RSS** | RSS 2.0 | ❌ | ❌（只当日） | ✅ | 无 | 同上 | ✅ 优（可区分 new/replace） | **P0** |
| **bioRxiv API** | JSON | ❌（仅 `?category=`） | ✅ 日期区间 | ✅ `abstract` | 无 | 文档未给明确值（30/页；实测 8.4s/页） | ✅ 优（8 页/天） | **P0** |
| **medRxiv API** | JSON | ❌（仅 `?category=`） | ✅ | ✅ | 无 | 同上 | ✅ 优（3 页/天） | **P0** |
| **Europe PMC** | REST JSON | ✅ 全字段 | ✅ `FIRST_PDATE:[.. TO ..]` | ✅ `resultType=core` | 无 | 未明示（实测 2.4s/请求） | ✅ 良（延迟 1–2 天） | **P0** |
| **Research Square RSS** | RSS 2.0 | ❌ | ❌（但含 `created on`，可本地判定） | ✅ `<abstract>` 全文 | 无 | 未明示（2.4 MB/次） | ✅ 良（滚动 1000 条≈3 天） | **P1** |
| Research Square API | JSON | ? | ? | ? | **需填表申请 token** | 有 rate-limit（官方称 token 可绕过） | ⚠️ 需审批 | P3 |
| **ChemRxiv** | — | — | — | — | — | — | ❌ 官网 403（走 EPMC） | P2（经 EPMC） |
| **SSRN** | — | — | — | — | — | — | ❌ 403/超时（走 EPMC） | P2（经 EPMC） |
| **Preprints.org** | — | — | — | — | — | — | ❌ 403（走 EPMC） | P2（经 EPMC） |
| **TechRxiv** | — | — | — | — | — | — | ❌ 403 | P3 |
| **EarthArXiv** | RSS | ❌ | ❌ | 未验证 | 无 | 未明示 | ⚠️ feed 存在，内容未验证 | P3 |
| **Nature RSS** | RSS 1.0 | ❌ | ❌ | ❌ | 无 | 未明示 | ✅ 良（本地过滤标题） | **P1** |
| **Science RSS** | RSS 1.0 | ❌ | ❌ | ❌ | 无 | 未明示 | ⚠️ 期次级，需配合 First Release | P2 |
| **Cell Press RSS** | RSS 1.0 | ❌ | ❌ | ⚠️ 导读 347 字符 | 无 | 未明示 | ⚠️ 期次级 | P2 |
| **NEJM RSS** | RSS 1.0 | ❌ | ❌ | ❌ | 无 | 未明示 | ⚠️ 期次级 | P2 |
| **Lancet RSS** | RSS 1.0 | ❌ | ❌ | ✅ 节选 | 无 | 未明示 | ✅ 良 | **P1** |
| **PNAS RSS** | RSS 1.0 | ❌ | ❌ | ❌ | 无 | 未明示 | ⚠️ 周更 | P2 |
| **Elsevier SD API** | REST | ✅ | ✅ | ✅ | **key + 订阅** | 有配额（未验证） | ✅ 优（若有权限） | P1（有条件） |
| **Springer Nature API** | REST | ✅ | ✅ | ✅ | **key** | 有配额（未验证） | ✅ 优（若有权限） | P1（有条件） |
| **IEEE Xplore API** | REST | ✅ | ✅ | ✅ | **key（免费注册）** | 日配额（未验证） | ✅ 优（若有 key） | P1（有条件） |
| **Wiley TDM** | REST | ⚠️ | ⚠️ | ⚠️ | **TDM token + 机构协议** | 未验证 | ❌ 当前不可行 | P3 |
| **ACM** | RSS(?) | ❌ | ❌ | ❌ | 无 | 未明示 | ❌ 参数未验证 | P3 |

---

## 推荐抓取组合

**分层策略**：P0 核心（无 key、稳定、覆盖 90% 需求）→ P1 补充 → P2/P3 以后再说。

- **P0（立刻做）**：arXiv（API+RSS）、bioRxiv/medRxiv（API）、Europe PMC（SRC:PPR，兜住 ChemRxiv/SSRN/Preprints.org）
- **P1（第二批）**：Research Square RSS、Nature RSS、Lancet RSS；若有机构权限再接 Elsevier/Springer/IEEE API
- **P2/P3**：Science/Cell/NEJM/PNAS 目次级 RSS（当"周报"用，不当"日更"用）

### 配方 1：arXiv 每日 cs.LG + q-bio 新论文（关键词收窄 + RSS 判定新增）

```python
import time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

ARXIV = "https://export.arxiv.org/api/query"
CATS  = ["cs.LG", "q-bio.NC"]
KW    = '(abs:"graph neural network" OR abs:"foundation model" OR ti:"protein language model")'

def fetch(cat, days=4):
    # submittedDate 是 GMT，格式 YYYYMMDDTTTT
    end   = time.strftime("%Y%m%d%H%M", time.gmtime())
    start = time.strftime("%Y%m%d%H%M", time.gmtime(time.time() - days*86400))
    q = f"cat:{cat} AND {KW} AND submittedDate:[{start}+TO+{end}]"
    url = (f"{ARXIV}?search_query={urllib.parse.quote(q)}"
           f"&sortBy=submittedDate&sortOrder=descending&start=0&max_results=200")
    req = urllib.request.Request(url, headers={"User-Agent": "AutoAcademicNotification/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        root = ET.fromstring(r.read())
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    out = []
    for e in root.findall("a:entry", ns):
        base_id = e.findtext("a:id", "", ns).rsplit("v", 1)[0]   # 去掉版本号做去重键
        out.append({
            "id":     base_id,
            "title":  " ".join(e.findtext("a:title", "", ns).split()),
            "abstract": " ".join(e.findtext("a:summary", "", ns).split()),
            "published": e.findtext("a:published", "", ns),      # v1 投稿时间(UTC)，非公告时间
            "updated":   e.findtext("a:updated", "", ns),
            "primary":  e.find("x:primary_category", ns).get("term"),
            "cats":     [c.get("term") for c in e.findall("a:category", ns)],
            "is_new_version": e.findtext("a:published", "", ns) != e.findtext("a:updated", "", ns),
        })
    return out

seen = set()
for c in CATS:
    for p in fetch(c):
        if p["id"] in seen or p["is_new_version"]:
            continue          # 跳过已入库 & 跳过 replace
        seen.add(p["id"])
        print(p["published"], p["primary"], p["title"][:80])
    time.sleep(3.5)           # arXiv ToU: 1 req / 3s，单连接
```

配套（更精确的"今日新增"判定）：

```bash
# 每日 20:30 ET 之后跑；Announce Type: new 才是真·首次公告
curl -s https://rss.arxiv.org/rss/cs.LG \
 | python3 -c "
import sys,re,html
t=sys.stdin.read()
for m in re.finditer(r'<item>.*?<link>(.*?)</link>.*?<description>(.*?)</description>', t, re.S):
    link, desc = m.group(1), html.unescape(m.group(2))
    if 'Announce Type: new' in desc:
        print(link, desc.split('Abstract:')[1].strip()[:100])
"
```

### 配方 2：bioRxiv + medRxiv 每日全量 → 本地关键词过滤

```python
import json, time, urllib.request, datetime, re

def biorxiv(server, day):        # day: 'YYYY-MM-DD'
    out, cursor = [], 0
    while True:
        url = f"https://api.biorxiv.org/details/{server}/{day}/{day}/{cursor}"
        with urllib.request.urlopen(url, timeout=90) as r:
            d = json.load(r)
        msg = d["messages"][0]
        out += d["collection"]
        cursor += msg["count"]                       # 每页固定 30
        if cursor >= int(msg["total"]) or msg["count"] == 0:
            break
        time.sleep(1)
    return out

PAT = re.compile(r"(graph neural|transformer|single[- ]cell|CRISPR|LLM|foundation model)", re.I)
day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
for srv in ("biorxiv", "medrxiv"):
    hits = [p for p in biorxiv(srv, day)
            if PAT.search(p["title"] + " " + p["abstract"])]
    print(srv, day, "total-hits:", len(hits))        # bioRxiv ~8 页/天, medRxiv ~3 页/天
```

数据量参考（实测）：`2026-10-20` bioRxiv `total=237`、`count_new_papers=221`；medRxiv `total=71`、`count_new_papers=57`。

### 配方 3：Europe PMC 一把梭（覆盖 ChemRxiv/SSRN/Preprints.org/Research Square）

```bash
curl -s "https://www.ebi.ac.uk/europepmc/webservices/rest/search" \
  --get \
  --data-urlencode 'query=SRC:PPR AND (PUBLISHER:"bioRxiv" OR PUBLISHER:"Research Square"
       OR PUBLISHER:"ChemRxiv" OR PUBLISHER:"SSRN" OR PUBLISHER:"Preprints.org")
       AND ("graph neural network" OR "large language model")
       AND FIRST_PDATE:[2026-10-20 TO 2026-10-22]' \
  --data 'format=json&pageSize=100&resultType=core&sort=P_PDATE_D desc' \
| python3 -c "
import sys,json
d=json.load(sys.stdin); print('hits:',d['hitCount'])
for r in d['resultList']['result']:
    print(r['firstPublicationDate'], r.get('bookOrReportDetails',{}).get('publisher'),
          '|', r['title'][:70])
"
```

### 配方 4（补充）：Nature / Lancet RSS 过滤

```bash
# Nature：RSS1.0，标题在 <title>，摘要在 <content:encoded>（实为引用行，需回抓落地页）
curl -s https://www.nature.com/nature.rss | python3 -c "
import sys,re,html
t=sys.stdin.read()
for it in re.findall(r'<item rdf:about=.*?</item>', t, re.S):
    ti=html.unescape(re.search(r'<title>(.*?)</title>',it,re.S).group(1))
    doi=re.search(r'<prism:doi>(.*?)</prism:doi>',it)
    if re.search(r'neural|protein|climate', ti, re.I):
        print(doi.group(1) if doi else '-', ti[:80])
"
```

---

## 待确认问题

1. **Wiley 正确的 RSS 路径**是什么？（`/feed/10.1002/(ISSN)xxxx`、`/action/showFeed?jc=` 均 404；官方 RSS 帮助页被 Cloudflare 403 挡住，无法取证）如果确认无 RSS，是否只能走 TDM token？
2. **ACM Digital Library 的 RSS 参数**：`dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=cacm` 返回 404+空 RDF，`jc=` 的正确取值未验证。
3. **Science First Release 的独立 feed** 是否存在？`jc=science_first_release` 返回 404；若不存在，Science 的每日增量只能抓 `science.org/toc/...` HTML 或走付费 API。
4. **Elsevier / Springer / IEEE 三家的 key 审批周期、日配额、以及是否强制绑定机构订阅/IP 段** —— 需注册后登录门户确认，本次未验证。
5. **Europe PMC 的官方速率限制**没有在本页找到明确数值（只有"be reasonable"类表述？未核实），当前按 1 req/s 自限。需要查 Europe PMC REST 文档的 rate limit 段。
6. **Research Square `sitemap*.xml` 文章级分片**是否可用于增量（本次只看了 `sitemap0.xml` 静态页）——未验证。
7. **EarthArXiv `https://eartharxiv.org/rss/preprints/`** 是否含摘要、条数、更新频率——未抓取，未验证。
8. **Cloudflare 403 是否纯地域性**：ChemRxiv / SSRN / Preprints.org / TechRxiv / Wiley 在本机全部 403。若生产环境换到海外出口 IP 或加代理，其中部分可能恢复；但依赖代理会让每日任务变脆，建议仍以 Europe PMC 为主通道。
9. **Nature `<content:encoded>` 是否还有其它字段带摘要**：本次确认 content:encoded 只有引用行+标题，摘要必须回抓 `nature.com/articles/<doi>` 落地页（该页 HTML 200 可抓，但需注意 robots 与频率）。
10. **arXiv `<updated>` 与公告日的映射**：官方说 feed 的 `<updated>` 是"查询当天午夜"，但实测返回 `2026-10-22T04:58:54Z`（= 美东 00:58），并非严格午夜；跨时区判定"新一批"时应以 RSS 的 `lastBuildDate`（实测 `04:00:11 +0000`）为准。

---

## 附：本次实测命令与关键状态码速查

```text
arXiv
  http://export.arxiv.org/api/query?...            → 301（必须跟随重定向）
  https://export.arxiv.org/api/query?...           → 200, 6.0s, 3810B
  https://rss.arxiv.org/rss/cs.LG                  → 200, 809924B, 379 items

bioRxiv / medRxiv
  https://api.biorxiv.org/details/biorxiv/2026-10-20/2026-10-20/0   → 200, 8.36s, 62695B, total=237
  https://api.biorxiv.org/details/medrxiv/2026-10-20/2026-10-20/0   → 200, total=71
  https://api.biorxiv.org/sum/m                                     → 200（顶层键 "bioRxiv content statistics"）

Europe PMC
  https://www.ebi.ac.uk/europepmc/webservices/rest/search?...       → 200, 2.47s

Research Square
  https://www.researchsquare.com/rss.xml           → 200, 2448813B, 1000 items
  https://www.researchsquare.com/request-api       → 200（正文说明需申请 token）
  https://www.researchsquare.com/sitemap.xml       → 200（sitemapindex）
  https://www.researchsquare.com/api               → 404 {"error":"notFound"}

被 Cloudflare 拦截（403 "Just a moment..."）
  chemrxiv.org/*（含 public-api、rss）
  ssrn.com / papers.ssrn.com / api.ssrn.com（www.ssrn.com 直接 000 超时）
  preprints.org/*
  techrxiv.org/*
  onlinelibrary.wiley.com/*（含 rss-feeds 帮助页、期刊页）

期刊 RSS（全部 200，RSS 1.0/RDF）
  nature.com/nature.rss                                      75 items, 2026-10-16~10-21
  science.org/action/showFeed?...jc=science                   39 items, 全部 2026-10-15T06:00:12Z
  cell.com/cell/current.rss                                   22 items, 无 pubDate
  nejm.org/action/showFeed?...jc=nejm                         51 items
  thelancet.com/rssfeed/lancet_current.xml                    34 items, description 135~955 字符
  pnas.org/action/showFeed?...jc=pnas                         97 items

商业 API 无凭证
  api.elsevier.com/content/search/sciencedirect   → 401
  api.springernature.com/meta/v2/json             → 401
  ieeexploreapi.ieee.org/api/v1/search/articles   → 403 "Developer Inactive"
  api.wiley.com/onlinelibrary/tdm/v1/articles/... → 400
```
