# 02: Europe PMC + 跨源/跨天去重

**What to build:** 加入 Europe PMC 后，同一篇论文从 PubMed 和 EPMC 进来只出现一次；已推送过的条目不再进入候选池；单源失败时另一源仍能产出结果。

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] PubMed/EPMC 的同一 DOI 只出现一次，字段按 PubMed 摘要/期刊优先合并。
- [ ] 预印本记录保留 preprint 标记与来源。
- [ ] 用 seeded 状态模拟“已推送”的 ID，该条不出现在候选池。
- [ ] 输出含各源计数与失败源；一个源 fixture 报错时另一源仍产出候选。
- [ ] 测试覆盖重复 DOI、已推送排除、单源失败。
