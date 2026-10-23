# DSH：看板卡定时

DSH 的无人值守入口是任务看板卡：`0 8 * * *` / `Asia/Shanghai` 由看板直接起一个会话，
再按 `SKILL.md` 的“每日运行”执行三步。看板卡钉住本仓库工作区，DSH 就会从
`.dsh/skills/` 发现这份 skill。

## 为什么是看板卡

- DSH 没有供外部调度器调用的 headless CLI；会话本身由看板启动，“谁定时”与“谁跑模型”
  是同一个东西。
- 因此 DSH **不经过 `scripts/run-daily.sh`**：那个 wrapper 只服务 Claude Code 与 Codex 的
  `claude -p` / `codex exec`，负责加载 secrets、加并发锁、写日志、透传退出码。看板卡
  不需要这些——会话里按 Prompt 显式执行 `set -a; . ./secrets.env; set +a`，日志以看板
  执行历史与 `state/` 的 `runs` 表为准。
- 也**不要**为 DSH 再套一层 systemd / launchd / crontab：那三家调度器驱动不了看板卡，
  只会多一个会失败的空壳。systemd、launchd 与 crontab 的片段在 Claude Code 与 Codex 的
  定时文档里。

## 创建任务卡

用任务看板工具创建一张卡（`task_board_create`）。字段固定：

- `title`：`每日学术速递`
- `description`：说明关键词来自 `config.yaml`，结果推送到微信，失败看 `runs`。
- `permission`：`workspace-write`（脚本要写 `out/` 与 `state/`）。
- `workspaceId`：固定为本仓库。若工具支持显式传，填本仓库的 workspace id；若从当前
  会话继承，创建后用 `task_board_get` 核对 `workspaceId` 对应本仓库路径。
- `goalRun`：`true`。完成门是 `push` 成功后调用 `update_goal(action: complete)`；
  发送失败时不调用 complete，看板会把这次执行记为失败。若部署没有打开全局 `/goal`
  开关，这个字段会被忽略，失败改用 `record-external-outcome` 记录（见“失败演练”）。
- `skipVerification`：`true`。不用 coding 验收裁判，每天不产生 6–12 次裁判请求；
  真正的验收是 `push` 退出码和 SQLite `runs`。
- `schedule`：`enabled: true`、`mode: "cron"`、`cron: "0 8 * * *"`、
  `timeZone: "Asia/Shanghai"`。

Prompt 用下面这份，逐字粘贴：

```text
加载 academic-digest skill，按它的“每日运行”执行今天的推送。工作区根目录就是本仓库。需要 token 或 SendKey 的命令前先执行 set -a; . ./secrets.env; set +a，不要打印密钥。

1. 采集：按 skill 的“每日运行 → 1. 采集”运行采集，确认 out/candidates.json 已生成。采集通常 2–4 分钟，网络差时可能更久；给 bash 留 15 分钟超时，被移到后台就用 job_output(wait: true) 等它结束，不要重跑。某个源 [fail] 但 collect 退出 0 时，照实写进页脚，不要为了修源重跑 collect。
2. 写作：按 skill 的 references/digest.md 读 out/candidates.json，对今日必读逐篇运行 fulltext，写出 out/selection.json 与 out/digest.md，再按 skill 的“每日运行 → 2. 写日报”运行 digest check。校验不通过就修到通过，不要推送。
3. 推送：按 skill 的“每日运行 → 3. 推送”运行 push，参数与产物路径都用 skill 里的那套。

只有第 3 步退出码为 0 且 stdout 出现 [ok] push: 时才视为完成。若本次执行有活动 goal（get_goal 返回非空），成功时调用 update_goal(action: complete)；没有 goal 时正常结束。任何一步失败都不要调用 complete；报告失败步骤和 stderr 的 [fail] 行，连续 3 轮仍失败再调用 update_goal(action: blocked) 说明原因。只写 out/ 与 state/ 下的运行时文件，不要改代码、文档、config.yaml、secrets.env 或任务卡。
```

创建后：

- `task_board_get` 检查 `workspaceId`、`permission`、`goalRun`、`skipVerification`、
  `schedule.cron`。
- 若看板提示权限高于部署默认，需要人在看板 UI 里确认一次；否则 cron 不会跑。
- `schedule.cron` 必须是 5 段；`nextRunAt` 应在下一个 08:00。

## 手动跑一次

在卡片详情里手动运行（或 `task_board_run`）。执行会话会加载 skill，依次跑 collect、
写日报、`digest check`、push。验收：

