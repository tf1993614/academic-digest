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

- 2026-10-23：wrapper 落在 `skills/academic-digest/scripts/run-daily.sh`，随 skill 分发；
  仓库根不再有第二个入口，`check-docs.py` 断言它在 skill 内且可执行。参数只接受
  `claude|codex`，其它（含无参数、多个参数）打印 usage 到 stderr 并退出 2，不启动客户端。
  它按 SKILL.md 同一套规则解析仓库根并 `cd` 进去，加载仓库根的 `secrets.env`（文件缺失时
  只告警，靠调度器继承的环境），用 `state/run-daily.lock` 加锁——`mkdir` + PID，macOS 不需
  `flock`；上一次还活着就跳过并退出 0，PID 已死的锁在下一次运行时回收，避免强杀一次后
  永远不再跑。整次运行追加到 `out/logs/run-daily.log`（首行同时打到 stdout，给
  `journalctl`/launchd 看），退出码原样透传。
- 三份调度文档：Claude Code 与 Codex 各给 systemd、launchd、crontab 三段可粘贴片段，
  片段里只有一条 wrapper 调用，没有 `cd`、secrets 加载、`flock` 或 `>>`。DSH 那份写明看板卡
  是唯一入口、不经过 wrapper，也不该再套宿主机的三种调度器。三份都写清 `Asia/Shanghai` 与
  “错过不补跑”（launchd 唤醒后合并补一次如实写出），`CRON_TZ` 只在 cronie 上有效、Codex
  需要沙箱网络、Claude 不要 `--bare`；三份都不出现云端定时。
- 测试：`tests/test_run_daily.py` 把生成的副本放在仓库外、用 PATH 上的 stub `claude` /
  `codex` 断言 argv 形态、仓库根与 secrets、退出码透传、缺 `secrets.env` 仍运行、非法参数
  退出 2、活锁跳过与死锁回收；`tests/test_skill_copies.py` 断言两份 CLI 文档各有三种调度器
  片段且都走 wrapper、三份都不提云端，并检查提交副本里的 wrapper 保持可执行。
  `check-docs.py` 机械检查 wrapper 的位置与可执行位。
- README、`SKILL.md` 的定时入口、`CODING_STANDARDS.md` 的 wrapper 契约同步更新；日志目录
  `out/logs/` 属于 `out/`，已在 `.gitignore` 内。
