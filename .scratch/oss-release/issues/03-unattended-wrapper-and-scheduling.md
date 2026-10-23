# 03: 无人值守 wrapper 与 client 定时文档

**What to build:** 用户照自己客户端那份 `references/scheduling.md` 粘贴一段 systemd / launchd / crontab，每天 08:00 就能收到日报；不需要读另外两家、也不需要自己写 secrets 加载与日志重定向。

**Blocked by:** 02.

**Status:** ready-for-agent

- [ ] skill 内提供 `run-daily.sh <claude|codex>`：加载 `secrets.env`、加并发锁、写日志、透传退出码；参数不是 `claude`/`codex` 时退出 2。
- [ ] 三份 `references/scheduling.md` 各自给出"该客户端 + 三种调度器"的可粘贴片段；DSH 那份写看板卡，不经过 wrapper；三份都不出现云端定时方案。
- [ ] 测试：`PATH` 里放 stub `claude` / `codex`，断言 wrapper 传给它的参数形态与退出码透传；非法参数走退出 2。
- [ ] 文档写明三条运行约束：时区与"错过不补跑"；crontab 的 `CRON_TZ` 只对 cronie 有效；Codex 需打开沙箱网络、Claude 不要加 `--bare`。

## Notes

- wrapper 是三客户端共用的唯一 shell 逻辑，调度片段里不要重复实现 secrets 加载与日志。
- 时区与补跑行为的依据见 `docs/research/06-distribution-and-scheduling.md` §2.3–2.5。
