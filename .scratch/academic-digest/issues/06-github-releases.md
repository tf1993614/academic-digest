# 06: GitHub release：8 个关注库 + 3 个 G6 官方库

**What to build:** 跟踪用户已 star 的 8 个 repo 与 Claude Code/Codex/DSH 三个官方库的新 release；每天最多 2 条，没有更新就不出现空区块。

**Blocked by:** 05.

**Status:** ready-for-agent

- [ ] fixture starred 列表（8 个）与 7 天内 release 产出最多 2 条关注库 release。
- [ ] 三个官方库在窗口内有 release 时进入 G6 数据；无更新时不生成条目。
- [ ] 每条含 repo、tag、日期、更新要点、链接。
- [ ] 多个 release 时按时间/相关性取前 2；不重复。
- [ ] 测试覆盖无更新、多更新、官方库更新。
