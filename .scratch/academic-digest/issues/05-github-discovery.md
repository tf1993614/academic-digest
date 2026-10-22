# 05: GitHub 发现：22 条查询 + 新库/活跃库 + 本地打分

**What to build:** 从 GitHub 找到相关的新库与活跃库，带上 stars、语言、最近更新、README 摘要与“为什么相关”；每天最多 1 个新库、2 个活跃库。

**Blocked by:** 01, 04.

**Status:** ready-for-agent

- [ ] fixture 搜索结果显示新库（created > 7 天、stars ≥ 5）与活跃库（pushed > 7 天、stars ≥ 30）。
- [ ] 每类数量受 1/2 上限约束；不足时不补。
- [ ] 每个 repo 含 owner/repo、stars、语言、最近更新、定位、相关性理由；README 通过 raw fixture 读取。
- [ ] G6 的 12 条发现查询可用，能产出 Claude Code/Codex/DSH 生态候选。
- [ ] 缺 token 时 CLI 明确报错；搜索请求带 UA 并按限速串行。
- [ ] 测试覆盖上限、查询构造、缺 token。
