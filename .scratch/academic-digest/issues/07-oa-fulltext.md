# 07: OA 全文能力：EPMC/arXiv/bioRxiv/RS/Unpaywall + 解析

**What to build:** 给定 DOI 或 arXiv ID，找到可公开获取的全文并抽取方法与局限段落；找不到时返回明确的 no_oa 状态，不阻塞日报。

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] EPMC OA XML fixture 能抽取方法/局限文本并标注来源。
- [ ] arXiv ID fixture 能从 HTML/PDF 抽取。
- [ ] bioRxiv/Research Square DOI fixture 能从 PDF 抽取。
- [ ] Unpaywall fixture 能定位 OA 版本；无 OA 时返回 no_oa，不抛异常。
- [ ] 输出含来源、OA 标记、抽取段落与长度；测试覆盖四种来源 + no_oa。
