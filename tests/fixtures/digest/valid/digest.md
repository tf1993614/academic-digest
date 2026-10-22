# 学术速递 · 2026-10-22
> 关键词：老化、多组学、单细胞 ｜ 新论文 12 篇，精选 10 篇 ｜ GitHub 5 个

## 今日必读
### 1. Aging multi-omics atlas of the mouse brain
- 标签：`aging` `multi-omics`
- 摘要：研究整合了衰老小鼠脑组织的转录组与蛋白组数据。作者比较了不同年龄层的细胞组成差异。结果显示老化伴随特定胶质细胞比例上升。
- 局限性：样本仅来自小鼠，跨物种外推有限；作者也承认测序深度不一致。
- 方法精读：作者先用单细胞多组学建库，再按年龄分层做差异分析，并用独立队列验证关键细胞类型。方法部分交代了批次校正与质控阈值。
- [原文](https://europepmc.org/article/MED/digest-g1-1) · [PDF](https://example.org/oa/digest-g1-1.pdf)

### 2. Single-cell foundation model benchmark
- 标签：`single-cell foundation model` `benchmark`
- 摘要：作者在统一数据划分下比较了多个单细胞基础模型。评测覆盖细胞类型注释与扰动预测两类任务。结果显示不同模型的优势任务差异明显。
- 局限性：只覆盖公开数据集，未见作者讨论私有数据上的泛化性。
- 方法精读：所有模型使用同一套基因过滤与归一化流程，并按任务分别训练轻量探针。评测同时报告了随机种子方差，方法可复现。
- [原文](https://europepmc.org/article/MED/digest-g3-1) · [PDF](https://example.org/oa/digest-g3-1.pdf)

### 3. Large language model agents for pathway reasoning
- 标签：`large language model` `pathway`
- 摘要：作者把通路推理拆成检索、证据汇总与结论生成三步代理流程。案例显示代理能给出可追溯的证据链。
- 局限性：作者声明只做了小规模专家评审，尚无基准数据集的量化结果。
- 方法精读：无 OA 全文，仅基于摘要
- [原文](https://europepmc.org/article/MED/digest-g5-1)

## 其它速览
- **Plasma proteomics of aging cohorts** — `aging` `proteomics` · 摘要：队列蛋白组随年龄变化。 · 局限性：缺少干预验证。 · [链接](https://europepmc.org/article/MED/digest-g1-2)
- **Spatial transcriptomics of the aging cortex** — `spatial transcriptomics` · 摘要：衰老皮层空间图谱。 · 局限性：样本量偏小。 · [链接](https://europepmc.org/article/MED/digest-g2-1)
- **Spatial cell-type mapping in the aged hippocampus** — `spatial transcriptomics` `cell type annotation` · 摘要：海马体细胞类型空间分布。 · 局限性：仅一个时间点。 · [链接](https://europepmc.org/article/MED/digest-g2-2)
- **Batch effect correction for spatial omics** — `batch effect correction` · 摘要：空间组学批次校正方法。 · 局限性：未覆盖多平台数据。 · [链接](https://europepmc.org/article/MED/digest-g2-3)
- **Cell-cell communication in aged brain niches** — `cell-cell communication` · 摘要：老化脑内细胞通讯变化。 · 局限性：配体受体库不完整。 · [链接](https://europepmc.org/article/MED/digest-g2-4)
- **Perturbation prediction with graph priors** — `perturbation prediction` · 摘要：图先验提升扰动预测。 · 局限性：只在单一细胞系验证。 · [链接](https://europepmc.org/article/MED/digest-g4-1)
- **Claude Code agent harness evaluation** — `claude code` `agent harness` · 摘要：对比多种 agent harness 的任务完成率。 · 局限性：任务集规模有限。 · [链接](https://europepmc.org/article/MED/digest-g6-1)

## GitHub
### 新项目
- **acme/cell-atlas** ⭐ 42 · Python · 2026-10-21 · Single-cell atlas toolkit · 与 G2 单细胞图谱工具相关 · [链接](https://github.com/acme/cell-atlas)
### 活跃项目
- **acme/scanpy-plus** ⭐ 900 · Python · 2026-10-21 · Single-cell analysis toolkit · 活跃维护的单细胞分析工具 · [链接](https://github.com/acme/scanpy-plus)
- **acme/spatial-hub** ⭐ 300 · Python · 2026-10-20 · Spatial transcriptomics hub · 空间转录组数据入口 · [链接](https://github.com/acme/spatial-hub)
### 关注项目的新 release
- **acme/aging-atlas v0.3.0** · 2026-10-22 · 细胞类型注释更快，修复批次效应边 · [链接](https://github.com/acme/aging-atlas/releases/tag/v0.3.0)

## AI 工具 / Agent Harness
- **anthropics/claude-code v2.0.0**（官方 release，2026-10-21）· 新增 /compact 与更快启动 · [链接](https://github.com/anthropics/claude-code/releases/tag/v2.0.0)
- **deepseek-ai/deepseek-harness v1.2.0**（官方 release，2026-10-19）· 插件热重载 · [链接](https://github.com/deepseek-ai/deepseek-harness/releases/tag/v1.2.0)
- **acme/claude-runner** ⭐ 900 · TypeScript · 2026-10-22 · Claude Code plugin runner · 与 G6 生态相关 · [链接](https://github.com/acme/claude-runner)
- **acme/codex-tool** ⭐ 500 · Go · 2026-10-21 · OpenAI Codex CLI wrapper · 与 Codex 生态相关 · [链接](https://github.com/acme/codex-tool)

---
来源：pubmed ok (2) ｜ europepmc ok (9) ｜ github ok (5)
候选：12 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00
