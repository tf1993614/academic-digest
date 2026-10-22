# GitHub 仓库发现 + 微信推送通道 技术调研

> 调研日期：2026-10-22（Asia/Shanghai）。测试环境：中国大陆网络，`api.github.com` 直连（走 HTTP 代理，出口 IP `38.244.6.37`，下文"共享出口 IP"均指此）。
> 本文所有"实测"内容均为本次调研用 `curl` 真实请求所得，响应片段原样粘贴；仅凭官方文档未实测的结论标注 **[文档]**；本次未能核实的一律标注 **未验证**。

---

## TL;DR

**A. GitHub 抓取（推荐组合）**

1. **必须用 token**。未认证 `core` 只有 **60 次/小时**、`search` **10 次/分钟**，且限额按 **出口 IP** 计——本次实测该 IP 被他人共享，几分钟内就被打到 `403 API rate limit exceeded`。每天扫 50–200 个候选 + 读 20 个 README，只有 60/小时必然失败。
2. **主路径：REST Search 抓候选 → REST 单仓库接口补元数据 → `raw.githubusercontent.com` 取 README**。
   - 候选：`GET /search/repositories?q=topic:llm+stars:>500+pushed:>YYYY-MM-DD&sort=updated&order=desc&per_page=100`
   - 元数据（stars/topics/license/最近 commit）：`GET /repos/{o}/{r}` + `GET /repos/{o}/{r}/commits?per_page=1`
   - README：`https://raw.githubusercontent.com/{o}/{r}/{branch}/README.md`（**不消耗 API 配额**、无鉴权，实测 200）
3. **`pushed:>` 是"活跃"信号，`created:>` 是"新仓库"信号，二者语义不同**：`pushed` = 任意分支最近一次 push，`created` = 建库时间。`created:>近7天` 会漏掉 99% 的相关老项目（实测 `topic:llm stars:>50 created:>2026-10-15` 仅 **10** 个结果）。
4. **GraphQL Search 并不更适合"发现"**：一样 1000 条上限、一样要 token，且游标分页对"按天增量"没有优势；它的价值在"一次查询批量取多仓库的多字段"（省请求数），适合**已知 repo 列表的补数据**，不适合扫库。
5. **老 repo 重复问题**：`sort=stars` 每次返回同一批头部仓库（实测 `topic:large-language-model stars:>5000` 只有 **10** 个结果，天天一样）。解法：`pushed:>日期` + `sort=updated` 做增量，再用 `created:>日期` 单独跑一条"新库"通道，两者并集后去重（本地保存已推送 `full_name`）。
6. **官方没有 trending API**（`/trending` 是网页，无官方 JSON）。替代：`created:>7天前 sort=stars` 近似"本周新星"，或自建 `pushed:>` 增量榜。
7. **Release 跟踪**：`/repos/{o}/{r}/releases` 最可靠（带 `published_at`、`body`、`tag_name`，支持 ETag → 304 不计配额）；`releases.atom` **免鉴权**可用但**体积不可控**（实测 `huggingface/transformers` 一次 **1.4 MB**，小仓库仅 1.8 KB），适合"只判断有没有新 release"的粗筛。
8. **配额核算**：50–200 候选/天 + 20 README/天，用 1 个 classic PAT（5000/小时）绰绰有余；纯靠未认证 60/小时 **不可行**。

**B. 微信推送（推荐）**

1. 免费且不需企业资质、直达个人微信的只有三类：**Server酱**（免费 5 条/天）、**PushPlus**（免费，但 **2024-08-01 起未实名无法调用接口**）、**WxPusher**（"永久免费"，需用户关注其公众号，见"未验证"项）。
2. **3000–6000 字长文没有任何单条通道能优雅承载**：Server酱 `desp` 上限 32 KB 但微信卡片只截前 30 字；企业微信机器人 `markdown`/`markdown_v2` 单条 **4096 字节（UTF-8）**，≈1300 汉字，6000 字必然要分 5 条。所以**正确形态是"摘要卡 + 链接到网页全文"**，长文只作为网页内容。
3. **首选方案 1（零门槛）**：Server酱 单条摘要卡（标题 + 3–5 条要点 + 全文链接），免费 5 条/天足够每天 1 篇。
4. **首选方案 2（要表格/长文）**：企业微信群机器人 `msgtype=markdown_v2`（**唯一支持表格**的免费通道），每条 ≤4096 字节，按"1 条总览 + N 条论文卡片"分条发送，20 条/分钟够用。**门槛：需注册企业微信（可免费注册，未认证状态群机器人是否可用本次未验证）。**
5. 不要用公众号模板消息/客服消息做主通道：需**认证服务号** + 48 小时会话窗口（**未验证**，见待确认），个人项目门槛过高。

---

## A 部分：GitHub 仓库发现

### A1. REST Search API：`GET /search/repositories`

#### A1.1 实测请求与返回

```bash
curl -sS -D - 'https://api.github.com/search/repositories?q=topic:large-language-model+stars:%3E5000&sort=stars&order=desc&per_page=2'
```

真实响应头（节选）：

```
HTTP/2 200
link: <https://api.github.com/search/repositories?q=topic%3Alarge-language-model+stars%3A%3E5000&sort=stars&order=desc&per_page=2&page=2>; rel="next", <...&page=5>; rel="last"
x-ratelimit-limit: 10
x-ratelimit-remaining: 9
x-ratelimit-resource: search
```

真实响应体（节选，字段已裁剪）：

```json
{"total_count":10,"incomplete_results":false,"items":[
 {"full_name":"jingyaogong/minimind","stargazers_count":64169,"fork":false,
  "pushed_at":"2026-09-22T16:07:34Z","created_at":"2024-07-27T04:34:12Z",
  "topics":["artificial-intelligence","large-language-model"]}]}
```

