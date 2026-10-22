# 自动学术速递 · 调研综合与方案建议

> 2026-10-22。本文把 01–05 号调研笔记收敛成一个可讨论的方案。所有“实测”均指本机 curl 真实请求；未实测的会标注。

## 0. 结论先行

**目标可行，且不需要自建服务器、不需要额外 LLM API key、不需要公众号。**

推荐形态：

> **一个 DSH skill（SKILL.md + 两个确定性 Python 脚本）+ 一张任务看板卡（每天 08:00 cron）**
>
> `collect.py` 抓取/归一化/去重/打分 → 会话模型按模板写中文日报 → `push.py` 排版并推送到微信 → SQLite 记录已推送。

关键选择：

| 决策 | 建议 | 理由 |
|---|---|---|
| 论文主源 | **PubMed E-utilities（`datetype=edat`）** | 唯一可靠的“入库日期”增量；摘要免费；无 key 3 req/s 够用 |
| 论文补充源 | **Europe PMC（`resultType=core`）** | 一次请求拿 1000 条；覆盖 MEDLINE + PMC + **预印本**（含 bioRxiv/medRxiv/Research Square） |
| 预印本 | **Europe PMC + arXiv/Research Square RSS** | EPMC 覆盖 bioRxiv/medRxiv/Research Square/ChemRxiv/SSRN，但索引延迟 1–2 天；arXiv/RS 的 RSS 更快且带摘要 |
| 期刊官网 | **不爬官网**；用 PubMed/EPMC 的期刊过滤 + 可选 RSS 目录 | 官网反爬/改版/ToS 风险高；RSS 摘要覆盖不一致 |
| GitHub | **Search API + 个人 token**；已关注 repo 用 `releases.atom` | 未认证 search 在共享出口 IP 上实测已被耗尽；token 是硬前提 |
| 微信 | **Server酱 Turbo**（首选）/ 企业微信应用消息（备选） | 个人微信没有官方 API；Server酱 3 分钟接通、免费 5 条/天、单条 32KB，一天一条日报够用 |
| 定时 | **任务看板 cron**，`Asia/Shanghai`，默认 08:00 | 用户已有看板；有执行历史、手动重跑、权限门 |
| 摘要 | **仅摘要 + 结构化 JSON + 证据句**；top 5–10 才考虑全文 | 成本可控、幻觉可控；500 篇全文级摘要既贵又没人看 |

## 1. 已实测打通的环节

| 环节 | 实测结果 |
|---|---|
| PubMed esearch/efetch | 200；`reldate=7&datetype=edat` 命中 157；`efetch retmode=xml` 有 `AbstractText` 结构化小节 |
| Europe PMC | 200；`FIRST_PDATE:[...]` + `SRC:PPR` 命中预印本；`core` 直接给 `abstractText`；`pageSize` 上限 1000 |
| arXiv API | 200；`cat:cs.LG AND submittedDate:[...]` 两天 402 条；Atom 可解析；`published` 是 v1 投稿时间，不等于公告时间 |
| arXiv RSS | `rss.arxiv.org/rss/cs.LG` 200；379 条/天；`announce_type=new/replace` + 摘要，适合日更 |
| bioRxiv API | 200；单日 bioRxiv 237 / medRxiv 71 条；每页固定 30 条；**没有关键词检索** |
| Research Square | RSS 200（2.4MB，1000 条约 3 天，**含 `<abstract>` 全文、作者、DOI**）——可直接用，不必爬 |
| 期刊 RSS | Nature/Science/Cell/NEJM/Lancet/PNAS 全部 200；但都是**期次级**，多数只有卷期页码，不适合日更 |
| GitHub Search | 未认证 10/min 且共享 IP 已被打满；认证后 30/min、core 5000/h；Search 最多返回 1000 条 |
| GitHub releases | `github.com/{owner}/{repo}/releases.atom` 200，无需 token；大库可能 1.4MB |
| Server酱 | 端点 200，错误 key 返回 `{"code":40001}`；官方确认 markdown、5 条/天、`desp` 上限 32KB |
| WxPusher | 端点 200，错误 token 返回 `code:1001`；40k 字符、markdown、永久免费 |
| 任务看板 | 本机账本 `Asia/Shanghai`；cron/时区/权限门/验收门均已确认 |

