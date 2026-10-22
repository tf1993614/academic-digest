# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

## 语言

### 日报结构

**日报**：
每天生成一次、通过 Server酱 推送到微信的学术摘要，包含论文与 GitHub 两部分。
_Avoid_: 简报、推送、digest

**今日必读**：
日报中优先级最高的 3 篇论文，附摘要、局限性与可获取全文时的方法精读。
_Avoid_: 重点推荐、头条

**其它速览**：
入选日报但未进入今日必读的论文，保留四要素的压缩版，每条 1–2 句。
_Avoid_: 其他、剩余、备选

**候选池**：
采集、归一化、去重后进入最终筛选的论文集合；不等于当天抓到的全部条目。
_Avoid_: 抓取结果、原始列表

**预印本**：
尚未经同行评审、发布在 arXiv / bioRxiv / medRxiv / Research Square 等平台的论文版本；
日报用 `is_preprint` 与 `预印本` 标签标记，与期刊版本共用 DOI 时合并为一条。
_Avoid_: 草稿、preprint、非正式论文

### 内容判断

**相关性**：
论文或仓库与用户关键词组在字面与语义上的匹配程度；是入选依据，不等同于引用量或期刊影响因子。
_Avoid_: 热度、重要性、影响力

**分组配额**：
每个关键词组在日报中的最低与最高席位数，用来防止宽泛组刷屏。
_Avoid_: 限额、比例

**局限性**：
作者明确声明的限制，加上一条独立的批判性判断；后者必须标注为“模型判断”。
_Avoid_: 缺点、不足、critique

**OA 全文**：
可以合法公开获取的全文，例如 Europe PMC OA、arXiv、bioRxiv、Research Square；订阅全文不算。
_Avoid_: 全文、PDF

### 运行与状态

**补窗**：
定时触发被错过时，下一次运行向前回溯的时间范围；不是重发旧消息。
_Avoid_: 补发、重试

**已推送**：
成功发送并记录、后续不再重复推送的条目；失败与 pending 不算。
_Avoid_: 已发送、已读

### GitHub 发现

**新库**：
最近创建、尚未积累 star 的相关仓库。
_Avoid_: 新项目、new repo

**活跃库**：
最近仍有 push、且 star 达到门槛的相关仓库。
_Avoid_: 热门库、trending

**关注库**：
用户已 star 的仓库，用于跟踪新 release。
_Avoid_: 收藏库、starred

**AI 工具 / Agent Harness**：
日报中独立于论文的区块，跟踪 Claude Code、Codex、DSH 等工具及其生态的 repo 与 release；不占论文席位。
_Avoid_: 工具推荐、AI 新闻

**DSH**：
DeepSeek Harness 的缩写，一个插件化的 AI 编程 / Agent 工具。
_Avoid_: DSH harness、deepseek harness（正文首次出现可写全称）