要点：
- `link` 头里的 `rel="last"` 直接暴露分页上界。实测 `per_page=1` 时 `rel="last"` 指向 `page=1000`，即便 `total_count=21695` —— **每次搜索最多返回 1000 条**。
- `total_count` 是"匹配总数"，但可翻页的只有前 1000 条；`incomplete_results=true` 表示查询超时、结果可能不全。

#### A1.2 支持的 q 语法（逐项核实）

| 限定符 | 实测/文档结论 | 证据 |
|---|---|---|
| `topic:` | 匹配仓库 topics 字段，精确标签 | 实测 `topic:large-language-model` 命中 `topics:[...,'large-language-model']` |
| `stars:>N` / `stars:>=N` / `stars:N..M` | 支持；`>` 需 URL 编码为 `%3E` | [文档](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories) |
| `pushed:>YYYY-MM-DD` | 支持，**含时间戳形式** `pushed:>2026-10-20T00:00:00Z` 也接受 | 实测 `created:>2026-10-20T00:00:00Z` 返回 200、`total_count=4292` |
| `created:>YYYY-MM-DD` | 支持 | 实测 `created:>2026-10-15 stars:>50 topic:llm` → `total_count=10` |
| `language:` | 支持 | [文档](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories) |
| `in:name,description,readme` | 支持；**省略时只搜 name + description + topics，不搜 README** | 文档原文："When you omit this qualifier, only the repository name, description, and topics are searched." |
| `fork:false` | 可写但**多余**：默认就不含 fork | 实测 `topic:llm stars:>10000` = **267**；加 `fork:true` = **268**（只多 1 个 fork） |
| `archived:false` | 支持 | [文档](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories) |

**`in:` 默认范围的实测交叉验证**（同一 `stars:>100` 过滤）：

| 查询 | total_count |
|---|---|
| `arxiv stars:>100`（默认） | 886 |
| `arxiv in:name,description stars:>100` | 825 |
| `arxiv in:readme stars:>100` | 21695 |
| `arxiv in:name,description,readme stars:>100` | 21695 |

→ 默认值 ≈ name+description+topics（886 比 825 多的 61 个来自 topics 命中），**不是** readme。README 关键词召回量是默认的 24 倍，但噪声极大。

#### A1.3 `sort` / `order` / `per_page`

- `sort=stars`（默认 `best match`）、`sort=updated`、`sort=forks`、`sort=help-wanted-issues`。
- 实测 `sort=updated&order=desc` 返回顺序按 `pushed_at` 严格降序（`05:01:37Z` → `05:01:08Z` → `05:01:13Z`，同分钟内略有乱序）。
- **`sort` 传非法值是静默忽略**：实测 `sort=bogus` 返回 **HTTP 200**、结果正常（回退到 best match），不会 422。别指望用它做校验。
- `per_page` **上限 100，超出被钳制而非报错**：实测 `per_page=150` → `HTTP 200`、只返回 **100** 条。

#### A1.4 速率限制（未认证 vs 认证）

实测 `GET /rate_limit`（未认证）：

```
x-ratelimit-limit: 60        x-ratelimit-resource: core
{"resources":{"core":{"limit":60,...},"search":{"limit":10,"remaining":10,...},
 "graphql":{"limit":0,"remaining":0,...}}}
```