## 2. 数据源矩阵

| 源 | 关键词检索 | 日期增量 | 摘要 | 鉴权/限流 | 定位 |
|---|---|---|---|---|---|
| PubMed | 强（`[tiab]` 自动扩 MeSH） | **`edat` 入库日，正确** | efetch XML | 无 key 3 req/s | **主源** |
| Europe PMC | 强 | `FIRST_PDATE` / `CREATION_DATE` | `core.abstractText` | 无 key；官方限流未取得 | **补充/预印本** |
| arXiv | 强（`all:/ti:/abs:/cat:`） | API `submittedDate`；RSS 按公告 | Atom `summary` | 1 请求/3 秒、单连接 | CS/物理主源；RSS 判新增，API 做检索 |
| bioRxiv/medRxiv | **无** | 日期区间全量 | `abstract` | 30 条/页，单日约 11 页 | 可选完整性补充 |
| Research Square | 无（RSS 全站） | RSS（近 3 天） | **RSS `<abstract>` 有全文** | RSS 2.4MB | 免费增量源 |
| 期刊 RSS | 无（本地过滤） | 期次目次 | 多数没有 | 无 | 只做 TOC/新闻，不做日更主源 |
| GitHub Search | 强（qualifier） | `pushed:`（活跃）/`created:`（新库） | README（raw 不计配额） | **token 必需**；1000 条上限 | **repo 主源** |
| GitHub releases.atom | — | 新 release | release notes | 无 | 已关注 repo |
| OpenAlex | 强 | 有 | 倒排索引 | **$0.10/天共享额度；cursor 要 key** | 只按 DOI 补元数据 |
| Semantic Scholar | 强 | 有 | `tldr` | **实测常年 429** | 只做 TLDR 兜底 |
| Crossref | 中 | `from-pub-date` | 基本没有 | 1 req/s | DOI/期刊名补全 |

### 必须记住的坑

1. **PubMed `efetch` 传 `retmode=json` 会 200 + 静默返回纯文本**；摘要必须 `retmode=xml`。
2. **`reldate=N` 实际是 N+1 天窗口**（含今天）；每日增量用 `datetype=edat`，不要用 `pdat`（会漏掉“早出版、晚入库”的文章）。
3. **Europe PMC `sort` 必须带方向**（`P_PDATE_D desc`），单独 `P_PDATE_D` 会 503；`pageSize` 上限 1000，0 会破坏 JSON。
4. **OpenAlex 不再是免费无限**：无 key 每天 $0.10、同 IP 共享，约 100 次关键词搜索；cursor 第二页起 401。
5. **GitHub 未认证 search 不可依赖**：10 req/min，共享 IP 已被别人打满；建 token 是配置第一步。Search 每次最多 1000 条，`per_page=150` 会被静默钳到 100。
6. **Research Square RSS 其实有摘要**：`<abstract>` 是完整摘要，另有 `<authors>`/`<doi>`；官方 JSON API 要申请 token 且 robots 禁 `/api/`，**不要爬 API，读 RSS 或 EPMC 即可**。
7. **arXiv 的“新”不等于“今天公告”**：API `<published>` 是 v1 投稿时间；公告按美东 14:00 截断、20:00 发布，周五到周一合并。只看昨天会漏，**回溯至少 4 天**；要精确判新增用 RSS 的 `announce_type: new`（跳过 replace）。
8. **期刊 RSS 是期次级，不是日更**：Science/NEJM/PNAS 的 description 只有卷期页码；只有 Lancet/Cell 带摘要节选。要摘要就按期刊名回查 PubMed/EPMC，别指望 RSS。
9. **微信长度**：Server酱 `desp` 32KB，6000 字中文日报（约 18KB）能装下，但通知卡片只预览前 30 字；企微群机器人 markdown 单条 4096 字节，6000 字必须拆 4–5 条。
10. **Server酱一天只有 5 条**：日报 + 失败重试要算着用；不要把每条论文单独发。

