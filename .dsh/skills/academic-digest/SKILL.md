---
name: academic-digest
description: 自动学术速递的每日运行与配置：按关键词抓取 PubMed/Europe PMC/arXiv/Research Square/GitHub，写 3+7 中文日报并推送到微信；也用于一次性 setup（写 config、doctor、dry-run、测试推送、创建 08:00 任务卡）与推送失败/pending 排查。
---

# 自动学术速递

## 定位仓库

本 skill 在 `<repo>/.dsh/skills/academic-digest/`。加载时 harness 会给出本 skill 的
base directory；先解析出真实仓库根并进入：

```bash
repo=$(git -C "<本 skill 的 base directory>" rev-parse --show-toplevel) || {
  echo "[fail] cannot locate the git repository from the skill directory" >&2
  exit 1
}
cd "$repo"
test -f scripts/collect.py && test -f academic_digest/cli.py || {
  echo "[fail] $repo is not the academic-digest repository root" >&2
  exit 1
}
```

之后所有命令都以仓库根为工作目录。用户级软链（`~/.dsh/skills/academic-digest`）
指向真实仓库，`git -C` 会跟随软链找到同一个仓库根，所以在任意工作区都能这样定位。

## 每日运行

看板卡每天 08:00 触发的固定三步。完成标准是第 3 步 `push` 退出 0 且 stdout 出现
`[ok] push:`；任何一步失败就停在那里，报告 stderr 的 `[fail]` 行。

每次 bash 调用都是新 shell。需要 GitHub token / SendKey 的命令先显式加载本地
secrets；不要打印值，不要写进回复、日报或 Prompt：

```bash
set -a; . ./secrets.env; set +a
```

### 1. 采集

```bash
set -a; . ./secrets.env; set +a
python3 scripts/collect.py --config config.yaml
```

- 产物固定是 `out/candidates.json`（`paths.candidates` 的默认值）。
- 联网采集通常 1–4 分钟；某个源不可达时会更久。给 bash 调用留足 15 分钟超时；如果
  被 harness 移到后台，用 `job_output(wait: true)` 等它结束，不要重跑。
- 打印 `[ok] <source>: N records` 是成功；某个源 `[fail]` 但退出 0 表示部分源失败，
  日报页脚照实写。退出 1（全部源失败）就停止，不写假日报。
- 部分源失败时**不要为了修源重跑 collect**：失败原因照实写进页脚，继续第 2 步。
  只有全部源失败（退出 1）才需要停下来；也不要为了“跑全”连续重试网络。
- 候选池最多 30 篇论文，另有 `github.new` / `github.active` / `github.g6` /
  `github.releases.starred` / `github.g6_releases`。

### 2. 写日报

读整个 `out/candidates.json`，按 [`references/digest.md`](references/digest.md) 选
3 篇今日必读 + 7 篇其它速览，写出 `out/selection.json` 与 `out/digest.md`。

- 今日必读逐篇跑 `fulltext`（带候选的 DOI / arXiv ID 与 `--title`），把方法、结果、
  局限作为精读与局限性的证据；拿不到 OA 全文就写 `无 OA 全文，仅基于摘要`，不换论文。
- selection 只记录论文；GitHub/G6 由 `candidates.github` 原样写进日报。
- 写完先校验；不合格就按 `[fail]` 修到退出 0，再进入推送：

```bash
python3 scripts/digest.py check \
  --candidates out/candidates.json \
  --selection out/selection.json \
  --digest out/digest.md
```

### 3. 推送

```bash
set -a; . ./secrets.env; set +a
python3 scripts/push.py --config config.yaml \
  --candidates out/candidates.json \
  --selection out/selection.json \
  --digest out/digest.md
```

- 退出 0 且 `[ok] push: sent ...`：当天完成。空日报默认发一条“今日没有匹配的检索条目”。
- 退出 1：把 `[fail]` 行原样报告，不要循环重试；`push` 已把未送达消息写进 SQLite
  `pending`，下次 live run 会先补发。退出 2 表示缺 SendKey 或参数/配置错误，没有发送，
  也没有 `pending`。两种情况都不要手工改状态库。

## 写作规范

只以 [`references/digest.md`](references/digest.md) 为准。硬约束：

- 论文标题逐字照抄候选池，不翻译；同一标题只出现一次。
- 今日必读四要素齐全（标签、摘要、局限性、方法精读）；其它速览一行含摘要、局限、链接。
- 摘要与局限性只写候选摘要或全文里有的内容，不编造数字、样本量、影响因子；模型判断
  要标明。
- 中文为主，模型名、方法名、工具名保留英文。
- 页脚必须覆盖 `candidates.sources` 的每个源、候选数、入选数与 ISO8601 生成时间。

## Setup（一次性）

完整步骤与话术在 [`references/setup.md`](references/setup.md)，顺序固定：

1. secrets：用户本地 `secrets.env` 已有 SendKey 与 GitHub token（`scripts/setup-secrets.sh`
   向导，600 权限、gitignored）。
2. config：复制 `config.example.yaml` 为 `config.yaml`，按访谈调整；`config.yaml` 不提交。
3. doctor：`set -a; . ./secrets.env; set +a; python3 scripts/doctor.py --config config.yaml`。
4. dry-run：用 fixture 日报构建 ServerChan payload，不读 SendKey、不发送。
5. 测试推送：用 fixture 日报真发一条到微信，确认收到。
6. 创建任务卡：cron `0 8 * * *` / `Asia/Shanghai`，工作区为本仓库，权限
   `workspace-write`，`goalRun: true` + `skipVerification: true`（完成门是
   `update_goal(complete)`，不启用验收裁判），Prompt 明确加载本 skill 并走上面三步。

只有第 3–5 步都通过才创建卡片；第 6 步后从看板手动跑一次，确认微信收到真实日报，
再把卡片交给 cron。

## 安全与失败

- `SERVERCHAN_SENDKEY` / `GITHUB_TOKEN` 只从环境变量读；不写进 Prompt、日报、日志、
  git 或状态库。错误信息已经脱敏。
- 部分源失败：继续发，页脚标 `failed`。全部源失败：`collect` 退出 1，不推送。
- `push` 重试后仍失败：不伪造成功，保留 `pending`；下一次运行优先补发。超过
  `push.pending_days` 的 pending 会被丢弃并记进 `runs.error`。
- 不要为了“让卡片成功”而跳过 `digest check` 或改 `pending`。
