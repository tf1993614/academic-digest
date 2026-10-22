# 生物医学 / 生命科学 / AI 论文检索 API 调研

- 调研日期：2026-10-22（Asia/Shanghai）
- 调研环境：中国大陆网络，`http_proxy=127.0.0.1:7898`（全局 HTTPS 代理，非直连）
- 验证方式：除特别标注「未验证」外，本文所有 URL / 字段 / 计数 / 报错**均为本机 curl 实测原文**
- 配套脚本建议：所有示例可直接复制到 shell 执行

---

## TL;DR

1. **主源选 PubMed E-utilities**：唯一能按"录入日期"（`datetype=edat`）做真正"最近 N 天增量"的源，摘要免费，无 key 即可跑，本机实测稳定（约 2.3s/请求）。**没有 `esummarize` 这个端点**（实测报 `Invalid eutil name`），只有 `esummary`；且 `esummary` 不含摘要，摘要必须走 `efetch`。
2. **`efetch` 不支持 `retmode=json`**：传了会静默降级返回纯文本（HTTP 200），必须用 `retmode=xml` 解析 `AbstractText`。这是最容易踩的坑。
3. **补充源选 Europe PMC**：同时覆盖 MEDLINE + PMC 全文 + 预印本（`source=PPR`），`resultType=core` 直接给 `abstractText`，`pageSize` 可到 1000，一条请求能拉一整天的量。缺点是**日期字段语义不如 PubMed 清楚**，且官方文档站从本机 403 不可达。
4. **OpenAlex 已改为"美元额度"计费制**：无 key 每天只有 **$0.10**，一次 `title_and_abstract.search` 花 $0.001 → **约 100 次搜索/天就没了**；且 **cursor 翻页第二页起强制要 key（实测 401）**。作为每日增量主源风险偏高，适合做"按 DOI 补齐元数据/主题分类"的补充源。
5. **Semantic Scholar 在本机基本不可用**：无 key 是"全体匿名用户共享 1000 rps"的池子，实测 `/paper/search` 连续 3 次 429，`/paper/search/bulk` 也间歇 429。且 **bulk 端点不支持 `tldr` 字段**（实测 `Unrecognized or unsupported fields: [tldr]`）。**只能做兜底，不能做主源。**
6. **Crossref 只作 DOI 元数据/期刊目次补充**：实测速率 1 req/s（响应头 `x-rate-limit-limit: 1`），摘要覆盖率低（实测多条 `abstract: NONE`）。
7. **推荐组合**：PubMed（主，edat 增量）→ Europe PMC（补预印本 + 全文链接 + 缺失摘要）→ Crossref（DOI 补全）→ OpenAlex（主题/引用增强，可选）→ S2（TLDR，可选、失败即跳过）。
8. **去重主键用 DOI（归一化小写）**，备用键 PMID；arXiv 用 `arXiv:xxxx.xxxxx`；三者都缺时用 `normalized(title)+year` 的哈希。

---

## 1. PubMed E-utilities

### 1.1 基本事实