| 资源 | 未认证 | 认证（PAT/OAuth/GitHub App 用户令牌） | 来源 |
|---|---|---|---|
| `core`（大部分 REST） | **60 次/小时（按 IP）** | **5000 次/小时**（按用户） | [文档](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) 原文："The primary rate limit for unauthenticated requests is 60 requests per hour." / "your personal rate limit of 5,000 requests per hour" |
| `search` | **10 次/分钟** | **30 次/分钟**（code search 仍需认证且 10/分钟） | [文档](https://docs.github.com/en/rest/search/search) 原文："For authenticated requests, you can make up to 30 requests per minute … For unauthenticated requests, the rate limit allows you to make up to 10 requests per minute." |
| `graphql` | **不可用（limit=0）**，必须 token | **5000 points/小时** | 实测 + [文档](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api) |
| `GITHUB_TOKEN`（Actions 内） | — | 1000 次/小时/仓库 | [文档](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) |

**真实被限流的返回**（未认证、共享出口 IP）：

```
HTTP 403
{"message":"API rate limit exceeded for 38.244.6.37. (But here's the good news: Authenticated requests get a higher rate limit...)",
 "documentation_url":"https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting"}
```

> 注意：限流是按 **IP** 而非按进程。本机出口是代理共享 IP，实测 10 次/分钟的 search 配额在几分钟内就被耗尽——这是"未认证不可行"的直接证据。

**Secondary rate limit**（[文档](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#about-secondary-rate-limits)）：
- 并发 ≤ **100**（REST + GraphQL 共享）
- 单端点 ≤ **900 points/分钟**（REST）；GraphQL 端点 ≤ 2000 points/分钟
- **90 秒 CPU / 60 秒真实时间**
- 内容生成类请求 ≤ **80/分钟**、≤ **500/小时**
- 触发后返回 403/429，可能带 `retry-after`；文档明确："Continuing to make requests while you are rate limited may result in the banning of your integration." 且 **无法查询 secondary 限额状态**。
- 应对：**串行请求**（文档："you should make requests serially instead of concurrently"）。

**必须带 User-Agent 吗？必须。** 实测（`search` 与 `core` 都测）：

```bash
curl -sS -H 'User-Agent:' https://api.github.com/repos/huggingface/transformers
```
```
HTTP 403
Request forbidden by administrative rules. Please make sure your request has a User-Agent header (.../troubleshooting-the-rest-api#user-agent-required)
```

文档原文："Requests without a valid `User-Agent` header will be rejected. You should use your username or the name of your application for the `User-Agent` value." 并注明 `curl` 默认已带合法 UA（所以只加 `-H 'User-Agent:'` 清空才会踩坑；Python `requests` 默认 UA 也可用，但建议显式设置）。

#### A1.5 条件请求（省配额的关键）

⚠️ 文档与实测有冲突，务必注意前提：

- [文档](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#use-conditional-requests)："Making a conditional request **does not count against your primary rate limit if a `304` response is returned and the request was made while correctly authorized with an `Authorization` header**."
- 实测（**未认证**）：带 `If-None-Match` 拿到 `304`，但 `x-ratelimit-remaining` 仍从 40 掉到 39。

```
HTTP/2 304
etag: W/"e1b358fd59debdd33e7cf0796e86ccc3e2e59b1388e019bc3b32092eb1135d21"
x-ratelimit-remaining: 39
```

**结论：304 免配额只对带 `Authorization` 头且"正确授权"的请求成立**；未认证场景不要指望 304 省配额（共享 IP 下测量有噪声，但保守假设"未认证 304 照扣"更安全）。

---

### A2. "每日新增/活跃相关 repo"的正确做法

#### A2.1 `pushed:>` vs `created:>` 语义差异

| 维度 | `pushed:>日期` | `created:>日期` |
|---|---|---|
| 含义 | 任意分支最近一次 push 时间（文档："will return a list of repositories, sorted by the most recent commit made on any branch"） | 仓库创建时间 |
| 捕获 | **老项目的新活动**（新功能、新论文实现落地） | **全新项目**（首版发布、跟热点新库） |
| 实测样本量 | `topic:llm stars:>500 pushed:>2026-10-18` → **751** | `topic:llm stars:>50 created:>2026-10-15` → **10** |
| 噪声 | 含大量"只改 README/CI"的伪活跃 | 含大量"一天就弃坑"的空壳库 |
| 用途 | 每日"活跃榜" | 每周"新星榜" |

**坑**：`pushed` 会被 **README 改动、CI 配置、依赖升级**触发，不等于"有实质更新"。若要质量，必须二次用 `commits` 看 commit message 或用 `releases` 判断是否真发版。

另外 `pushed:>日期` 与 `sort=updated` 语义高度重叠（`updated_at` 实测 ≈ `pushed_at`），**同时用会双重过滤**，收益不大；`pushed:` 用来卡时间窗，`sort=` 用来定序，二选一即可。

#### A2.2 star 阈值

- 阈值决定信噪比，实测不同阈值的结果量级：
  - `topic:llm stars:>10000` → 267
  - `topic:llm`（无阈值） → 160430
- 推荐双阈值：**主榜 `stars:>300`**（足够挡住个人练手库）+ **新星榜 `stars:>30` 且 `created:>` 近 7 天**（新库还没涨起来）。
- `stars:` 是**当前值**，不是增量；要"涨星快"只能自己存历史快照做差分（Search API 不提供 star 时间序列）。

#### A2.3 topic 搜索 vs 关键词搜索

| 维度 | `topic:llm` | 关键词（`llm in:name,description` 或默认） |
|---|---|---|
| 精度 | 高（作者主动打标，语义明确） | 低（"llm" 会命中 `llm-security` 等无关库） |
| 召回 | 低（大量优质库没打 topic） | 高（实测 `arxiv in:readme` 是默认范围的 24 倍） |
| 稳定性 | 打标不变则结果稳定 | 描述文案一改就进出结果集 |
| 建议 | **主通道**，用 3–8 个 topic 组合（`topic:llm`、`topic:large-language-model`、`topic:paper-implementation`…） | 辅助通道，用 `in:readme` 抓"论文复现"类，但必须叠加 `stars:>` 抗噪 |

注意：`topic:` 多个值是 **OR** 关系（`topic:a topic:b` 命中任一），需要用 URI 编码正确传参。

#### A2.4 排序导致的老 repo 重复问题（重点）

`sort=stars&order=desc` 在**任何时间点**都返回同一批头部仓库——实测 `topic:large-language-model stars:>5000` 总共只有 10 个结果，天天推同一批。

三种解法（按推荐度）：

1. **时间窗 + 本地去重（推荐）**：`pushed:>昨天` + `sort=updated`，只取 `per_page=100`（1000 条上限内足够），本地存 `full_name → last_pushed` 做差分，只推"上次没见过 / pushed_at 变新"的。
2. **双通道并集**：`pushed:>7天前 sort=updated`（活跃）+ `created:>7天前 sort=stars`（新星），各取前 50，按 `full_name` 去重。
3. **避开 `sort=stars`**：`sort=stars` 只适合"首次冷启动建库"，日常增量必须换成 `sort=updated`。

**注意 `sort=updated` 与分页的互斥**：文档明确警告 `sort=updated` 会因条目位置变化导致翻页错乱（"[a] stable sort order … `sort=updated` reorder the list whenever an item changes"），所以增量场景**只取第一页**，不要翻页。

#### A2.5 官方 trending API：没有

`https://github.com/trending` 是服务端渲染网页，无官方 JSON 接口（[github/docs](https://github.com/github/docs) 中无 trending API 条目）。替代方案：

| 替代 | 做法 | 代价 |
|---|---|---|
| Search 近似 | `created:>7天前 sort=stars&order=desc` | 只有"新建库"，漏掉老库爆发 |
| 自建增量榜 | 每天存 `stars` 快照做差分 | 需本地存储，首日无数据 |
| 第三方镜像 | 各类 trending RSS 镜像 | 非官方，稳定性自负 |
| GH Archive / BigQuery | 公开事件流 | 重型，日更延迟大 |

---

### A3. GraphQL Search 是否更好

**结论：对"发现"没有优势，对"批量补数据"有优势。**

- 端点：`POST https://api.github.com/graphql`，**必须 token**。实测无有效 token：

```bash
curl -H 'Authorization: bearer invalid_token_test' -d '{"query":"{repository(owner:\"huggingface\",name:\"transformers\"){stargazerCount}}"}' https://api.github.com/graphql
```
```
HTTP/2 401
{"message":"Bad credentials","documentation_url":"https://docs.github.com/rest","status":"401"}
```

- 配额：[文档](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api) **5000 points/小时/用户**；单次调用节点上限 **500,000**；节点数 = 请求的 `first` × 嵌套层数，超了直接报错。
- `search(type: REPOSITORY, first: 100)` 同样受 **1000 条** 上限约束，代价是节点数按 `first` 算。
- 优势：一次请求拿 `stargazerCount / pushedAt / primaryLanguage / licenseInfo / repositoryTopics / releases` 等多个字段，**把 N 个请求压成 1 个**。实测 REST 需要 3 个请求（repo + commits + releases）的元数据，GraphQL 1 个请求搞定。
- 劣势：必须 token（无法匿名冷启动）；查询成本不透明（要读 `rateLimit { cost }`）；错误处理比 REST 差（部分字段报错整单失败）。

**Token 权限最小集**：

| 目标 | 最小 token | 依据 |
|---|---|---|
| 只读 public 仓库（REST + GraphQL + Search） | **Classic PAT，不勾任何 scope**（`(no scope)`） | [文档](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)：`(no scope)` = "Grants read-only access to public information (including user profile info, repository info, and gists)" |
| 同上，用 fine-grained PAT | **Fine-grained PAT，Repository access 选 "Public repositories (read-only)"**（甚至不选仓库也有全公开只读） | [文档](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)：不选任何仓库时 "Tokens always include read-only access to all public repositories" |
| 需要 star 仓库 | 才需要 `public_repo` | 文档："Also required for starring public repositories" |

→ **`public_repo` 是不必要的**（它给 public 仓库的读**写**权）。只读场景用 "no scope" classic PAT 或 fine-grained 的 public read-only 即可，泄露风险最小。

---

### A4. 已关注 repo 的 release 跟踪

三种方式实测对比：

#### A4.1 `/repos/{owner}/{repo}/releases`（推荐）

```bash
curl -sS 'https://api.github.com/repos/huggingface/transformers/releases?per_page=1'
```
```json
[{"tag_name":"v5.20.2","name":"Patch release v5.20.2","draft":false,"prerelease":false,
  "published_at":"2026-10-19T17:45:37Z","created_at":"2026-10-19T17:37:58Z",
  "body":"# Patch release: v5.20.2 ..."}]
```
- 响应头带 `etag`，可 `If-None-Match` → 304（**带 Authorization 时**不扣配额）。
- 一次请求含 `body`（changelog），可直接喂给摘要模型。
- 消耗 `core` 配额（1 次/仓库）。

#### A4.2 `releases.atom`（免鉴权，但体积不可控）

```bash
curl -sS -D - 'https://github.com/huggingface/transformers/releases.atom'
```
```
HTTP/2 200
content-type: application/atom+xml; charset=utf-8
etag: W/"b43000cc4b42de83d2ab5460ddbd2ff6"
cache-control: max-age=0, private, must-revalidate
bytes=1399542   time=2.86s
```
- **免鉴权、不消耗 API 配额**（响应头无 `x-ratelimit-*`），实测 200。
- 固定 **10 条 entry**，含 `<updated>`、`<title>`、完整 `<content>`。
- **体积**：`huggingface/transformers` 一次 **1.4 MB**（正文太长）；小仓库 `jingyaogong/minimind` 仅 **1818 字节**。→ 只适合"判断有没有新 release"的粗筛，且必须带 `If-None-Match`。
- **更新延迟 未验证**：`cache-control: max-age=0, private, must-revalidate` 说明源站要求每次回源，但 CDN 边缘实际延迟本次未量化（未做"发版 → 抓 feed"的时序实验）。

#### A4.3 `tags`

```bash
curl -sS 'https://api.github.com/repos/huggingface/transformers/tags?per_page=3'
```
```json
[{"name":"v5.20.2","commit":{"sha":"18329f1065382e54db698e242cf98bd3f3e5a..."}}]
```
- 只有 tag 名 + commit sha，**没有发布时间、没有 changelog**。
- 很多仓库打 tag 不发 release（也有先发 release 后补 tag），**tag 数 ≠ release 数**。
- 结论：**tags 只用于兜底**（如 release 为空但需要知道版本号），日常跟踪用 `/releases`。

---

### A5. 仓库内容摘要：各字段从哪拿

| 字段 | 最优来源 | 实测 | 备注 |
|---|---|---|---|
| README 正文 | `https://raw.githubusercontent.com/{o}/{r}/{branch}/README.md` | `HTTP 200, 17010 bytes, time 1.84s`，`cache-control: max-age=300` | **不消耗 API 配额**、免鉴权。缺点：要自己猜文件名/分支（`README.md`/`readme.md`/`README.rst`），建议先用 API 拿 `default_branch` |
| README（准确路径） | `GET /repos/{o}/{r}/readme` + `Accept: application/vnd.github.raw+json` | `HTTP 200, 17010 bytes`，同内容 | **1 次 core 配额**，但自动处理文件名/分支/重定向，推荐生产用这个 |
| stars / forks | `GET /repos/{o}/{r}` → `stargazers_count` / `forks_count` | `167966` / `34947` | 与 Search 结果里的值一致，无需二次请求 |
| topics | 同上 → `topics[]` | `['audio','deep-learning','deepseek',...]` | 需 `Accept: application/vnd.github+json`（默认已含） |
| license | 同上 → `license.spdx_id` | `{"key":"apache-2.0","spdx_id":"Apache-2.0"}` | 无 license 时为 `null` |
| 最近 commit | `GET /repos/{o}/{r}/commits?per_page=1` | `sha f348d3dc, committer_date 2026-10-21T19:09:36Z` | 也可用 repo 的 `pushed_at` 省一次请求，但 commit 能拿 message |
| 仓库描述 | `GET /repos/{o}/{r}` → `description` | `"🤗 Transformers: the model-definition framework..."` | 可直接做一句话摘要 |

**官方 trending API：确认没有。** 见 A2.5。

---

### A6. 速率与配额核算（50–200 候选/天 + 20 README/天）

按"每天 1 次扫描"估算：

| 步骤 | 请求数 | 资源 |
|---|---|---|
| Search 候选（3–8 个 topic × 1 页，pages=1） | 3–8 | `search` |
| 候选去重后取 top 50–200，补元数据（仅对"新的"候选） | 50–200 | `core`（若 Search 结果字段够用，可省掉这步——Search 已返回 stars/topics/pushed_at） |
| 读 20 个 README | 20 | `core`（走 API）或 **0**（走 raw.githubusercontent） |
| Release 检查（已关注 20 个 repo） | 20 | `core`（带 ETag → 多数 304） |
| 最近 commit（可选，20 个） | 20 | `core` |

- **未认证（60/小时）**：光"50 个元数据 + 20 README"就 70 次，**必然爆**。且本机是共享出口 IP，实测几分钟就被别人打满 403。→ **未认证明确定不可行**。
- **1 个 classic PAT / fine-grained PAT（5000/小时）**：最坏 8 + 200 + 20 + 20 + 20 ≈ **268 次/天**，占配额 5.4%，**完全够用，还留有重试余量**。
- **Search 的 10/分钟（未认证）才是真瓶颈**：3–8 个 topic 查询要 3–8 分钟摊开（"每天一次"没问题，但**不要并发**）。
- 优化手段：① Search 结果已含 stars/topics/pushed_at → 砍掉元数据请求；② README 走 raw 域名 → 砍掉 20 次 core；③ Release 用 ETag/`If-None-Match`；④ 串行 + 指数退避，避免 secondary limit。

---

## B 部分：微信推送通道

> 说明：所有通道均在本机（中国大陆网络）实测可达，下面的错误码是**用无效凭据请求真实生产端点**得到的，用于确认端点形态与鉴权方式；真实发送未做（无凭据）。

### B1. Server 酱（sct.ftqq.com）

**实测请求 / 返回**：

```bash
curl -X POST 'https://sctapi.ftqq.com/SCT_INVALID_KEY_123.send' \
  --data-urlencode 'title=test' --data-urlencode 'desp=hello'
```
```
HTTP/2 400
content-type: application/json
server: openresty
{"message":"[AUTH]错误的Key","code":40001,"info":"错误的Key","args":[null],"scode":461}
```

**核实结论**：

| 项 | 值 | 来源 |
|---|---|---|
| SendKey | 微信扫码登录后在 `/sendkey` 页生成，一段专属密钥 | 官网前端文案："SendKey 是你的专属推送密钥…微信扫码登录即可生成" |
| 接口 URL | `POST https://sctapi.ftqq.com/<SendKey>.send`（也支持 `.send` 后接 `?` 查询参数形式） | 官网前端："POST https://sctapi.ftqq.com/<SendKey>.send" |
| 参数 | `title`（标题）、`desp`（正文，**支持 Markdown**）、`short`（卡片摘要，≤64 字）、`tags`、`channel` | 官网前端：`short: 消息卡片内容，选填。最大长度64` |
| Markdown | 支持（`desp` 渲染 Markdown），**两次回车才换行** | 官网前端 placeholder："输入消息内容，支持 Markdown。注意 Markdown 语法中两次回车才是换行" |
| 免费额度 | **每天 5 条** | 官网前端原文："免费额度每天 5 条" |
| 内容长度 | **最大 32 KB**；消息卡片只截取**前 30** 字显示 | 官网前端："最大长度为 32KB，消息卡片截取前 30 显示" |
| 是否需要实名/付费 | 免费额度无需付费；更高额度需会员（**会员价格与实名要求未验证**） | 官网有"年费会员"入口，具体条款未核实 |
| 到达形态 | 微信服务号「Server酱」会话消息（卡片 + 详情页），点开看 Markdown 全文 | 官网描述"一个 HTTP 请求，就能把…推送到微信" |

**评价**：接入成本最低（一个 URL 即可），32 KB 足够放 6000 汉字，**但微信会话卡片只露 30 字**，长文阅读体验差。

### B2. PushPlus（pushplus.plus）

**实测请求 / 返回**：

```bash
curl -X POST 'https://www.pushplus.plus/send' -H 'Content-Type: application/json' \
  -d '{"token":"INVALID_TOKEN_TEST","title":"t","content":"c","template":"markdown"}'
```
```
HTTP 200
{"code":903,"data":"无效的用户token","msg":"用户令牌不正确"}
```

**核实结论**：

| 项 | 值 | 来源 |
|---|---|---|
| token | 用户 token（也可用"消息 token"，可直接拼在 URL 后 `/send/{token}`） | 文档参数表："token 是 无 用户token或消息token，可直接加到请求地址后" |
| 接口 | `POST http://www.pushplus.plus/send`（HTTPS 同域可用），JSON 或 form | 文档 |
| template | `html`（**默认**）、`markdown`、`txt`、`json`、`form`、`doc`、`excel` | 文档参数表："template 否 html 发送模板" |
| 渠道 channel | `wechat`（默认，免费）、`app`（免费）、`extension`（免费）、`webhook`（免费）、`sms`（**收费，10 积分/条 ≈ 0.1 元**）、`mail` 等 | 文档渠道枚举表 |
| 免费额度 | **未验证**（文档站"额度说明"页 404，未能取到确切条数；页面导航存在"系统功能额度"入口） | — |
| 内容长度 | 文档只提示"GET 请求受限于 URL 长度，大段内容请用 POST"，**未给明确字符上限**；微信侧实际渲染上限未验证 | 文档 |
| 实名 | **2024-08-01 起未实名用户无法调用发送消息接口** | 站内公告原文："2024年8月1日起未实名的用户将会无法调用发送消息接口和支付功能。" |
| 异步语义 | `code=200` **只代表服务端收到请求**，不代表发送成功；返回 `data` 为消息流水号，可回调/查询 | 文档："仅代表服务端收到请求了，并不表示发送消息成功了" |
| 公众号渠道限制 | 依赖其"pushplus 推送加"服务号；模板不可自定义（FAQ 有条目"微信消息模板是否可以自定义"） | 文档 FAQ 索引 |

**评价**：功能最全（模板多、渠道多、有 webhook/回调），**但强制实名**，且 200 只是"收到"。

### B3. WxPusher（wxpusher.zjiecode.com）

**实测请求 / 返回**：

```bash
curl -X POST 'https://wxpusher.zjiecode.com/api/send/message' -H 'Content-Type: application/json' \
  -d '{"appToken":"AT_INVALID","content":"hello","summary":"s","contentType":3}'
```
```
HTTP 200
{"code":1001,"msg":"appToken不正确","data":null,"success":false}
```

**核实结论**：

| 项 | 值 | 来源 |
|---|---|---|
| 鉴权 | `appToken`（标准推送，创建应用获得）；另有"极简推送 SPT"（扫码即得，无需建应用） | 官方文档首页："标准推送 API：使用 appToken，通过 UID 单发或 Topic 群发…极简推送 SPT：无需创建应用，扫码获取 SPT 后即可发送" |
| 接口 | `POST https://wxpusher.zjiecode.com/api/send/message` | 官方文档示例（与实测一致） |
| 定向 | `uids`（单发）/ `topicIds`（群发）/ 二者组合 | 文档首页 |
| 消息类型 contentType | `1`=纯文本，`2`=HTML，`3`=Markdown（按实测请求参数名 `contentType`） | 文档（具体枚举值以官方 OpenAPI 为准） |
| Markdown/HTML | 支持（contentType=3 / 2） | 文档 |
| 免费额度 | 官方称"**永久免费**"（具体每日条数上限 **未验证**） | 文档首页原文，页面"最后更新：2026-10-10" |
| 是否需关注公众号 | **未验证**（文档强调可投递到 Android/iOS/HarmonyOS/桌面客户端及"微信 ClawBot"，历史版本依赖关注其公众号） | — |
| 额外能力 | `url` 支持自定义 URL Scheme、点击通知直接打开 | 文档首页 |

**评价**：文档最新（2026-10-10）、宣称永久免费、支持 Markdown/HTML、有 Topic 群发，适合"多设备 + 多读者"。国内个人开发者常用。

### B4. 企业微信群机器人 webhook

**实测请求 / 返回**：

```bash
curl -X POST 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=INVALID-KEY' \
  -H 'Content-Type: application/json' -d '{"msgtype":"markdown","markdown":{"content":"hello"}}'
```
```
HTTP 200
{"errcode":93000,"errmsg":"invalid webhook url, hint: [1792645461552652872615655], from ip: 38.244.6.37, more info at https://open.work.weixin.qq.com/devtool/query?e=93000"}
```

**核实结论**（[官方文档](https://developer.work.weixin.qq.com/document/path/91770)，页面"最后更新：2025/08/07"）：

| 项 | 值 |
|---|---|
| URL 形态 | `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<UUID>`（key 在群机器人配置页生成） |
| msgtype | `text` / `markdown` / `markdown_v2` / `image` / `news` / `file` / `voice` / `template_card`（**8 种**） |
| 单条上限 | `markdown` 与 `markdown_v2` 的 `content` **最长 4096 字节，必须 UTF-8**；image base64 前 ≤2 MB |
| 表格 | **`markdown` 不支持表格；`markdown_v2` 支持表格**（文档示例含 `| 姓名 | 文化衫尺寸 | 收货地址 |`） |
| markdown_v2 限制 | 不支持字体颜色、不支持 `@群成员`；客户端 <4.1.36（安卓 <4.1.38）会退化成纯文本 |
| 频率 | **每个机器人 ≤20 条/分钟**（文档："每个消息推送发送的消息不能超过20条/分钟"） |
| 是否需要企业 | **需要企业微信账号**（注册企业微信，创建内部群 → 添加群机器人）。个人可免费注册，**未认证状态是否可用群机器人 未验证** |
| 能否推到个人微信 | **不能直接推**。群机器人只发到企业微信群；需在微信里接收需开通"企业微信消息"并关联，或成员在微信中接收企业微信消息（体验受限） |
| 公网回调 | **不需要**（纯出站 POST） |

**评价**：**唯一免费且支持表格的通道**，20 条/分钟对每天 1 篇足够，稳定性最好（腾讯官方）。缺点是 4096 字节/条 + 需要企业微信。

### B5. 企业微信应用消息 & 公众号模板消息/客服消息

| 通道 | 门槛 | 适用性 |
|---|---|---|
| **企业微信应用消息** | 需企业微信 + 自建应用（`corpid` + `corpsecret` + `agentid`），应用可见范围要配置 | 实测 `GET /cgi-bin/gettoken?corpid=INVALID&corpsecret=INVALID` → `{"errcode":40013,"errmsg":"invalid corpid..."}`，端点正常。适合"公司内部团队"，个人用门槛偏高；单应用频率限制**未验证** |
| **微信公众号模板消息** | 需**认证服务号**（企业主体 + 300 元/年认证费，**未验证**当前价格）+ 用户 48 小时内有交互 + 模板需审核 | 实测 `POST /cgi-bin/stable_token`（`appid/secret`）→ `{"errcode":40013,"errmsg":"invalid appid rid: ..."}`，端点正常。**个人订阅号无法用**，不适合本项目 |
| **公众号客服消息** | 同上，且受 **48 小时会话窗口**限制（用户最后一次互动后 48h 内才能发） | 定时推送场景**不可靠**（用户不互动就发不出），不推荐 |

> 结论：B5 两类都是"企业/认证主体 + 用户交互前置条件"，**不适合作为每日自动推送的主通道**。

### B6. 两张对比表

#### 表 1：GitHub 抓取方式对比

| 方式 | 鉴权 | 配额 | 能拿到什么 | 适合 | 主要坑 |
|---|---|---|---|---|---|
| REST Search `/search/repositories` | 可选（推荐 token） | 10/min 未认证；30/min 认证；**1000 条结果上限**、扫描 4000 仓库 | 候选列表 + stars/topics/pushed_at/description | **每日候选发现（主通道）** | 结果上限 1000；`sort=stars` 老面孔重复；查询 ≤256 字符、≤5 个布尔运算符 |
| REST 单仓库 `/repos/{o}/{r}` | 可选 | core 60/h 未认证；5000/h 认证 | stars/topics/license/pushed_at/description | 补元数据 | 未认证 60/h 根本不够 |
| REST `/repos/{o}/{r}/readme` | 可选 | core（1 次/仓库） | README 原文（自动定位文件名/分支） | 生产取 README | 消耗配额 |
| `raw.githubusercontent.com` | **免鉴权** | **不占 API 配额** | README 原文 | **首选取 README** | 需自己拼 `branch/filename`；`max-age=300` |
| REST `/releases` | 可选 | core（支持 ETag→304） | tag/发布时间/changelog 正文 | **release 跟踪首选** | 1 次/仓库 |
| `releases.atom` | **免鉴权** | 不占 API 配额 | 最近 10 条 release（含正文） | 粗筛"有没有新版" | 体积可达 MB 级；更新延迟未验证 |
| `/tags` | 可选 | core | tag 名 + commit sha | 兜底 | 无时间、无 changelog |
| GraphQL `search` | **必须 token** | 5000 points/h、50 万节点/次 | 多字段一次取回 | 已知 repo 列表批量补数据 | 不能匿名；1000 条上限同 REST；成本不透明 |
| `/trending` 官方 API | — | — | — | **不存在** | 只能用 Search 近似 |

#### 表 2：微信推送通道对比

| 通道 | 接入难度 | 费用 | 直达个人微信 | Markdown | 表格 | 链接 | 单条长度 | 频率限制 | 稳定性/封禁风险 | 需公网回调 | 关键门槛 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Server酱** | ★（一个 URL） | 免费 5 条/天，超额需会员 | ✅ 服务号会话 | ✅ | ❌ | ✅ | **32 KB**（卡片仅显示前 30 字） | 5 条/天（免费） | 中（第三方，依赖其服务号） | ❌ | 微信扫码即可，**最低** |
| **PushPlus** | ★★ | 免费（短信 0.1 元/条） | ✅ 公众号 | ✅ `template=markdown` | ❌（`html` 模板可凑合） | ✅ | 未给硬上限（GET 有 URL 限制） | 免费额度**未验证** | 中 | ❌（回调可选） | **必须实名**（2024-08-01 起） |
| **WxPusher** | ★★ | 宣称永久免费 | ✅（公众号/客户端） | ✅ `contentType=3` | ❌ | ✅（支持 URL Scheme） | 未验证 | 未验证 | 中 | ❌ | appToken；是否需关注公众号**未验证** |
| **企业微信群机器人** | ★★ | 免费 | ⚠️ 仅企业微信群（微信侧需关联） | ✅ `markdown`/`markdown_v2` | ✅ **仅 markdown_v2** | ✅ | **4096 字节** | **20 条/分钟** | **高**（腾讯官方） | ❌ | 需注册企业微信 |
| **企业微信应用消息** | ★★★★ | 免费 | ⚠️ 同上 | ✅ | ✅ | ✅ | 未验证 | 未验证 | 高 | ❌ | 企业 + 自建应用 + agentid |
| **公众号模板消息** | ★★★★★ | 认证费（未验证） | ✅ | ❌（模板固定） | ❌ | ✅ | 模板字段限制 | 需 48h 内有交互 | 中 | ✅（服务器配置） | **认证服务号**，个人不可用 |
| **公众号客服消息** | ★★★★★ | 同上 | ✅ | 有限 | ❌ | ✅ | — | **48 小时窗口** | 中 | ✅ | 认证服务号 + 用户互动 |

---

## 推荐方案

### 针对"每天一篇 3000–6000 字长摘要（多论文条目 + 链接）"

**先明确一个硬约束**：微信生态里**没有任何免费通道能优雅承载 6000 字**。企业微信机器人单条 4096 字节 ≈ 1300 汉字，要 5 条；Server酱能放 32 KB 但会话卡片只露 30 字，用户要点进详情页。所以**"全文进微信"是错的目标**，正确形态是 **摘要卡 + 网页全文链接**。

#### 首选方案 1：Server酱「摘要卡 + 网页链接」（零门槛、最快落地）

- **形态**：单条推送。`title` = 日期 + 今日主题；`short` = 30 字内一句话钩子；`desp` = Markdown 摘要（3–5 条要点，每条含论文名 + 一句结论 + 链接）+ "阅读全文"指向你自己的静态页（GitHub Pages / Cloudflare Pages）。
- **为什么选它**：① 免费 5 条/天，每天 1 篇完全够；② 一个 URL 就是全部接入代码，无需注册企业、无需实名、无需公网回调；③ 32 KB 上限让你**可以**直接塞 3000 字当兜底（用户不点链接也能在详情页读）。
- **代价**：微信卡片信息量极小（30 字），转化依赖用户点开；第三方服务，长期稳定性一般。
- **实现要点**：`desp` 里 Markdown 两次回车才换行；把"表格"改成列表（微信不渲染表格）。

#### 首选方案 2：企业微信群机器人 `markdown_v2`「1 条总览 + N 条论文卡」（要表格/结构化的最佳解）

- **形态**：分条推送，控制在 3–6 条内（远低于 20 条/分钟）：
  1. 总览条：`今日 5 篇 · 关键词` + 网页全文链接；
  2. 每篇论文一条 `markdown_v2`：标题（`### `）+ 作者/会议 + 3 行要点 + 表格（`| 指标 | 数值 |`）+ arXiv/代码链接；
  3. 可选：末尾一条"已关注仓库的新 release"。
- **为什么选它**：① **唯一免费支持表格**的通道（`markdown_v2`），论文对比表能直接渲染；② 腾讯官方，封禁风险最低；③ 4096 字节/条 × 5 条 ≈ 6500 汉字，刚好覆盖 3000–6000 字；④ 不需要公网回调。
- **代价/门槛**：需注册企业微信并建内部群（**未认证企业能否用群机器人 未验证**，落地前先花 5 分钟验证）；只能发到企业微信群，不能直接进个人微信会话。
- **降级**：若坚持"进个人微信"，把方案 2 的每条内容同时用 Server酱 发一遍（每天 ≤5 条仍合规）。

#### 不推荐作为首选

- **PushPlus**：功能最全但**强制实名**，且 `code=200` 只是"已接收"，排障成本高。可作为方案 1 的备份通道（同一摘要双发）。
- **WxPusher**：可用，但额度/公众号依赖未核实，适合做第二备份。
- **企业微信应用消息 / 公众号模板消息 / 客服消息**：需企业资质或认证服务号 + 48h 窗口，**与"个人每日自动推送"场景不匹配**，仅在有企业主体时考虑。
- **境外服务（Telegram Bot / Bark / ntfy 等）**：本机在中国大陆，Telegram 需代理；Bark 仅 iOS。均不列为首选。

#### 落地建议（组合拳）

```
GitHub 侧：1 个 fine-grained PAT（public read-only）
  → 每天 1 次：3–8 个 search（topic + stars + pushed:昨天, sort=updated, per_page=100）
  → 本地去重（full_name 集合）→ 取新候选 top N
  → raw.githubusercontent 拉 README（不占配额）
  → 汇总成 3000–6000 字 Markdown → 发布到静态页
微信侧：主 = Server酱 单条摘要卡（含全文链接）
        备 = 企业微信 markdown_v2 分条（含表格）
```

---

## 待确认问题

**A. GitHub**

1. `releases.atom` 的**实际更新延迟**：需做"发一个 release → 轮询 feed 记录首次出现时间"的实验（本次只验证了可达性与体积）。
2. 认证态下 `304` **是否真的不扣配额**：本次无 token，未认证实测 304 仍扣了 1 次；需用真 token 做配对实验（文档说带 `Authorization` 时不扣）。
3. `topic:` 多值时是 OR 还是 AND：本次只验证单 topic，多 topic 组合需再测。
4. Search 的 `total_count` 是否也会被 1000 上限截断（本次 `total_count=21695` 而只能翻到 1000 页，说明 `total_count` 是全量、分页受限，但边界行为待确认）。
5. fine-grained PAT 只选 "Public repositories (read-only)" 时，**GraphQL search 是否可用**（GraphQL 对 fine-grained 的支持历来有坑，需实测）。

**B. 推送**

1. **PushPlus 免费额度确切条数**（文档站"额度说明"页返回 404，未取到）。
2. **WxPusher 每日条数上限**、是否需要用户关注其公众号才能收消息。
3. **Server酱** 免费额度之外是否**要求实名**、会员价格；`channel` 参数能否转发到企业微信/钉钉群。
4. **企业微信未认证企业**能否创建群机器人并正常发消息（群机器人是否有"仅认证企业可用"的限制）。
5. **公众号模板消息/客服消息**当前（2026）政策：认证费用、48h 窗口是否仍生效、订阅通知是否已完全替代模板消息。
6. 微信侧对 **Markdown 表格**的渲染：Server酱/PushPlus 详情页对表格的支持程度（本次只确认企业微信 `markdown_v2` 支持表格）。
7. 各通道对 **URL 数量/外链跳转**的限制（微信内打开外部链接是否有拦截/提示页）。

---

## 附：本次调研的可复现命令清单

```bash
# 配额总览（未认证）
curl -sS https://api.github.com/rate_limit

# 候选发现
curl -sS 'https://api.github.com/search/repositories?q=topic:llm+stars:%3E500+pushed:%3E2026-10-18&sort=updated&order=desc&per_page=100'

# 元数据
curl -sS https://api.github.com/repos/huggingface/transformers

# README（不占配额）
curl -sS https://raw.githubusercontent.com/huggingface/transformers/main/README.md

# Release（带 ETag 轮询）
curl -sS -D - https://api.github.com/repos/huggingface/transformers/releases?per_page=1

# Release feed（免鉴权）
curl -sS -D - https://github.com/huggingface/transformers/releases.atom

# 推送通道连通性（无效凭据，仅验证端点）
curl -X POST 'https://sctapi.ftqq.com/<KEY>.send' -d 'title=t&desp=d'
curl -X POST 'https://www.pushplus.plus/send' -H 'Content-Type: application/json' -d '{"token":"x","content":"c"}'
curl -X POST 'https://wxpusher.zjiecode.com/api/send/message' -H 'Content-Type: application/json' -d '{"appToken":"x","content":"c","contentType":3}'
curl -X POST 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<KEY>' -H 'Content-Type: application/json' -d '{"msgtype":"markdown","markdown":{"content":"hi"}}'
```