- 微信收到当天真实日报（不是 fixture 的 2026-10-22 测试内容）。
- 看板执行历史显示成功。
- `out/digest.md` 是 3 篇今日必读 + 7 篇其它速览，GitHub 三种模式齐全，G6 是独立
  区块，页脚覆盖所有源。
- `state/academic-digest.sqlite3` 的 `runs` 新增一行 `command='push'`、`status='ok'`。

通过后再让 cron 接手。当天手动跑过也不影响 cron，下一次 08:00 会照常触发。

## 失败演练（可选，消耗 0 次成功额度）

目的：确认发送失败会留下 pending，下一次优先补发，并且看板能把这次执行记为失败。
不要改每日生产卡的 Prompt 或 `secrets.env`，临时建两张演练卡：

1. **失败卡**：`task_board_create`，工作区同生产卡、权限 `workspace-write`、
   `goalRun: true`、`skipVerification: true`，标签加“演练”。Prompt 只跑：
   ```bash
   skill="$(git rev-parse --show-toplevel)/skills/academic-digest"
   set -a; . ./secrets.env; set +a
   SERVERCHAN_SENDKEY=INVALID_KEY_FOR_DRILL python3 "$skill/scripts/push.py" \
     --config tests/fixtures/walking/config.yaml \
     --candidates tests/fixtures/digest/valid/candidates.json \
     --selection tests/fixtures/digest/valid/selection.json \
     --digest tests/fixtures/digest/valid/digest.md \
     --state-db out/.board-drill.sqlite3
   ```
   并写明“预期失败，不要调用 `update_goal(complete)`”。状态库放在工作区内，保证
   跨会话可见（`out/` 已 gitignored）。
2. 运行失败卡。`push` 重试后退出 1，把未送达消息写进 `out/.board-drill.sqlite3` 的
   `pending`，`runs.status='failed'`。若 Host 打开了全局 `/goal`，没调用 complete
   会让卡片自动失败；若没打开（本机当前如此），普通单回合按回合结果结算，用
   `task_board_manage(action: "record-external-outcome", result: "failed",
   initiatedBy: "academic-digest-setup", summary: "send-failure drill")` 记录失败。
3. **补发卡**：同样建一张临时卡，Prompt 只跑同一条命令但**不覆盖** SendKey
   （`set -a; . ./secrets.env; set +a` 后用 `secrets.env` 里的真实 key），仍用
   `out/.board-drill.sqlite3`。`push` 先按 `part` 顺序补发 pending，再发当天 fixture；
   stdout 的发送条数应包含补发的那条，`pending` 归零，卡片 succeeded。
4. 演练结束后归档两张演练卡，删除 `out/.board-drill.sqlite3`；确认 `secrets.env`
   未改动、权限仍是 600，并且没有把无效 key 留在任何文件或看板 Prompt 里。

## 运行约束

- **时区**：看板卡的 `schedule.timeZone` 固定写 `Asia/Shanghai`；cron 表达式由看板按这个
  时区解释，与宿主机时区无关，也没有 crontab 那套 `CRON_TZ` 变量（那个变量只对 cronie
  有效）。
- **错过不补跑**：宿主机停机或看板当时不可用时，错过的 08:00 **不会**在恢复后补跑；
  下一次 08:00 正常触发。真正的兜底是采集的 `lookback`（arXiv 默认 4 天，覆盖周末），
  不是补发旧消息。
- **会话必须在仓库工作区启动**：`config.yaml`、`secrets.env`、`out/`、`state/` 都在仓库
  根；卡片工作区钉错，三步会找不到配置或把状态写到别处。
- **Host 必须可写工作区**：`workspace-write` 权限是脚本写 `out/` 与 `state/` 的前提；
  若看板提示权限高于部署默认，需要人在看板 UI 里确认一次，否则定时不会跑。

## 用户级安装（可选）

项目级 skill 只在本仓库工作区可见。要在任意工作区使用：

```bash
mkdir -p "$HOME/.dsh/skills"
ln -sfn "$(git rev-parse --show-toplevel)/.dsh/skills/academic-digest" \
  "$HOME/.dsh/skills/academic-digest"
readlink -f "$HOME/.dsh/skills/academic-digest"
```

软链指向真实仓库，skill 里的 `git -C` 会跟随软链找到同一个仓库根，因此在其他项目里
也能运行同一个 skill 与同一份配置。

不要手改 `.dsh/skills/academic-digest/`；改源目录 `skills/academic-digest/` 后跑
`scripts/sync-skills.sh` 重新生成三份副本。
