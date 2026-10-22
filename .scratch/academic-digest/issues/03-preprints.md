# 03: 预印本：arXiv RSS + Research Square RSS + 可选 bioRxiv/medRxiv

**What to build:** 日报能纳入当天真正新公告的 arXiv 论文和 Research Square 预印本；bioRxiv/medRxiv 可按配置开启；所有预印本参与去重并打标。

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] arXiv fixture 同时含 `new` 与 `replace` 时，只保留 `new`；lookback 至少 4 天。
- [ ] Research Square RSS 的 `<abstract>`、作者、DOI 进入候选，不调用官方 API。
- [ ] bioRxiv/medRxiv 默认关闭；开启后按日期区间 fixture 产出候选并本地过滤。
- [ ] 预印本带来源与“预印本”标记；与其他源同一 DOI 时只保留一条。
- [ ] 测试覆盖 new/replace、RS 摘要、bioRxiv 开关。
