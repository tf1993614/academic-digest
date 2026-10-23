# 03: 无人值守 wrapper 与 client 定时文档

**What to build:** 用户照自己客户端那份 `references/scheduling.md` 粘贴一段 systemd / launchd / crontab，每天 08:00 就能收到日报；不需要读另外两家、也不需要自己写 secrets 加载与日志重定向。

**Blocked by:** 02.

**Status:** done

- [x] skill 内提供 `run-daily.sh <claude|codex>`：加载 `secrets.env`、加并发锁、写日志、透传退出码；参数不是 `claude`/`codex` 时退出 2。
- [x] 三份 `references/scheduling.md` 各自给出"该客户端 + 三种调度器"的可粘贴片段；DSH 那份写看板卡，不经过 wrapper；三份都不出现云端定时方案。
- [x] 测试：`PATH` 里放 stub `claude` / `codex`，断言 wrapper 传给它的参数形态与退出码透传；非法参数走退出 2。
- [x] 文档写明三条运行约束：时区与"错过不补跑"；crontab 的 `CRON_TZ` 只对 cronie 有效；Codex 需打开沙箱网络、Claude 不要加 `--bare`。

## Notes

- wrapper 是三客户端共用的唯一 shell 逻辑，调度片段里不要重复实现 secrets 加载与日志。
- 时区与补跑行为的依据见 `docs/research/06-distribution-and-scheduling.md` §2.3–2.5。

## Comments

- 2026-10-23：无人值守 wrapper 放在 skill 里、随副本分发；仓库根没有第二个入口。参数只接受
  `claude|codex`，其它（含无参数、多个参数）只打印 usage 到 stderr 并退出 2，不启动客户端。
  它按 SKILL.md 同一套规则解析仓库根并 `cd` 进去，加载 `secrets.env`（文件缺失只告警，靠
  继承的环境），用 `state/run-daily.lock` 加锁：`mkdir` + wrapper 与 client 两个 PID 及各自
  start time；空 PID 有一次短宽限，活着的持有者让重叠运行跳过并退出 0，PID 已死或已被复用
  的锁在下一次回收。整次运行追加到 `out/logs/run-daily.log`，另打一行摘要到 stdout，退出码
  原样透传（被信号杀掉就是 128+N）。
- 三份调度文档：Claude Code 与 Codex 各给 systemd unit+timer、launchd plist、crontab 三段
  可粘贴片段，片段里只有一条 wrapper 调用，没有 `cd`、secrets 加载、`flock` 或 `>>`。DSH 那份
  写明看板卡是唯一入口、不经过 wrapper，也不该再套宿主机的三种调度器；创建接口的
  `schedule` 没有时区字段，建卡后用 `task_board_schedule` 设 `Asia/Shanghai`。三份都写清
  “错过不补跑”（launchd 唤醒后合并补一次如实写出）与 `CRON_TZ` 只在 cronie 上有效；Codex
  沙箱网络、Claude 不要 `--bare` 写在各自主文档；三份都不出现云端定时。
- 测试：PATH 上放 stub `claude` / `codex`，并且两种 skill 布局都跑——副本在 git 仓库内时
  解析该仓库，副本在仓库外时回退到启动目录所在的仓库。断言 argv 形态、secrets、退出码
  透传、缺 `secrets.env` 仍运行、非法参数退出 2；锁用锁文件直接构造“活锁 / 客户端仍活 /
  两个 PID 都已死”三种情形，不 sleep、不依赖并发时序。调度文档的三种片段、wrapper argv
  片段、片段不重复 secrets 与日志、不出现云端方案，以及提交副本里 wrapper 的 100755
  git mode，都由副本测试钉住。
- README 与 SKILL.md 的定时入口、CODING_STANDARDS 的 wrapper 契约同步更新；日志落在
  `out/` 下（已 gitignore）。
