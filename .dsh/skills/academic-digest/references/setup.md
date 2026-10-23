# 一次性 Setup

目标：让研究者的机器具备“每天 08:00 从看板跑一次、微信收到真实日报”的条件。只有在
`doctor`、`dry-run`、真实测试推送都通过之后，才创建定时卡片。

全程不打印 `SERVERCHAN_SENDKEY` / `GITHUB_TOKEN`；不要把它们写进 Prompt、日报、
README、ticket 或对话。

## 0. 先确认仓库

按 SKILL.md 的“定位仓库”得到 `repo` 并 `cd` 进去。确认：

```bash
test -f config.example.yaml && test -f scripts/setup-secrets.sh
test -f secrets.env && stat -c %a secrets.env
git check-ignore -q config.yaml && git check-ignore -q secrets.env
```

期望 `secrets.env` 权限是 `600`，`config.yaml` 与 `secrets.env` 都被 git 忽略。缺失
secrets 时让用户自己跑向导（会打开浏览器，属于只有人能做的一步）：

```bash
scripts/setup-secrets.sh
```

## 1. 访谈并写 config.yaml

先复制模板，再按用户回答改，不要改 `config.example.yaml` 本身。已有 `config.yaml`
时不要覆盖：

```bash
test -f config.yaml || cp config.example.yaml config.yaml
```

访谈项与默认值：

| 项 | 默认 | 说明 |
|---|---|---|
| 时区 | `Asia/Shanghai` | IANA 名称 |
| 关键词组 | G1–G6 | 老化×多组学、单细胞/空间、基础模型/表征、扰动/调控、LLM/图/多模态、AI 工具/Agent Harness |
| 每组配额 | G2 ≤ 4，其它 6 | `topics[].max_items`，候选池席位上限 |
| 文献源 | PubMed、Europe PMC、arXiv、Research Square 开；bioRxiv/medRxiv 关 | 全量预印本源按需再开 |
| GitHub | 开，`user: tf1993614` | 需要 token；官方库是 Claude Code / Codex / DSH |
| GitHub 阈值 | 新库 7 天/5 星/1 条；活跃库 7 天/30 星/2 条；G6 2 条 | 见 `github.*` |
| OA 全文 | Unpaywall 邮箱可空 | 留空则少一条 OA 路径，不影响运行 |
| 推送 | Server酱，`send_empty: true`，标题 ≤32 字 | `push.*` 全部可省略 |
| 定时 | 每天 `0 8 * * *`，`Asia/Shanghai` | 建卡时用 |

写完后先只做配置校验（不发请求、不建状态库）：

```bash
python3 - <<'PY'
from academic_digest.config import load_config
c = load_config("config.yaml")
print("config ok:", ", ".join(t.name for t in c.topics), "| sources:", ", ".join(n for n, on in c.sources.items() if on))
PY
```

`topics` 必须包含用户在用的六组；启用 `sources.github` 时环境里必须有
`GITHUB_TOKEN`，否则这一步会明确报 `github.token`。

## 2. doctor（联网）

```bash
set -a; . ./secrets.env; set +a
python3 scripts/doctor.py --config config.yaml
```

期望最后一行 `doctor: all checks passed`，并列出每个源的连通性、GitHub search 配额、
状态库与候选池路径可写。任何 `[fail]` 都先修，不要继续。

## 3. dry-run（离线，不发送）

用录制好的合格日报构造 payload，验证标题、Markdown 和拆分。`--dry-run` 不读 SendKey、
不打开状态库、不联网；但仍要先加载 secrets，因为 `config.yaml` 启用了 GitHub，配置
校验会检查 `GITHUB_TOKEN` 是否存在：

```bash
set -a; . ./secrets.env; set +a
rm -f /tmp/academic-digest-payload.json
python3 scripts/push.py \
  --config config.yaml \
  --candidates tests/fixtures/digest/valid/candidates.json \
  --selection tests/fixtures/digest/valid/selection.json \
  --digest tests/fixtures/digest/valid/digest.md \
  --now 2026-10-22T08:00:00+08:00 \
  --dry-run --out /tmp/academic-digest-payload.json

python3 - <<'PY'
import json
p = json.load(open("/tmp/academic-digest-payload.json"))
print("messages:", len(p["messages"]))
for m in p["messages"]:
    print(m["part"], m["parts"], len(m["title"]), m["title"])
PY
```

期望标题是 `学术速递 · 2026-10-22`（或带 `（1/2）`），`messages` 非空。payload 里
不应出现 SendKey。

## 4. 真实测试推送（消耗 1 次额度）

同一个 fixture 日报，经 Server酱 真发一条到微信。状态写 `/tmp`，不污染正式状态库：

```bash
set -a; . ./secrets.env; set +a
rm -f /tmp/academic-digest-setup-test.sqlite3
python3 scripts/push.py \
  --config tests/fixtures/walking/config.yaml \
  --candidates tests/fixtures/digest/valid/candidates.json \
  --selection tests/fixtures/digest/valid/selection.json \
  --digest tests/fixtures/digest/valid/digest.md \
  --state-db /tmp/academic-digest-setup-test.sqlite3
```

期望 stdout 是 `[ok] push: sent 1 message(s), recorded N paper(s)`。请用户在微信确认
收到 `学术速递 · 2026-10-22`。失败按 stderr 的 `[fail]` 修，不要重试到刷屏。

## 5. 创建任务卡

用任务看板工具创建一张卡（`task_board_create`）。字段固定：

