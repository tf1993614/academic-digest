# 07: OA 全文能力：EPMC/arXiv/bioRxiv/RS/Unpaywall + 解析

**What to build:** 给定 DOI 或 arXiv ID，找到可公开获取的全文并抽取方法与局限段落；找不到时返回明确的 no_oa 状态，不阻塞日报。

**Blocked by:** 01.

**Status:** done

- [x] EPMC OA XML fixture 能抽取方法/局限文本并标注来源。
- [x] arXiv ID fixture 能从 HTML/PDF 抽取。
- [x] bioRxiv/Research Square DOI fixture 能从 PDF 抽取。
- [x] Unpaywall fixture 能定位 OA 版本；无 OA 时返回 no_oa，不抛异常。
- [x] 输出含来源、OA 标记、抽取段落与长度；测试覆盖四种来源 + no_oa。

## Comments

- 2026-10-22：已实现 `fulltext` CLI。给定 `--doi` 或 `--arxiv` 时按固定顺序尝试
  Europe PMC `fullTextXML` → arXiv HTML/PDF → bioRxiv/medRxiv/Research Square PDF
  → Unpaywall 最佳 OA 位置；每个来源记一条 `attempts`（同一来源内部的 HTML→PDF
  回退与多条 OA 候选合并为一条），全部失败返回 `status: no_oa` 与可读 `reason`，
  退出码仍为 0，日报可据此标注“仅基于摘要”。配置了
  `fulltext.unpaywall.email` 才尝试 Unpaywall；留空时完全跳过该来源，不记为失败。
  Unpaywall 请求 URL 含邮箱，live 失败信息会脱敏后再写入 `attempts` / `reason`。
  输出含 `source`、`oa`、`format`、`doi`、`arxiv_id`、`url`、`length`、
  `methods`、`results`、`limitations`、`reason`、`attempts`。
  JATS XML 按 `sec-type` / 标题定位；HTML 按标题栈处理嵌套小节；PDF 用 PyMuPDF
  文本层按标题切段，并在 `References` / `Acknowledgements` 处重置。Europe PMC
  搜索请求取 `pageSize: 10`，结果必须 DOI 匹配；wrong-DOI 与缺 DOI 的邻近日录都
  会跳过，避免 fuzzy 查询把
  别人的 PMC id 当成目标论文。方法/结果/局限分别最多 4/3/4 段、4000/3000/2000
  字符，超长在句号处截断；`length` 为保留段落总字符数。没有显式 Limitations 小节
  时只从 Discussion/Conclusion 取作者声明的局限，Methods/Results 的顺带提及不提升
  为局限。新增 fixture：EPMC XML（含 wrong-DOI 与缺 DOI 邻近日录）、arXiv HTML、
  arXiv PDF、bioRxiv PDF、medRxiv PDF、Research Square PDF、Unpaywall 定位 PDF、
  Unpaywall 定位 HTML、Unpaywall 无 OA、段落数截断、字符数截断，以及共享
  `tests/fixtures/fulltext/config.yaml`、无邮箱配置与坏邮箱配置。新增 20 个 CLI
  边界测试，覆盖上述来源与顺序（EPMC 先于 Unpaywall、arXiv 先于预印本 PDF、
  预印本 PDF 先于 Unpaywall）、arXiv 失败后继续预印本 PDF、arXiv HTML→PDF 回退
  只记一条 attempt、段落数 4/3/4 与字符数 4000/3000/2000 的截断、arXiv 版本号
  归一化、fixture 缺失/无邮箱降级为 `no_oa`、缺目标和坏邮箱的退出码、stdout 模式。
  验收：`python3 -m pytest`（79 passed，全部离线）；`mypy` / `pyflakes` 无问题。
  `docs/adr/0001-literature-source-strategy.md` 已追加 Issue 07 amendment。按标题
  匹配预印本版本与 DOI→arXiv 交叉检索不在本 ticket 的 DOI/arXiv 输入范围内，留给
  日报契约阶段；`collect` 不调用 `fulltext`，Issue 08 只对今日必读 top 3 逐篇调用。
