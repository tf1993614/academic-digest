# 一次性 Setup

目标：让研究者的机器具备“按自己的调度每天跑一次、微信收到真实日报”的条件。只有在
`doctor`、`dry-run`、真实测试推送都通过之后，才接入定时。

全程不打印 `SERVERCHAN_SENDKEY` / `GITHUB_TOKEN`；不要把它们写进 Prompt、日报、
README、ticket 或对话。

## 0. 先确认仓库

按 SKILL.md 的“定位仓库”得到 `repo` 并 `cd` 进去。确认：

```bash
test -f config.example.yaml && test -f "<skill>/scripts/setup-secrets.sh"
test -f secrets.env && stat -c %a secrets.env
git check-ignore -q config.yaml && git check-ignore -q secrets.env
```

期望 `secrets.env` 权限是 `600`，`config.yaml` 与 `secrets.env` 都被 git 忽略。缺失
secrets 时让用户自己跑向导（会打开浏览器，属于只有人能做的一步）：

```bash
"<skill>/scripts/setup-secrets.sh"
```

## 1. 访谈并写 config.yaml

先复制模板，再按用户回答改，不要改 `config.example.yaml` 本身。已有 `config.yaml`
时不要覆盖：

```bash
test -f config.yaml || cp config.example.yaml config.yaml
```

逐项问用户，并把回答写进 `config.yaml`：时区；保留/删减哪些关键词组；每组配额；
期刊白名单；启用哪些文献源与 GitHub；GitHub 用户名与关注库；Unpaywall 邮箱；推送
通道（V1 只有 Server酱，没有其它选项）；定时时间。用户不改就按下面的默认值。白名单
默认留空，**不要替用户猜名单**；只有用户明确给出期刊全名时才写入 `journal_filter`。
访谈项与默认值：

| 项 | 默认 | 说明 |
|---|---|---|
| 时区 | `Asia/Shanghai` | IANA 名称 |
| 关键词组 | G1–G6 | 老化×多组学、单细胞/空间、基础模型/表征、扰动/调控、LLM/图/多模态、AI 工具/Agent Harness |
| 每组配额 | G2 ≤ 4，G6 2，其它 6 | `topics[].max_items`，候选池席位上限 |
| 期刊白名单 | `[]`（不限期刊） | `journal_filter`，完整期刊名；PubMed/Europe PMC 用 `JOURNAL` 过滤，命中候选排序 +2；可参考 [Nature Index 期刊列表](https://www.nature.com/nature-index/faq) |
| 文献源 | PubMed、Europe PMC、arXiv、Research Square 开；bioRxiv/medRxiv 关 | 全量预印本源按需再开 |
| GitHub | 开，`user: tf1993614` | 需要 token；官方库是 Claude Code / Codex / DSH |
| GitHub 阈值 | 新库 7 天/5 星/1 条；活跃库 7 天/30 星/2 条；G6 2 条 | 见 `github.*` |
| OA 全文 | Unpaywall 邮箱可空 | 留空则少一条 OA 路径，不影响运行 |
| 推送 | Server酱，`send_empty: true`，标题 ≤32 字 | `push.*` 全部可省略 |
| 定时 | 每天 `0 8 * * *`，`Asia/Shanghai` | 按客户端的 scheduling 文档接入 |

写完后先只做配置校验（不发请求、不建状态库）。`config.yaml` 默认启用 GitHub，
配置校验会检查 `GITHUB_TOKEN` 是否存在，所以先加载 secrets：

```bash
set -a; . ./secrets.env; set +a
python3 - "<skill>" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
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
python3 "<skill>/scripts/doctor.py" --config config.yaml
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
python3 "<skill>/scripts/push.py" \
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
python3 "<skill>/scripts/push.py" \
  --config tests/fixtures/walking/config.yaml \
  --candidates tests/fixtures/digest/valid/candidates.json \
  --selection tests/fixtures/digest/valid/selection.json \
  --digest tests/fixtures/digest/valid/digest.md \
  --state-db /tmp/academic-digest-setup-test.sqlite3
```

期望 stdout 是 `[ok] push: sent 1 message(s), recorded N paper(s)`。请用户在微信确认
收到 `学术速递 · 2026-10-22`。失败按 stderr 的 `[fail]` 修，不要重试到刷屏。

## 5. 接入定时

0–4 步都通过后再读定时说明。分发副本里只有对应客户端的那一份，路径是
`references/scheduling.md`；源目录里三份都在 `references/scheduling/`（下面三个路径只在
源目录存在）：

- DSH 看板卡：`references/scheduling/dsh.md`
- Claude Code：`references/scheduling/claude.md`
- Codex：`references/scheduling/codex.md`

接好定时后手动跑一次，确认微信收到当天真实日报，再把调度交给定时器。DSH 的建卡字段、
手动验收与失败演练在副本的 `references/scheduling.md` 里（源目录对应
`references/scheduling/dsh.md`）。

## 常见失败

- `github.token`：环境里没有 token。先 `set -a; . ./secrets.env; set +a`。
- `doctor` 某个源失败：网络/限速。隔几分钟重跑；不要改代码绕过。
- `push` 退出 2：缺 SendKey 或参数错误，先修环境，没发送任何东西。
- `push` 退出 1 且写了 pending：不要手工删；恢复通道后下一次运行会补发。
- 定时没触发或错过：见对应客户端的 `references/scheduling.md`；错过的调度不补跑，
  采集的 lookback 会覆盖最近几天。