- `title`：`每日学术速递`
- `description`：说明关键词来自 `config.yaml`，结果推送到微信，失败看 `runs`。
- `permission`：`workspace-write`（脚本要写 `out/` 与 `state/`）。
- `workspaceId`：省略即继承当前会话的工作区；创建后用 `task_board_get` 确认是本仓库。
- `goalRun`：`true`。完成门是 `push` 成功后调用 `update_goal(action: complete)`；
  发送失败时不调用 complete，看板会把这次执行记为失败。若部署没有打开全局 `/goal`
  开关，这个字段会被忽略，失败改用 `record-external-outcome` 记录（见第 7 步）。
- `skipVerification`：`true`。不用 coding 验收裁判，每天不产生 6–12 次裁判请求；
  真正的验收是 `push` 退出码和 SQLite `runs`。
- `schedule`：`enabled: true`、`mode: "cron"`、`cron: "0 8 * * *"`、
  `timeZone: "Asia/Shanghai"`。

Prompt 用下面这份，逐字粘贴：

```text
加载 academic-digest skill，按它的“每日运行”执行今天的推送。工作区根目录就是本仓库。需要 token 或 SendKey 的命令前先执行 set -a; . ./secrets.env; set +a，不要打印密钥。

1. 采集：运行 python3 scripts/collect.py --config config.yaml，确认 out/candidates.json 已生成。采集可能超过 10 分钟并被移到后台；用 job_output(wait: true) 等它结束，不要重跑。某个源 [fail] 但 collect 退出 0 时，照实写进页脚，不要为了修源重跑 collect。
2. 写作：按 skill 的 references/digest.md 读 out/candidates.json，对今日必读逐篇运行 fulltext，写出 out/selection.json 与 out/digest.md，再运行 python3 scripts/digest.py check --candidates out/candidates.json --selection out/selection.json --digest out/digest.md。校验不通过就修到通过，不要推送。
3. 推送：运行 python3 scripts/push.py --config config.yaml --candidates out/candidates.json --selection out/selection.json --digest out/digest.md。

只有第 3 步退出码为 0 且 stdout 出现 [ok] push: 时才视为完成。若本次执行有活动 goal（get_goal 返回非空），成功时调用 update_goal(action: complete)；没有 goal 时正常结束。任何一步失败都不要调用 complete；报告失败步骤和 stderr 的 [fail] 行，连续 3 轮仍失败再调用 update_goal(action: blocked) 说明原因。只写 out/ 与 state/ 下的运行时文件，不要改代码、文档、config.yaml、secrets.env 或任务卡。
```

创建后：

- `task_board_get` 检查 `workspaceId`、`permission`、`goalRun`、`skipVerification`、
  `schedule.cron`。
- 若看板提示权限高于部署默认，需要人在看板 UI 里确认一次；否则 cron 不会跑。
- `schedule.cron` 必须是 5 段；`nextRunAt` 应在下一个 08:00。

## 6. 手动跑一次

在卡片详情里手动运行（或 `task_board_run`）。执行会话会加载 skill，依次跑 collect、
写日报、`digest check`、push。验收：

- 微信收到当天真实日报（不是 fixture 的 2026-10-22 测试内容）。
- 看板执行历史显示成功。
- `out/digest.md` 是 3 篇今日必读 + 7 篇其它速览，GitHub 三种模式齐全，G6 是独立
  区块，页脚覆盖所有源。
- `state/academic-digest.sqlite3` 的 `runs` 新增一行 `command='push'`、`status='ok'`。

通过后再让 cron 接手。当天手动跑过也不影响 cron，下一次 08:00 会照常触发。

## 7. 失败演练（可选，消耗 0 次成功额度）

目的：确认发送失败会留下 pending，下一次优先补发，并且看板能把这次执行记为失败。

1. 先备份 `secrets.env`，临时把 SendKey 换成一个无效值（不要打印，也不要提交）。
2. 从看板跑一次那张卡。`push` 会重试后退出 1，把未送达消息写进 `pending`，
   `runs.status='failed'`；因为卡片启用了 `/goal` 且这一轮没有调用
   `update_goal(complete)`，看板执行记录会显示失败。
3. 如果部署没有打开全局 `/goal`，普通单回合不会因为 shell 退出码自动判负；用
   `task_board_manage(action: "record-external-outcome", result: "failed",
   initiatedBy: "academic-digest-setup", summary: "send-failure drill")` 把这次
   演练记成失败，或在 UI 里移到失败列。
4. 恢复正确 SendKey，再跑一次。`push` 先按 `part` 顺序补发 pending，再发当天日报；
   stdout 的发送条数应包含补发的那条，`pending` 归零，`runs.status='ok'`。
5. 演练结束后确认 `secrets.env` 已恢复、权限仍是 600，并且没有把无效 key 留在
   任何文件或看板 Prompt 里。

## 8. 用户级软链（可选）

项目级 skill 只在本仓库工作区可见。要在任意工作区使用：

```bash
ln -sfn "$(git rev-parse --show-toplevel)/.dsh/skills/academic-digest" \
  "$HOME/.dsh/skills/academic-digest"
readlink -f "$HOME/.dsh/skills/academic-digest"
```

软链指向真实仓库，skill 里的 `git -C` 会跟随软链找到同一个仓库根，因此在其他项目里
也能运行同一个 skill 与同一份配置。

## 常见失败

- `github.token`：环境里没有 token。先 `set -a; . ./secrets.env; set +a`。
- `doctor` 某个源失败：网络/限速。隔几分钟重跑；不要改代码绕过。
- `push` 退出 2：缺 SendKey 或参数错误，先修环境，没发送任何东西。
- `push` 退出 1 且写了 pending：不要手工删；恢复通道后下一次运行会补发。
- 权限确认门：卡片权限高于部署默认时，定时不会跑；让人在看板 UI 确认卡片。
- 看板没触发：Host 必须在线；错过的 cron 不补跑，采集的 lookback 会覆盖最近几天。