## 3. 微信推送通道

| 通道 | 到达 | 免费额度 | 长度 | Markdown | 门槛 | 评价 |
|---|---|---|---|---|---|---|
| **Server酱 Turbo** | 个人微信（服务号会话） | **5 条/天**；会员 1000 条/天（39 元/年） | **`desp` 32KB** | ✅ 表格/图片 | 扫码拿 SendKey | **首选**，一天一条日报够用；通知卡片只预览前 30 字，点开看全文 |
| 企业微信应用消息 | 微信（企微应用会话，经微信插件） | 免费、额度宽松 | 完整 | ✅ | 注册企业微信 + 建应用 + 拿 secret | 备选；配置 30 分钟，长期最稳 |
| PushPlus | 个人微信 | 200 条/天 | 较长 | ✅ | **必须实名认证**（2024-08-01 起） | 额度大，但实名是门槛 |
| WxPusher | App / 微信 ClawBot（**是否直达个人微信未验证**） | 永久免费 | **40k 字符 / 65k 字节** | ✅ | 扫码 SPT 或建应用 | 长文最强，但微信到达方式需先验证 |
| 企业微信群机器人 | 企微群（不进私聊） | 免费 | **4096 字节**，20 条/分钟 | ✅ 子集（仅 markdown_v2 支持表格） | 有群即可 | 太短，长日报要拆 4–5 条 |
| 公众号模板消息 | 服务号会话 | 依配额 | — | — | **认证服务号（企业主体，年审 300 元）** | 个人不可行 |

**建议**：先接 Server酱（快），把通道做成可插拔；如果用户已有企业微信，再加企微应用消息作为主通道。

**长度策略**：日报正文控制在 5000–6000 汉字（约 15–18KB），Server酱一条能装下；企微群机器人按 `##` 分节拆 4–5 条，带“（1/4）”后缀，绝不从一条论文中间截断。**不需要为了长度自建网页**；如果以后想“摘要卡 + 全文链接”，再考虑 GitHub Pages/Gist。

## 4. 任务看板怎么接

- 一张卡：`每日学术速递`，Prompt 固定三步（collect → 写 digest → push）。
- cron：`0 8 * * *`，`timeZone: Asia/Shanghai`，不限次数。
- 工作区：本仓库；权限 `workspace-write`（要写 `state/`、`out/`）。
- **Host 必须在线**：看板不唤醒睡眠机器；错过的触发点**不补跑**。所以 `collect.py` 用 `state.last_success` 做 2–7 天补窗，而不是固定“昨天”。
- **权限门**：卡片权限高于部署默认时，cron 会拒绝，直到人在 UI 确认。首次配置后手动跑一次确认。
- **验收门**：看板默认的 `/goal` 总开关是关的；开了以后每张 goal 卡要过 6 次裁判调用。对“抓取+总结+推送”不划算。建议：
  - 简单版：不启用 goal，卡片跑完即成功；可靠性靠 `push.py` 退出码 + `state/runs.jsonl`。
  - 严谨版：启用 `/goal`，但勾“跳过本任务验收”（`skipVerification: true`）；注意跳过验收也同时跳过了“必须调用 complete”的完成门，所以它只节省裁判成本，不提供额外完成保证。
  - **不推荐**：开 goal + 开验收，每天多 6–12 次裁判调用，判据还是 coding 导向。

## 5. 推荐架构

