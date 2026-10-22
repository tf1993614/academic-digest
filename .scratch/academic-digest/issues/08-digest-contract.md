# 08: 日报与 selection 契约：3+7、四要素、digest check

**What to build:** 模型从 30 条候选池选出 3 篇今日必读 + 7 篇其它速览，写成含四要素的中文日报；selection 校验配额与 id；`digest check` 能拒绝结构不合格的日报。

**Blocked by:** 04, 05, 06, 07.

**Status:** ready-for-agent

- [ ] 给定 fixture 候选池，产出 3 篇今日必读 + 7 篇其它速览，每条含标题、标签、摘要、局限性。
- [ ] 今日必读 top 3 含方法精读，或明确“无 OA 全文，仅基于摘要”。
- [ ] selection 校验：id 存在、G2 ≤4、非空组 ≥1；不合格时失败并指出原因。
- [ ] GitHub 区块含 3 种模式；G6 独立区块 1–2 条，不占 3+7。
- [ ] 页脚含各源状态、候选/入选计数；不含密钥。
- [ ] `digest check` 对合格/不合格 fixture 给出正确退出码与错误；测试离线。