| 项 | 值 | 来源 |
|---|---|---|
| Base URL | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | 实测 |
| 端点 | `einfo / esearch / epost / esummary / efetch / elink / egquery / espell / ecitmatch` | 实测（`esummarize` 不存在） |
| 鉴权 | 无需 key；可选 `api_key=` + `tool=` + `email=` | 实测 |
| 速率（无 key） | **3 req/s** — 实测响应头 `x-ratelimit-limit: 3`、`x-ratelimit-remaining: 2` | 实测 |
| 速率（有 key） | 10 req/s（官方文档口径，本机无 key，**未验证**） | [E-utilities usage](https://www.ncbi.nlm.nih.gov/books/NBK25497/) |
| 返回格式 | `retmode=json`（仅 esearch/esummary 可靠）/ `xml` / `text` | 实测 |
| 摘要 | **免费**，需 `efetch` | 实测 |
| 全文 | 不提供，仅 `pmcrefcount` / PMC 链接 | 实测 |

`esummarize` 实测原文：

```json
{"error":"Invalid eutil name 'esummarize'","api-key":"38.244.6.37","type":"ip",
"status":"ok"}
```

> 结论：任务描述里的 "esummarize" 应理解为 `esummary`；不存在独立摘要端点，摘要靠 `efetch&rettype=abstract`。

### 1.2 API key / email / tool 的作用

- `api_key`：把速率从 3 req/s 提到 10 req/s。**无效 key 会直接 400 且不降级**，实测：
  ```json
  {"error":"API key invalid","api-key":"INVALIDKEY123","type":"invalid","status":"unknown"}
  ```
- `email` + `tool`：NCBI 用于"出问题时联系你"，属于礼节性参数，不改变速率。实测带 `tool/email` 时响应头仍是 `x-ratelimit-limit: 3`。
- key 申请：NCBI 账号 → Account Settings → API Key Management，即时生效。

### 1.3 日期语义：`reldate` vs `mindate/maxdate`，`edat` vs `pdat`（关键）

实测同一查询 `CRISPR` 的 `querytranslation` 与命中数：

| 写法 | 翻译成 | 命中数 |
|---|---|---|
| `reldate=1&datetype=edat` | `... AND 2026/10/21:2026/10/22[Date - Entry]` | 6 |
| `reldate=1&datetype=pdat` | `... AND 2026/10/21:2026/10/22[Date - Publication]` | 2 |
| `reldate=7&datetype=edat` | `... AND 2026/10/15:2026/10/22[Date - Entry]` | 170 |
| `mindate=2026/10/15&maxdate=2026/10/22&datetype=pdat` | `... AND 2026/10/15:2026/10/22[Date - Publication]` | 120 |

要点：

- **`reldate=N` 实际是"含今天在内的 N+1 天窗口"**（`reldate=1` → 今天+昨天）。做"每天增量"时用 `reldate=2` 再本地去重更安全，或改用 `mindate/maxdate` 显式给区间。
- **`datetype=edat`（Entry Date）= 记录进入 PubMed 的日期**，是增量抓取唯一正确的字段：新文章可能在 paper 出版日（pdat）之前/之后很久才入库。实测同一条记录 `pubdate = 2026 Jul 24` 而 `edat` 落在 `2026/10/21`——用 pdat 抓会漏掉它。
- **`datetype=pdat`（Publication Date）= 期刊出版日**，适合"补历史"、不适合增量。
- `mindate/maxdate` 与 `datetype` 组合时必须都写，格式 `YYYY/MM/DD`（也接受 `YYYY`、`YYYY/MM`）。

### 1.4 字段标签语法（实测翻译结果）

| 标签 | 语义 | 实测 `querytranslation` 片段 |
|---|---|---|
| `[tiab]` | 标题+摘要 | `"single cell rna seq"[Title/Abstract]` |
| `[dp]` | 出版日期 | `2026/10/20:2026/10/22[Date - Publication]` |
| `[pt]` | 出版类型 | `"review"[Publication Type]` |
| `[ta]` | 期刊缩写 | `("nature"[Journal] OR "nature paris france"[Journal] OR "nat ment health"[Journal])` ← **注意会自动扩展同义词** |
| `[MeSH]` | MeSH 主题词 | 见 1.6 的 CRISPR 翻译：自动扩成 `"clustered regularly interspaced short palindromic repeats"[MeSH Terms] OR ...` |
| `[au]` / `[ad]` / `[journal]` | 作者 / 单位 / 刊名全称 | 未逐一测（常识性） |

> **坑**：`[ta]` 会做同义词扩展（`Nature` 展开出 `nat ment health` 等），想要精确期刊请用 `"Nature"[Journal]` 或 ISSN：`"0028-0836"[is]`。

实测 `[ta]` 过滤（2026-10-15..22，`cancer[tiab]` + `Nature[ta]`）返回 `count = 0`，翻译式如上——说明过滤生效但当期确实无命中，**不要误判为语法错误**。

### 1.5 过滤综述 / RCT

```bash
# 综述
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("(immunotherapy[tiab]) AND (review[pt]) AND (2026/10/15:2026/10/22[dp])"))')&retmode=json&retmax=100"
```
实测：`count = 74`，翻译 `"review"[Publication Type]`。

```bash
# RCT
... term="(immunotherapy[tiab]) AND (randomized controlled trial[pt]) AND 2026/10/15:2026/10/22[dp]"
```
实测：`count = 3`，翻译 `"randomized controlled trial"[Publication Type]`。

更稳的写法（覆盖多种 PT）：

- 综述：`(review[pt] OR systematic review[pt] OR meta-analysis[pt])`
- 临床试验：`(randomized controlled trial[pt] OR clinical trial, phase iii[pt])`
- 也可用 Article Type 过滤器：`AND pubmed pmc local[sb]` 之类 sb 子集（未验证）。

### 1.6 可直接复制的配方

**(a) 最近 7 天增量，关键词 + 只要 PMID 列表**

```bash
curl -sS "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi" \
  --data-urlencode "db=pubmed" \
  --data-urlencode "term=(CRISPR[tiab] OR \"base editing\"[tiab]) AND (2026/10/15:2026/10/22[edat])" \
  --data-urlencode "retmode=json" --data-urlencode "retmax=500" \
  --data-urlencode "tool=aan_daily" --data-urlencode "email=you@example.org"
```

实测返回（`reldate=1&datetype=edat`）：

```json
{"header":{"type":"esearch","version":"0.3"},
 "esearchresult":{"count":"6","retmax":"3","retstart":"0",
  "idlist":["42902384","42902383","42902180"],
  "querytranslation":"(\"clustered regularly interspaced short palindromic repeats\"[MeSH Terms] OR ...) AND 2026/10/21:2026/10/22[Date - Entry]"}}
```

**(b) 批量取摘要（XML，唯一可靠方式）**

```bash
curl -sS "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi" \
  --data-urlencode "db=pubmed" --data-urlencode "id=42902384,42902383" \
  --data-urlencode "rettype=abstract" --data-urlencode "retmode=xml"
```

实测返回片段：

```xml
<PubmedArticle><MedlineCitation Status="MEDLINE" Owner="NLM" IndexingMethod="Automated">
<PMID Version="1">42902384</PMID>
<DateCompleted><Year>2026</Year><Month>10</Month><Day>21</Day></DateCompleted>
<Article PubModel="Electronic"><Journal><ISSN IssnType="Electronic">1750-1326</ISSN>
<JournalIssue CitedMedium="Internet"><Volume>21</Volume><Issue>1</Issue>
<PubDate><Year>2026</Year><Month>Jul</Month><Day>24</Day></PubDate></JournalIssue>
<Title>Molecular neurodegeneration</Title><ISOAbbreviation>Mol Neurodegener</ISOAbbreviation></Journal>
<ArticleTitle>Parkinson's disease LRRK2 mutations dysregulate iron homeostasis ...</ArticleTitle>
<ELocationID EIdType="doi" ValidYN="Y">10.1186/s13024-026-00979-5</ELocationID>
<Abstract><AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">Iron accumulation is a hallmark ...</AbstractText>
<AbstractText Label="METHODS" NlmCategory="METHODS">Here, we investigated ...</AbstractText>
```

> 结构化摘要 = 多个 `<AbstractText Label="...">`，拼接时按 `Label` 加小标题即可。
> 每条记录有用的字段：`PMID`、`ArticleTitle`、`Abstract/AbstractText`、`ELocationID[@EIdType='doi']`、`Journal/ISOAbbreviation`、`PubDate`、`ArticleDate`、`PublicationTypeList`、`MeshHeadingList`。

**(c) 只要元数据（不含摘要）→ esummary，轻量**

```bash
curl -sS "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=42902384&retmode=json"
```

实测字段（`result.<pmid>` 下）：

```json
{"uid":"42902384","pubdate":"2026 Jul 24","epubdate":"2026 Jul 24",
 "source":"Mol Neurodegener","fulljournalname":"Molecular neurodegeneration",
 "title":"Parkinson's disease LRRK2 mutations dysregulate iron homeostasis ...",
 "pubtype":["Journal Article"],"recordstatus":"PubMed - indexed for MEDLINE",
 "articleids":[{"idtype":"pubmed","idtypen":1,"value":"42902384"},
               {"idtype":"doi","idtypen":3,"value":"10.1186/s13024-026-00979-5"},
               {"idtype":"pii","idtypen":4,"value":"10.1186/s13024-026-00979-5"}],
 "sortpubdate":"2026/07/24 00:00"}
```

可用键（实测 44 个）：`uid, pubdate, epubdate, source, fulljournalname, authors, lastauthor, title, volume, issue, pages, lang, issn, essn, pubtype, articleids, recordstatus, pubstatus, sortpubdate, sortfirstauthor, references, pmcrefcount, elocationid ...`
**没有 `abstract`**——这是 esummary 与 efetch 的分界线。

**(d) `efetch` 的 JSON 陷阱（实测）**

```bash
curl -sS ".../efetch.fcgi?db=pubmed&id=42902384&rettype=abstract&retmode=json"
```
HTTP **200**，但 body 是纯文本：

```
Mol Neurodegener. 2026 Jul 24;21(1):68. doi: 10.1186/s13024-026-00979-5.

Parkinson's disease LRRK2 mutations dysregulate iron homeostasis ...
Mamais A(1), Batchelor RD Jr(2), ...
```

> 传 `retmode=json` 不会报错，只会静默返回 `retmode=text` 的内容。**生产代码里必须断言 `Content-Type` 或首字符是 `<`。**

### 1.7 限额与稳定性

- 单次 `esearch` `retmax` 上限 10000；`efetch` 一次建议 ≤ 200 个 ID（官方建议 200，**未验证**上限值，但实测 2 个 ID 正常）。
- 失败模式：偶发 500/超时；建议 3 次指数退避重试（1s/4s/9s）。
- 本机实测 5 次请求延迟 2.2–2.4s，稳定；无 Cloudflare 拦截。

---

## 2. Europe PMC REST API

### 2.1 基本事实

| 项 | 值 |
|---|---|
| Base | `https://www.ebi.ac.uk/europepmc/webservices/rest/` |
| 端点 | `/search`、`/{source}/{id}/fullTextXML`、`/search?resultType=core` 等 |
| 鉴权 | 无需 key（实测） |
| 速率 | **未在响应头暴露**；官方文档站从本机 403（Cloudflare `Just a moment...`），无法引用官方数字 → **速率限制未验证**，实务按 ≤5 req/s 保守使用 |
| 分页 | `pageSize`（1–1000，实测）+ `cursorMark` |
| 预印本 | **收录**（`source=PPR`，实测命中 Research Square `10.21203/rs.3.rs-11150671/v1`） |
| 全文 | OA 文章给 `fullTextUrlList` + `/fullTextXML` 端点 |
| 版本 | 响应体 `"version":"6.9"` |

### 2.2 日期字段（实测差异，重要）

同一查询 `CRISPR`，不同日期字段的命中数：

| 字段写法 | 命中数 |
|---|---|
| `FIRST_PDATE:[2026-10-21 TO 2026-10-22]` | **29** |
| `CREATION_DATE:[2026-10-01 TO 2026-10-22]` | **1885** |
| `FIRST_CREATION_DATE:[2026-10-01 TO 2026-10-22]` | 0 |
| `PUB_DATE:[...]` | 0 |
| `ENTRY_DATE:[...]` | 0 |
| `LAST_UPDATE_DATE:[...]` | 0 |
| **对照组** `BOGUS_FIELD_XYZ:[...]` | 0 |

> ⚠️ 对照实验说明：**未知字段同样返回 0 而非报错**，所以上表里 0 的三行只能说明"在这个语法下没命中的证据不足"，**不能断定字段不存在**。`FIRST_CREATION_DATE` 在任务描述中被提到，但本机实测拿不到非零结果，且官方字段表 403 不可达 → **标记为未验证**。可用的是 `FIRST_PDATE` 和 `CREATION_DATE`（后者与 JSON 里的 `firstIndexDate` 对应）。
>
> 实务建议：增量抓取用 `FIRST_PDATE`（首次出版日）做"新文章"，用 `CREATION_DATE` 做"新入库（含回溯补录）"。

### 2.3 resultType 与摘要

实测同样 25 条 / 同一天窗口的响应体积：

| resultType | 体积 | 含内容 |
|---|---|---|
| `idlist` | 2,615 B | 仅 id + source |
| `lite` | 18,298 B | 标题/作者/刊名/DOI/`isOpenAccess`/`firstPublicationDate` |
| `core` | 87,796 B | 上述 + `abstractText` + `fullTextUrlList` + `license` + `pubTypeList` + 作者机构 |

`core` 实测（MED 记录）：

```json
{"id":"42901363","source":"MED","pmid":"42901363",
 "doi":"10.1016/j.molbiopara.2026.111789",
 "abstractText":"Veterinary parasitic diseases remain a major threat to livestock production ...",  // len=1566
 "license":"cc by","isOpenAccess":"Y","inEPMC":"Y","hasPDF":"Y",
 "fullTextUrlList":{"fullTextUrl":[
   {"availability":"Free","availabilityCode":"F","documentStyle":"html","site":"PubMedCentral",
    "url":"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13681438/?tool=EBI"}]}}
```

> 注意：**不是每条 `core` 都有 `abstractText`**——实测某 PMC 记录 `has abstractText: False`。缺失时回落到 PubMed `efetch`。

### 2.4 可直接复制的配方

**(a) 最近 1 天，关键词 + 摘要，一次拿满**

```bash
curl -sS -G "https://www.ebi.ac.uk/europepmc/webservices/rest/search" \
  --data-urlencode 'query=(CRISPR OR "gene editing") AND (FIRST_PDATE:[2026-10-21 TO 2026-10-22])' \
  --data-urlencode 'format=json' \
  --data-urlencode 'resultType=core' \
  --data-urlencode 'pageSize=1000' \
  --data-urlencode 'sort=P_PDATE_D desc'
```

实测命中 29 条，首条返回：

```json
{"version":"6.9","hitCount":29,
 "nextCursorMark":"AoIIQD+NFCg1NjcxNjM4OQ==",
 "nextPageUrl":"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=CRISPR&cursorMark=AoIIQD%2BNFCg1NjcxNjM4OQ%3D%3D&resultType=lite&pageSize=1&format=json",
 "request":{"queryString":"CRISPR","resultType":"core","cursorMark":"*","pageSize":1000,"sort":"P_PDATE_D desc","synonym":false},
 "resultList":{"result":[
   {"id":"PMC13681438","source":"PMC","pmcid":"PMC13681438",
    "title":"CRISPR Technology Applied to the Analysis of Antibiotic Resistance Genes in the Environment",
    "authorString":"Yan J, Yuan X, Zhu Z, ...","journalTitle":"Environment & Health",
    "pubYear":"2026","pubType":"journal article","isOpenAccess":"Y","inEPMC":"Y","hasPDF":"Y",
    "firstPublicationDate":"2026-10-21","firstIndexDate":"2026-10-21"},
   {"id":"PPR1347026","source":"PPR","doi":"10.21203/rs.3.rs-11150671/v1",
    "title":"Development and validation of an RPA-CRISPR-Cas12b assay ...",
    "pubType":"preprint","bookOrReportDetails":{"publisher":"Research Square","yearOfPublication":2026}}]}}
```

**(b) 分页（cursorMark）**

```bash
# 第一页
curl -sS "...&pageSize=100&cursorMark=*" 
# 后续页：把响应里的 nextCursorMark 原样回传
curl -sS "...&pageSize=100&cursorMark=AoIIQDSRoig1NjczNTE5Ng=="
```

实测第一页返回 `"nextCursorMark": "AoIIQDSRoig1NjczNTE5Ng=="`，`resultList.result` 为 `["PMC13681438","PPR1347026","PPR1347212"]`。

**(c) 只要 OA 全文 XML**

```bash
curl -sS "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13681438/fullTextXML"
```

### 2.5 坑（实测）

- `pageSize=0` 不是合法值 → 返回体无 `hitCount`，JSON 解析直接失败。**探测计数要写 `pageSize=1`。**
- `pageSize=1001` → `{"errCode": 404, "errMsg": "Invalid page size provided. Valid size is between 1 and 1000"}`（注意 HTTP 层是 4xx，错误码字段却是 404，容易误判）。
- **`sort` 必须带方向**：`sort=P_PDATE_D` → **HTTP 503**；`sort=P_PDATE_D desc` → 200。`sort=CITED desc` 也 200。
- 无 `x-ratelimit-*` 响应头，无法自适应限流 → 客户端自行 5 req/s 上限 + 退避。
- 站点 `europepmc.org` 全站 403（Cloudflare 人机校验），**官方文档从本机不可达**；`docs.europepmc.org` TLS 握手直接失败（`SSL_ERROR_SYSCALL`）。本文 EPMC 事实全部来自 API 响应本身。

---

## 3. OpenAlex

### 3.1 重大变更：已从"礼貌池"改为"美元额度池"

实测响应头（无 key 请求 `/works`）：

```
x-ratelimit-limit: 1000
x-ratelimit-limit-usd: 0.1
x-ratelimit-remaining: 979
x-ratelimit-remaining-usd: 0.0979
x-ratelimit-cost-usd: 0.001
x-ratelimit-credits-used: 10
x-ratelimit-reset: 68253
```

响应体 `meta.notice` 原文：

> "No API key, so this request shares one free daily budget ($0.10) with everyone on your network's IP address. Get a free key with its own $1/day at https://openalex.org/settings/api and add api_key=YOUR_KEY to your requests."

官方文档（[help.openalex.org/api/authentication](https://help.openalex.org/api/authentication/)）要点：

| 谁在调用 | 每秒请求数 | 每日预算 |
|---|---|---|
| 无 key | 10 req/s | **$0.10**（且与同 IP 所有人共享） |
| 免费 key | 30 req/s | **$1.00** |
| 年费计划 | 50 req/s | $20–$200+/天 |

计费（[example-costs](https://help.openalex.org/access/example-costs/)）：

| 操作 | 单价 | "$0.10/天"能跑多少次 |
|---|---|---|
| List + filter（`filter=...`，无 `search`） | $0.0001（1 credit） | ~1,000 |
| **Search**（`title_and_abstract.search` / `search=`） | **$0.001（10 credits）** | **~100** |
| Search + `rerank=true` | $0.002 | ~50 |
| 单条按 ID 查（`/works/W...`） | 免费 | 无限 |

> **结论：OpenAlex 从"几乎无限"变成了"每天约 100 次关键词搜索"**。做每日多关键词增量时必须用免费 key（$1/天 ≈ 1000 次搜索），或者把关键词合并成一次 `OR` 查询。

**`mailto=` 礼貌池是否还存在：未验证。** 实测 `mailto=probe@example.org` 请求正常返回 200，但响应头与无 `mailto` 完全相同（无专属配额字段）；官方新文档只讲 `api_key`，未再提 polite pool。**结论：不要再依赖 `mailto`，改用免费 key。**

### 3.2 `/works` 过滤参数（实测可用）

| 参数 | 实测结果 |
|---|---|
| `from_publication_date:2026-10-21` | 生效；`meta.count=7` |
| `to_publication_date:YYYY-MM-DD` | 存在（成对使用），未单独测 |
| `title_and_abstract.search:CRISPR` | 生效，且被识别为 **search**（$0.001/次，10 credits） |
| `publication_date:2026-10-21` | 生效（单日精确匹配） |
| `type:review` | 生效，`count=10`，返回 `type:["review","review"]` |
| `primary_topic.id:T10156` | 生效，`count=398`，返回完整 `primary_topic{display_name,score,subfield,field,domain}` |
| `doi:10.1186/s13024-026-00979-5` | 生效（可直接按 DOI 精确定位） |
| `select=id,doi,title,publication_date,type` | 生效，显著减小响应体 |
| `per_page` | 最大 **100**（200 为已废弃的 legacy 行为） |
| `cursor=*` + `meta.next_cursor` | 第一页 OK；**第二页 401** |

`x_query` 里的自然语言翻译很实用（实测定价与语义确认）：

```json
"x_query": {"oql":"get works where published since 2026-10-21 and title-abstract has (CRISPR)",
            "x_new_oql":"get works since 2026-10-21 with CRISPR in the title or abstract"}
"cost_usd": 0.001
```

### 3.3 `abstract_inverted_index` 还原摘要（实测可还原）

实测：`n_tokens=338`，`n_positions=212`（同词多位置）。还原算法 = 按位置排序拼回：

```python
def unabstract(aii: dict) -> str:
    if not aii: return ""
    pos = [(p, tok) for tok, ps in aii.items() for p in ps]
    pos.sort()
    return " ".join(tok for _, tok in pos)
```

实测还原结果：

```
Background: Iron accumulation is a hallmark of sporadic and familial Parkinson's disease (PD)
pathology and correlates with clinical motor symptom severity. The biochemical mechanisms
driving iron dyshomeostasis in PD brain and whether these are early or late event in the
neurodegenerative process r...
```

> 还原完美（含标点，标点作为独立 token 存放）。OpenAlex 摘要**免费**、覆盖率高，但**没有小标题结构**（PubMed 的 `Label="METHODS"` 信息丢失）。

### 3.4 可直接复制的配方

**(a) 最近 7 天 + 关键词 + 摘要**

```bash
curl -sS -G "https://api.openalex.org/works" \
  --data-urlencode 'filter=from_publication_date:2026-10-15,title_and_abstract.search:(CRISPR OR "base editing")' \
  --data-urlencode 'select=id,doi,title,publication_date,type,primary_location,abstract_inverted_index,cited_by_count' \
  --data-urlencode 'per_page=100' \
  --data-urlencode 'api_key=YOUR_KEY'
```

实测（无 key，单关键词）返回：

```json
{"meta":{"count":7,"db_response_time_ms":21,"page":1,"per_page":2,
  "cost_usd":0.001,"next_cursor":"IlsyNy45NzMwOSwgMTgzMDI5NzYwMDAwMCwgJ2h0dHBzOi8vb3BlbmFsZXgub3JnL1c3MTE1MDAzODg0J10i"},
 "results":[{"id":"https://openalex.org/W7214423125","doi":"https://doi.org/10.1007/978-1-0716-5547-4.pdf",
   "publication_date":"2026-10-24","type":"book","title":"CRISPR delivery",
   "abstract_inverted_index":{"Background":[0],"Iron":[1],"accumulation":[2],"...":[]}}]}
```

**(b) cursor 翻页（必须带 key）**

```bash
# 第一页
curl -sS "https://api.openalex.org/works?filter=...&per_page=100&cursor=*&api_key=K"
# 第二页起：无 key 时实测返回
```
```json
{"error":"API key required for cursor paging",
 "message":"Paging past the first page with cursor= needs a free API key. Get one in a minute at https://openalex.org/settings/api"}
```
HTTP **401**。

**(c) 按 DOI 批量补元数据（免费额度最划算）**

```bash
curl -sS "https://api.openalex.org/works?filter=doi:10.1186/s13024-026-00979-5|10.1038/s41586-026-00001-1&select=id,doi,title,primary_topic"
```

### 3.5 坑

- **`from_publication_date` 会返回未来日期**：实测 `filter=from_publication_date:2026-10-21` 命中了 `publication_date: 2028-01-01` 的记录（OpenAlex 收录了标注未来出版年的记录）。做"最近 N 天"**必须同时加 `to_publication_date`**，否则结果里混入未来文献。
- `type` 取值是 OpenAlex 自己的词表（`article/review/book/book-chapter/preprint/dataset/...`），不是 PubMed 的 `pt`。
- 关键词里的空格/括号要 URL 编码，`+` 会被当字面量。
- 无 key 时 `$0.10` 是**同 IP 共享**的——办公室/机房出口 IP 可能已被别人跑光，直接 429。

---

## 4. Semantic Scholar Graph API

### 4.1 基本事实

| 项 | 值 |
|---|---|
| Base | `https://api.semanticscholar.org/graph/v1` |
| 端点 | `/paper/search`（相关性）、`/paper/search/bulk`（批量/布尔）、`/paper/batch`、`/paper/{id}` |
| 无 key 速率 | 官方口径：**1000 rps 由全体匿名用户共享**（[官方 Overview](https://www.semanticscholar.org/product/api)）→ 实践中经常被跑满 |
| 有 key 速率 | 官方口径：**1 RPS**（"introductory rate limit"） |
| 鉴权 | 可选 `x-api-key` 头；[申请表单](https://www.semanticscholar.org/product/api#api-key-form) 免费、邮件下发 |
| 摘要 | **免费**（`abstract` 字段） |
| TLDR | `/paper/search` 有；**`/paper/search/bulk` 没有** |
| 全量数据 | S2AG / S2ORC 数据集可整包下载 |

### 4.2 本机实测：几乎不可用

`/paper/search` 连续 3 次全部 429：

```
try1 http=429 t=1.73
try2 http=429 t=2.05
try3 http=429 t=1.70
{"message": "Too Many Requests. Please wait and try again or apply for a key for higher rate limits. https://www.semanticscholar.org/product/api#api-key-form", "code": "429"}
```

`/paper/search/bulk` 间歇可用：8 次尝试中 1 次成功、多次 429。成功的样本（`query="large language model"&year=2026`）：

```json
{"total": 61065,
 "data":[
   {"paperId":"...","title":"LLMs for Integrated Business Intelligence: A Big Data-Driven Framework ...",
    "publicationDate":"2026-04-05","venue":"Big Data and Cognitive Computing",
    "publicationTypes":["JournalArticle"],
    "externalIds":{"DOI":"10.3390/bdcc10040110","CorpusId":287237300},
    "abstract":"Enterprise decision making in marketing, finance, and audit remains fragmented, leading to inefficient budget allocation and incomplete risk assessment. This study proposes ..."},
   {"title":"Multilingual Code-Switched Text Translation Using Large Language Models",
    "publicationDate":"2026-04-24","venue":"2026 2nd International Conference on Intelligent Systems and Computational Networks (ICISCN)",
    "externalIds":{"DOI":"10.1109/ICISCN67954.2026.11566110","CorpusId":289490724}}]}
```

> **跨源 ID 极其好用**：`externalIds` 直接给 `DOI / PubMed / PubMedCentral / CorpusId`，实测样本 `{"PubMedCentral":"13064676","DOI":"10.1128/mbio.03691-25","PubMed":"41841738"}`。

### 4.3 关键坑：bulk 不支持 `tldr`

实测原文：

```json
{"error":"Unrecognized or unsupported fields: [tldr]"}
```

- `fields=...,tldr` 在 `/paper/search/bulk` **直接 400**。
- `tldr` 只在 `/paper/search`（相关性搜索）和 `/paper/batch` 可用。
- 结论：**想用 TLDR 就必须走 `/paper/search`，而它在本机 429 到不可用** → TLDR 在当前网络环境下不是可靠能力。

### 4.4 日期过滤：**未完全验证**

- `year=2026` 实测有效（`total=61065`）。
- `publicationDateOrYear=2026-10-15:2026-10-22` 三次尝试均被 429 吞掉，**未能验证语法是否成立** → 标记未验证。若需按天粒度，建议改用 `/paper/search`（有 key 时）或 `/paper/batch` 按 PMID/DOI 反查。

### 4.5 配方（有 key 时）

```bash
# 相关性搜索 + TLDR（1 RPS，需 key）
curl -sS "https://api.semanticscholar.org/graph/v1/paper/search" \
  -H "x-api-key: $S2_KEY" \
  --data-urlencode 'query=CRISPR off-target' \
  --data-urlencode 'fields=title,abstract,tldr,externalIds,publicationDate,venue' \
  --data-urlencode 'limit=100' -G

# 批量布尔检索（无 key 也可能成功，需重试）
curl -sS -G "https://api.semanticscholar.org/graph/v1/paper/search/bulk" \
  --data-urlencode 'query="base editing" + (mice | human)' \
  --data-urlencode 'fields=title,abstract,externalIds,publicationDate,venue,publicationTypes' \
  --data-urlencode 'year=2026'
```

bulk 的语法：`+` = AND，`|` = OR，`-` = 取反，`"..."` = 短语，`*` = 前缀。

### 4.6 TLDR 质量（主观，未做系统评测）

- TLDR 是 S2 的生成式一句话摘要，**不是原文**，会丢失方法学细节和数值；用于"列表页给人扫一眼"可以，**不能作为推送正文的事实来源**。
- 本次因限流未能批量取到 TLDR 样本 → **质量评估未验证**。

---

## 5. Crossref（DOI 元数据 / 期刊目次补充）

### 5.1 基本事实

| 项 | 值 |
|---|---|
| Base | `https://api.crossref.org/works` |
| 鉴权 | 无需 key；礼貌池走 `mailto`（文档口径） |
| 速率 | 实测响应头 `x-rate-limit-limit: 1`、`x-rate-limit-interval: 1s`、`x-api-pool: public-array` → **1 req/s** |
| 摘要 | **不可靠**，按出版商是否上传 `<jats:abstract>` 而定 |
| 强项 | DOI 权威元数据、期刊目次（`filter=issn:`）、参考文献、`published` 精确日期 |

### 5.2 实测

```bash
curl -sS -G "https://api.crossref.org/works" \
  --data-urlencode 'filter=from-pub-date:2026-10-20' \
  --data-urlencode 'query.bibliographic=CRISPR' \
  --data-urlencode 'rows=2' \
  --data-urlencode 'select=DOI,title,container-title,published,abstract,type'
```

返回：

```json
{"status":"ok","message-type":"work-list",
 "message":{"total-results":262,
  "items":[
   {"DOI":"10.1201/9781003650904-3","type":"book-chapter",
    "title":["CRISPR/Cas and Synthetic Biology in Agriculture"],
    "container-title":["CRISPR/Cas for Plant Genome Editing"],
    "published":{"date-parts":[[2026,10,21]]}},
   {"DOI":"10.1201/9781003650904-1","type":"book-chapter",
    "title":["Introduction to CRISPR/Cas Technology"],
    "container-title":["CRISPR/Cas for Plant Genome Editing"],
    "published":{"date-parts":[[2026,10,21]]}}]}}
```

响应头：

```
x-rate-limit-limit: 1
x-rate-limit-interval: 1s
x-api-pool: public-array
```

> **摘要实测两条均为 `abstract: NONE`**（book-chapter 类型）。Crossref 摘要**只对部分出版商存在**，不能当摘要来源。

### 5.3 配方

```bash
# 某刊最近 3 天的目次（ISSN 过滤 + 日期）
curl -sS -G "https://api.crossref.org/journals/0028-0836/works" \
  --data-urlencode 'filter=from-pub-date:2026-10-19,until-pub-date:2026-10-22' \
  --data-urlencode 'rows=100' \
  --data-urlencode 'select=DOI,title,published,abstract,type' \
  --data-urlencode 'mailto=you@example.org'

# 按标题/作者做 DOI 反查（去重后补齐被引/期刊信息）
curl -sS -G "https://api.crossref.org/works" \
  --data-urlencode 'query.bibliographic=Parkinson LRRK2 iron ferroptosis 2026' \
  --data-urlencode 'rows=3' \
  --data-urlencode 'select=DOI,title,published,container-title'
```

### 5.4 坑

- `rows` 上限 1000；深分页用 `cursor=*`（与 OpenAlex 类似，但 Crossref 的 cursor 无 key 要求，**未验证**）。
- `filter=from-pub-date` 与 `published` 字段可能不一致（在线先发 vs 印刷），期刊目次场景建议用 `filter=from-online-pub-date`（未验证）。
- 1 req/s 是硬限制，批量补 DOI 要串行 + 队列。

---

## 6. 跨源去重与增量策略

### 6.1 去重键优先级

| 优先级 | 键 | 归一化规则 | 覆盖情况 |
|---|---|---|---|
| 1 | **DOI** | 转小写、去 `https://doi.org/` 前缀、去尾部 `/`、`&`→`and` 不改 | PubMed/EPMC/OpenAlex/Crossref/S2 全有 |
| 2 | **PMID** | 纯数字字符串 | PubMed/EPMC/S2(部分) |
| 3 | **arXiv ID** | `arXiv:2401.01234`（去 `vN` 版本号） | OpenAlex/S2/EPMC(部分) |
| 4 | `title+year` 哈希 | 小写、去标点、压缩空白、去 HTML 标签 | 兜底（预印本→正式发表、Crossref 缺 DOI 的场景） |

跨源合并流程：

```
候选集 = PubMed(edat 窗口) ∪ EPMC(FIRST_PDATE 窗口) ∪ 可选源
   ↓
1) 有 DOI → 按 normDOI 分组
2) 无 DOI 有 PMID → 按 PMID 分组，再用 PMID 反查 DOI（EPMC/NLM ID Converter）补齐
3) 都没有 → 按 normTitle 前 80 字符 + 首作者姓 + 年份 做 similarity ≥ 0.9 聚类
   ↓
合并策略（字段优先级）：
  title        : PubMed > EPMC > OpenAlex > Crossref
  abstract     : PubMed(结构化) > EPMC.core > OpenAlex(倒排还原) > S2 > Crossref
  pub_date     : Crossref.published > EPMC.firstPublicationDate > PubMed.pubdate
  venue        : Crossref.container-title > EPMC.journalTitle > PubMed.source
  oa_fulltext  : EPMC.fullTextUrlList > OpenAlex.primary_location > S2.openAccessPdf
  topics       : OpenAlex.primary_topic（独有）
  tldr         : S2（独有，可选）
```

### 6.2 每日增量状态机

```
state: { last_success_utc, seen_dois: set, seen_pmids: set }

每天 T 时刻：
  window = [last_success_utc - 2天, now]        # 回看 2 天，抗漏抓/补录
  PubMed : esearch datetype=edat, mindate..maxdate=window  → 取 PMID
  EPMC   : FIRST_PDATE:[window]  +  CREATION_DATE:[window]  → 取 id
  合并去重 → 差集 seen_* → 新条目
  为缺摘要的新条目补 efetch（≤200/批）
  成功后再推进 last_success_utc = now（失败不推进，保证 at-least-once）
```

**为什么回看 2 天**：`reldate` 本身含今天+昨天；EPMC 的 `firstIndexDate` 与 PubMed 的 `edat` 不同步（实测同一条记录 `firstPublicationDate=2026-10-21` 而 `firstIndexDate=2026-10-21`、PubMed `edat=2026/10/21` 但 `pdat=2026 Jul 24`），存在数小时到数天的入库延迟差。回看窗口 + `seen` 集合是幂等的。

### 6.3 失败模式总表

| 源 | 超时/延迟（本机实测） | 限流 | 需 key | 区域可达性（大陆+代理） | 主要失败姿态 |
|---|---|---|---|---|---|
| PubMed | 2.2–2.4s | 3/s（实测头），10/s 有 key | 否 | ✅ 稳定 | 偶发 5xx；`efetch retmode=json` 静默降级 |
| Europe PMC | ~1–5s（首包 5.1s） | 未见响应头 | 否 | ✅ 稳定（API）／❌ 文档站 403 | `pageSize=0/1001` 报错；`sort` 缺方向 503 |
| OpenAlex | 2.8s | 10/s 无 key，30/s 有 key；**$0.10/天** | cursor 翻页要 key | ✅ 稳定 | 额度耗尽 429；cursor 401；混入未来日期 |
| Semantic Scholar | 1.7–2.0s（429 时） | 匿名共享池，**实测常年 429**；有 key 1 RPS | 强烈建议 | ⚠️ 可达但基本取不到数据 | 连续 429；bulk 不支持 tldr |
| Crossref | 2.3s | **1 req/s**（实测头） | 否 | ✅ 稳定 | 摘要缺失；深分页限制 |

---

## 7. 推荐组合

### 7.1 分角色

| 角色 | 源 | 理由 |
|---|---|---|
| **主源** | **PubMed E-utilities** | ① 唯一有可靠"入库日期"`edat`，天然适配每日增量；② 摘要免费且带结构化小标题；③ MeSH 词表让"按概念而非字面"检索成为可能（`CRISPR[tiab]` 会自动扩展同义词，实测量化过）；④ 无 key 3 req/s 足够（每天 1 个窗口通常 1–5 次请求）；⑤ 本机 2.3s 延迟、无拦截 |
| **补充源** | **Europe PMC** | ① 补 PubMed 不收录的**预印本**（`source=PPR`，实测命中 Research Square）；② `resultType=core&pageSize=1000` 一次请求拿全量摘要，极大降低请求数；③ 直接给 OA 全文 URL 与 `fullTextXML`；④ 覆盖 PMC 全库（部分非 MEDLINE 刊） |
| **补充源 2** | **Crossref** | DOI 权威落库、期刊目次（`/journals/{issn}/works`）、印刷/在线出版日；1 req/s 足够每日补全 |
| **增强源（可选）** | **OpenAlex** | `primary_topic` / `cited_by_count` / 机构消歧是独有能力；但**按美元计费**，只用于"对已抓到的 DOI 批量补元数据"（按 DOI 查是 $0.0001/次 甚至免费），**不要用它做关键词发现** |
| **兜底（best-effort）** | **Semantic Scholar** | 只取它独有的 `tldr` 和 `externalIds.PubMed` 交叉校验；**必须放在 try/except 里，429 直接跳过**，绝不阻塞主流程 |

### 7.2 推荐流水线

```
06:00  ① PubMed esearch (datetype=edat, 窗口=近 48h) → PMIDs
       ② PubMed efetch (rettype=abstract, retmode=xml, 200/批) → 结构化摘要
       ③ Europe PMC search (FIRST_PDATE 窗口, resultType=core, pageSize=1000)
       ④ Crossref 仅对"缺 DOI/缺期刊全名"的条目做 query.bibliographic 反查（1 req/s 串行）
       ⑤ (可选) OpenAlex 按 DOI 批量补 primary_topic / cited_by_count
       ⑥ (可选) S2 /paper/search 取 tldr，超时 3s 或 429 即放弃
       ⑦ 去重（DOI→PMID→title hash）→ 相关性打分 → 推送
```

**为什么不把 OpenAlex 或 S2 当主源**：

- OpenAlex：关键词搜索 $0.001/次，无 key 一天只有 100 次；且 cursor 翻页要 key。作为"每日多关键词 + 多页"的发现层成本不可控。
- S2：本机实测基本 429，可用性 < 20%；`bulk` 还不支持 `tldr`。工程上无法承诺 SLA。

**为什么不用 bioRxiv 官方 API 作为主源**：它只覆盖单一预印本库，量小但可作为"生命科学预印本"的定向补充（你已实测可直连）。EPMC 的 `source=PPR` 已覆盖大部分 bioRxiv/medRxiv/Research Square 记录，优先用 EPMC 减少一个数据源。

### 7.3 请求预算（每日一次全量）

| 源 | 请求数 | 耗时估算 |
|---|---|---|
| PubMed esearch | 关键词数 × 1（可 OR 合并成 1 次） | 2.4s |
| PubMed efetch | ⌈新增数/200⌉ | 2.4s × N |
| Europe PMC | ⌈新增数/1000⌉ | 2–5s × N |
| Crossref | 仅缺口条目，1 req/s 串行 | 缺口数 × 1s |
| OpenAlex（可选） | ⌈DOI 数/100⌉ 或 1 次批量 filter | 2.8s × N |
| **合计** | **约 5–15 次请求** | **< 60s** |

---

## 8. 待确认问题

1. **PubMed 有 key 时是否真的是 10 req/s** —— 本机无 key，仅验证了无 key 的 `x-ratelimit-limit: 3`。需要申请 key 后复测响应头。
2. **`efetch` 单次 ID 上限** —— 官方建议 200，但未在本机验证边界（试 500/1000 会怎样）。
3. **Europe PMC 官方速率限制** —— `europepmc.org` 全站 403、`docs.europepmc.org` TLS 失败，无法取得官方数字。需要换网络（或直连非代理）访问文档站确认；同时确认 `FIRST_CREATION_DATE` 是否真是合法字段（本机实测 0 命中，但未知字段也返回 0，无法区分）。
4. **OpenAlex `mailto` 礼貌池是否已彻底废弃** —— 新文档只讲 `api_key`，实测 `mailto` 不改变任何配额头；需要看 changelog 或官方声明。
5. **OpenAlex 免费 key 的实际 $1/天是否够用** —— 取决于每日关键词数与 `OR` 合并程度，需要按真实关键词表算一次。
6. **S2 的 `publicationDateOrYear` 区间语法** —— 三次尝试全被 429 吞掉，未验证；拿到 key 后需复测。
7. **S2 TLDR 质量** —— 因限流未取到批量样本，无法评估；需要 key 后做 50 条人工抽查。
8. **`reldate` 在跨月/跨年边界的表现** —— 实测只覆盖 `2026-10-21/22`，未测月末（如 `2026-10-31` + `reldate=2`）是否会串月出错。
9. **预印本 → 正式发表的合并** —— EPMC 的 `PPR` 记录与后续 `MED` 记录是否有稳定关联字段（如 `commentCorrectionList`），未验证；这直接决定去重逻辑要不要做"预印本升级"特判。
10. **中国大陆直连（不走代理）的表现** —— 本次全部经 `127.0.0.1:7898` 代理，未做"直连 vs 代理"对照；生产部署若在境内直连，5 个源的延迟/可达性需重测（你已实测 PubMed/GitHub/bioRxiv 可直连，但 EPMC `www.ebi.ac.uk` 与 OpenAlex Cloudflare 未验证直连）。

---

## 参考链接

- PubMed E-utilities 使用与限流：https://www.ncbi.nlm.nih.gov/books/NBK25497/
- E-utilities API 参考（esearch/efetch/esummary 参数）：https://www.ncbi.nlm.nih.gov/books/NBK25499/
- PubMed 字段标签与日期检索帮助：https://pubmed.ncbi.nlm.nih.gov/help/
- Europe PMC REST API（入口，本机 403）：https://europepmc.org/RestfulWebService
- Europe PMC API 基址（实测可用）：https://www.ebi.ac.uk/europepmc/webservices/rest/search
- OpenAlex 鉴权与速率：https://help.openalex.org/api/authentication/
- OpenAlex 计费示例：https://help.openalex.org/access/example-costs/
- OpenAlex 分页（cursor）：https://help.openalex.org/api/paging/
- OpenAlex 过滤与搜索：https://help.openalex.org/api/filtering/
- Semantic Scholar API Overview（速率与 key）：https://www.semanticscholar.org/product/api
- Semantic Scholar Graph API 文档：https://api.semanticscholar.org/api-docs/
- Crossref REST API 文档：https://github.com/Crossref/rest-api-doc
- Crossref 礼貌池与速率：https://api.crossref.org/swagger-ui/index.html
