# 05: 看板卡 Prompt 迁移

**What to build:** 生产看板卡按"加载 academic-digest skill，按它的每日运行执行"跑，Prompt 里不再出现任何脚本路径，因此以后再搬目录也不会失效。

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] 卡片 Prompt 不含脚本路径，只要求加载 skill 并执行每日三步；完成门仍是 `push` 退出 0。
- [ ] 若卡片 Prompt 已冻结，则新建一张同字段的卡、归档旧卡，不修改历史执行记录。
- [ ] 手动跑一次：微信收到当天真实日报；`state/` 的 `runs` 新增一行 `push`/`ok`。
- [ ] 次日 08:00 自动跑通一次，卡片执行历史为成功。

## Notes

- 这是仓库外操作，验收不能靠 `git diff`；以看板执行历史 + `state/` 的 `runs` 表为准。
- 若改写卡片，只动 `prompt` 与必要的 title/description，不动权限、工作区、cron。
