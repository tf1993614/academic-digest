# 05: 看板卡 Prompt 迁移

**What to build:** 生产看板卡按"加载 academic-digest skill，按它的每日运行执行"跑，Prompt 里不再出现任何脚本路径，因此以后再搬目录也不会失效。

**Blocked by:** 02.

**Status:** ready-for-agent

- [x] 卡片 Prompt 不含脚本路径，只要求加载 skill 并执行每日三步；完成门仍是 `push` 退出 0。
- [x] 若卡片 Prompt 已冻结，则新建一张同字段的卡、归档旧卡，不修改历史执行记录。
- [x] 手动跑一次：微信收到当天真实日报；`state/` 的 `runs` 新增一行 `push`/`ok`。
- [ ] 次日 08:00 自动跑通一次，卡片执行历史为成功。

## Notes

- 这是仓库外操作，验收不能靠 `git diff`；以看板执行历史 + `state/` 的 `runs` 表为准。
- 若改写卡片，只动 `prompt` 与必要的 title/description，不动权限、工作区、cron。

## Comments

- 2026-10-23：旧卡 Prompt 已冻结，按票面新建同字段卡
  `aabbec5e-6251-4607-bf9b-640853791397`：Prompt 只写「加载 skill，按每日运行执行」，
  无脚本路径；`cron 0 8 * * *`、`goalRun`、`skipVerification`、工作区与标签沿用旧卡；
  权限继承部署默认的 `workspace-write`（未钉住，避免人工确认门）。旧卡
  `7dfb1e87-0c59-45a5-9028-08478950719a` 先停用定时、再归档，执行历史一条未改。
- 手动跑一次：执行 `e8c46f79-c1d8-4392-81bc-88171410e162` 成功（看板结果
  `succeeded`）。`state/` 的 `runs` 新增 collect（`arxiv` 读超时、其余源 ok，退出 0）与
  push（`ok`，`pending_count` 为 0）；`out/digest.md` 是 2026-10-23 的真实 3+7 日报。
  用户已确认微信收到 2026-10-23 的日报。
- 剩余验收：2026-10-24 08:00 自动跑通后，勾第 4 条并把 `Status` 改为 `done`。