```
每天 08:00（任务看板 cron）
        │
        ▼
DSH 会话加载 academic-digest skill
        │
        ├─ 1. python3 scripts/collect.py --config config.yaml
        │      ├─ PubMed (edat 窗口, 2 天) ──┐
        │      ├─ Europe PMC (FIRST_PDATE, MED+PPR) ──┤
        │      ├─ arXiv RSS (announce_type=new) + API (关键词/回溯 4 天) ──┤ 归一化
        │      ├─ Research Square RSS (含 abstract) ──┤ → DOI/PMID/arXiv
        │      ├─ bioRxiv/medRxiv (可选，按日期全量) ──┤ → 去重 → 规则打分
        │      ├─ 期刊白名单 → PubMed/EPMC 的 JOURNAL 过滤 ──┤
        │      └─ GitHub Search (token, pushed:> + sort=updated) ──┘ → out/candidates.json
        │
        ├─ 2. 模型读 candidates.json（top 10–15），按模板写 out/digest.md
        │      每条：一句话结论 / 方法 / 与你关键词的关系 / 局限
        │      强制：只用摘要；没有摘要写“仅标题”；不编造数字
        │
        ├─ 3. python3 scripts/push.py --digest out/digest.md
        │      ├─ 按通道限长拆分
        │      ├─ 发送 Server酱 / 企微 / PushPlus / WxPusher
        │      └─ 成功才写 pushes + last_success；失败留 pending 重试
        │
        └─ 4. 成功 → update_goal(complete)（若启用 goal）；失败 → 不调用
```

### 目录

```
academic-digest/
├── SKILL.md                 # 触发、配置访谈、每日三步、故障处理
├── scripts/
│   ├── collect.py           # 多源适配器 + 归一化 + 去重 + 打分
│   ├── push.py              # 排版 + 分条 + 通道适配 + 状态
│   ├── doctor.py            # 网络/密钥/通道自检 + 测试推送
│   └── state.py             # SQLite：papers/pushes/runs
├── references/
│   ├── sources.md           # 各源查询配方（来自 01/02）
│   └── digest-template.md   # 日报模板
└── assets/
    └── config.example.yaml
```

运行时文件在仓库根：`config.yaml`、`secrets.env`（600）、`state/`、`out/`。

### 配置样例

```yaml
timezone: Asia/Shanghai
lookback:
  pubmed: 2               # edat 窗口
  europepmc: 2            # 索引延迟 1–2 天，回看 2 天
  arxiv: 4                # 公告按美东 14:00 截断、周末合并
  researchsquare: 3       # RSS 约覆盖近 3 天
language: zh

topics:
  - name: 单细胞与空间组学
    terms: ["single-cell", "scRNA-seq", "spatial transcriptomics", "spatial omics"]
    exclude: ["review"]
    max_items: 5
  - name: 基因编辑
    terms: ["CRISPR", "base editing", "prime editing", "gene editing"]
    max_items: 3

sources:
  pubmed: true
  europepmc: true
  arxiv:
    enabled: true
    rss: true               # 每日新增用 RSS（announce_type=new）
    api: true               # 关键词/历史用 API
    categories: ["q-bio.QM", "q-bio.GN", "cs.LG"]
  researchsquare:
    enabled: true           # RSS 自带 abstract；官方 API 不爬
  biorxiv: false            # EPMC 已覆盖大部分；要完整性再开（约 11 页/天）
  journal_filter: []        # 例如 ["Nature", "Cell", "Science"]；走 PubMed/EPMC 的 JOURNAL 过滤
  journal_rss: []           # 只用于 TOC/新闻，例如 ["Lancet", "Cell"]
  github:
    enabled: true
    # 日期由 collect.py 按 lookback 注入；这里写相对占位
    queries:
      - 'topic:single-cell stars:>50 pushed:>{date}'
      - '"spatial transcriptomics" in:name,description stars:>30 pushed:>{date}'
    min_stars: 30
    max_items: 3
    token_env: GITHUB_TOKEN

summarize:
  papers_max: 8
  repos_max: 3
  detail: brief           # brief | standard | deep
  fulltext: false

push:
  channel: serverchan     # serverchan | wecom_app | pushplus | wxpusher
  serverchan_max_bytes: 30000
  wecom_max_bytes: 3800   # 4096 字节上限留余量
  send_empty: false       # 无新内容时是否发“今日无更新”

schedule:
  cron: "0 8 * * *"
  timezone: Asia/Shanghai
```

### 打分（规则层，够用）

- 标题命中：每个 term +3（全词组命中额外 +2）
- 摘要命中：每个 term +1
- 期刊白名单：+2；预印本：0
- 新鲜度：今天 +2，昨天 +1
- GitHub：`log10(stars)` + 最近 30 天有 push +1 + README 命中 +2
- 负词/排除词：命中直接丢弃
- 每个来源设上限，保证多样性（避免 8 篇全是 PubMed）

> 每天 100–500 篇的量级，**不需要 embedding、不需要向量库**。规则层召回 top 30，模型只读 top 10–15。

### 去重与幂等

- 键优先级：`DOI`（小写归一）> `PMID` > `arXiv ID`（去 vN）> `normTitle+year` 哈希。
- SQLite `pushes(paper_id, topic, channel, digest_date)` 唯一约束；发送前查，发送后写。
- 抓取窗口按源设置（PubMed 2 天、EPMC 2 天、arXiv 4 天、RS 3 天），而不是自然日。
- 失败不推进 `last_success`；`out/pending/` 保留未发送日报，下次优先重试。

## 6. 方案对比

| | A. Skill + 脚本 + 看板（推荐） | B. 纯 Skill（模型自己 curl） | C. 独立 Python 服务 + 系统 cron |
|---|---|---|---|
| 可控性 | 高（脚本确定性） | 低（每天路径不同） | 高 |
| 成本 | 低（只总结 top 10–15） | 高（上下文塞大量摘要） | 低 |
| 维护 | 中（两个脚本） | 低（只有 prompt） | 高（服务/部署/日志） |
| 与看板配合 | 原生 | 原生 | 割裂 |
| 额外 key | 不需要（用会话模型） | 不需要 | 需要 LLM API key |
| 适合 | **本项目** | 极简试用 | 多用户/团队产品 |

## 7. 成本与运行时间

- Server酱：免费 5 条/天；一天 1 条日报 + 重试，够用。
- GitHub token：免费。
- LLM：每天 10–15 条摘要，约 2–4 万 token；参考同类项目约 0.2 元/天。
- 看板验收：跳过，0 额外调用。
- 运行时间：采集 30–90 秒（主要慢在 bioRxiv；默认关掉），总结 1–2 分钟，推送 1 秒。

## 8. 需要你拍板的事

1. **领域与关键词**：给我 3–5 个中文关键词/方向即可，我负责扩展成英文 terms + MeSH + 排除词。是否要期刊白名单（如只看 Nature/Cell/Science 子刊）？
2. **微信通道**：你有没有 Server酱 / 企业微信 / PushPlus / WxPusher 的现成 key？没有的话我建议先花 3 分钟注册 Server酱，跑通再换。
3. **日报体量**：默认 8 篇论文 + 3 个 repo，每条 3–4 句（一句话结论 + 方法 + 相关性）。要更多/更少？要不要“今日必读 + 其他速览”两级？
4. **GitHub 关注模式**：①每天新出现的相关 repo；②最近活跃/涨星快的 repo；③你已 star 的 repo 的新 release。可多选。
5. **推送时间**：默认每天 08:00 Asia/Shanghai；机器关机错过时，下次运行补最近 2–7 天，可以吗？
6. **全文**：默认只读摘要（更快更便宜、幻觉更少）；top 3–5 是否需要拉 OA 全文做方法/局限精读？

## 9. 调研笔记

- [00 综合方案](00-synthesis.md)（本文）
- [01 文献检索 API](01-literature-apis.md)：PubMed/EPMC/OpenAlex/S2/Crossref 的实测配方与坑
- [02 预印本与期刊](02-preprints-journals.md)：arXiv/bioRxiv/Research Square/期刊 RSS 的实测与 4 个抓取配方
- [03 GitHub 与微信](03-github-wechat.md)：Search API 配额/查询配方，5 个推送通道的实测对比
- [04 竞品与摘要方案](04-products-summarization.md)：开源项目架构、排序、幻觉控制、SQLite 设计
- [05 DSH Skill 与任务看板](05-dsh-skill-taskboard.md)：skill 发现规则、cron/验收/权限门
