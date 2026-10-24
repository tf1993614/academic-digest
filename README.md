# 自动学术速递

每天按你的关键词，把 PubMed / Europe PMC / arXiv / Research Square / GitHub 的新内容
筛成一份中文日报，推送到微信。

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![License MIT](https://img.shields.io/badge/License-MIT-yellow)
![Clients](https://img.shields.io/badge/clients-Claude%20Code%20%7C%20Codex%20%7C%20DSH-6b4fbb)

> 脚本管事实，模型管表达，Server酱管到达。

## 这是什么

- 每天一次，按 `config.yaml` 里的关键词组（示例是六组）抓取 PubMed、Europe PMC、
  arXiv、Research Square 与 GitHub。
- 目标 **3 篇今日必读 + 7 篇其它速览**（候选不足时按实际数量）；今日必读带标签、
  摘要、局限性与方法精读。
- GitHub 单独成块：新库、活跃库、关注库的新 release，以及 AI 工具 / Agent Harness 的
  G6 区块。
- 一个自包含的 Agent Skill：仓库里同时提交 `.dsh`、`.claude`、`.agents` 三个扫描根下的
  生成副本，克隆后三家客户端各扫各的目录。
- 推送走 [Server酱](https://sct.ftqq.com/)，日报是 Markdown，手机微信直接可读。

## 为什么做

每天翻五个来源、读几十条英文摘要，真正值得读的往往只有几篇；RSS 只按时间排，不会按
你的关键词筛。这个项目把流程拆成三段：

1. **确定性脚本**负责采集、去重、排序、配额、校验与推送；
2. **模型**只负责读候选池、写 3 + 7 的选题理由与中文摘要；
3. **Server酱**负责到达。

采集、校验、推送都可以离线复现；模型写得好不好，有 `digest check` 按固定契约把关。

## 一期日报长什么样

下面是 `tests/fixtures/digest/valid/digest.md` 的节选（测试假数据，不是真实论文）：

```markdown
# 学术速递 · 2026-10-22
> 关键词：… ｜ 新论文 12 篇，精选 10 篇 ｜ GitHub 5 个

## 今日必读
### 1. Aging multi-omics atlas of the mouse brain
- 标签：`aging` `multi-omics`
- 摘要：…
- 局限性：…
- 方法精读：…
- [原文](…) · [PDF](…)

## 其它速览
- **Single-cell foundation model benchmark** — `single-cell foundation model` · 摘要：… · 局限性：… · [链接](…)

## GitHub
### 新项目
- **owner/repo** ⭐ 42 · Python · 2026-10-21 · 一句话定位 · 与哪组相关 · [链接](…)

## AI 工具 / Agent Harness
- **anthropics/claude-code v2.0.0**（官方 release，2026-10-21）· 更新要点 · [链接](…)

---
来源：pubmed ok (2) ｜ europepmc ok (9) ｜ github ok (5)
候选：12 ｜ 入选：10 ｜ 生成：2026-10-22T08:00:00+08:00
```

- 今日必读目标 3 篇，四要素齐全；方法精读只基于 OA 全文，拿不到就明确写“仅基于摘要”。
- 其它速览一篇一行，含摘要、局限、标签与链接。
- GitHub 三个区块与 G6 不占论文的 3 + 7 席位；没有更新时整块省略，不补空条目。
- 页脚覆盖每个源的状态、候选数、入选数与生成时间；`digest check` 会逐项校验。

## 快速开始（5 分钟）

要求：Python 3.11+、git。第一次先装一次依赖。最省事的是 `pip install -e .`：它会装依赖，
并顺带提供可选的 `academic-digest` 命令；`academic_digest` 的代码随 skill 走，入口脚本
自己解析 `sys.path`，所以不装这个包也能跑：

```bash
git clone https://github.com/tf1993614/academic-digest.git
cd academic-digest
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

下面四条命令只读 `tests/fixtures/` 里的录制响应，不联网、不需要 secrets、不需要
`config.yaml`：

```bash
# 1. 配置与录制响应自检
python3 skills/academic-digest/scripts/doctor.py \
  --config tests/fixtures/walking/config.yaml \
  --fixtures tests/fixtures/walking

# 2. 采集候选池；--now 固定逻辑时钟，输出可复现
python3 skills/academic-digest/scripts/collect.py \
  --config tests/fixtures/walking/config.yaml \
  --fixtures tests/fixtures/walking \
  --now 2026-10-22T08:00:00+08:00 \
  --out /tmp/candidates.json \
  --state-db /tmp/state.sqlite3

# 3. 校验一份模型写好的 selection 与日报
python3 skills/academic-digest/scripts/digest.py check \
  --candidates tests/fixtures/digest/valid/candidates.json \
  --selection tests/fixtures/digest/valid/selection.json \
  --digest tests/fixtures/digest/valid/digest.md

# 4. 构建 Server酱 payload；不读 SendKey、不发送
python3 skills/academic-digest/scripts/push.py \
  --config tests/fixtures/walking/config.yaml \
  --candidates tests/fixtures/digest/valid/candidates.json \
  --selection tests/fixtures/digest/valid/selection.json \
  --digest tests/fixtures/digest/valid/digest.md \
  --now 2026-10-22T08:00:00+08:00 \
  --dry-run
```

四条都退出 0，说明代码、fixture 与依赖都就位。接下来配置真实运行：

```bash
# secrets.env：写入 SERVERCHAN_SENDKEY 与 GITHUB_TOKEN，权限 600（gitignored）
skills/academic-digest/scripts/setup-secrets.sh
# config.yaml：从模板复制后按访谈调整（gitignored）
cp config.example.yaml config.yaml
set -a; . ./secrets.env; set +a
python3 skills/academic-digest/scripts/doctor.py --config config.yaml
```

`doctor` 联网检查每个源的连通性、GitHub 配额与状态库路径；看到最后一行
`doctor: all checks passed` 之后再接定时。

## 接到你的客户端

仓库自带三份生成副本，克隆后不需要再复制或软链即可被三家发现（依赖仍需按上一节装一次）：

| 客户端 | 扫描根 | 触发 |
|---|---|---|
| DSH | `.dsh/skills/` | 看板卡或会话中加载 `academic-digest` |
| Claude Code | `.claude/skills/` | `/academic-digest` |
| Codex | `.agents/skills/` | `/skills` 选择器 |

三份副本由 `scripts/sync-skills.sh` 从 `skills/academic-digest/` 生成，除
`references/scheduling.md` 外逐字节一致；**不要手改副本**，改源目录后重新同步。

想在所有仓库里使用，可以把对应副本软链到用户级扫描根：

```bash
mkdir -p ~/.dsh/skills ~/.claude/skills ~/.agents/skills
ln -sfn "$PWD/.dsh/skills/academic-digest" ~/.dsh/skills/academic-digest
ln -sfn "$PWD/.claude/skills/academic-digest" ~/.claude/skills/academic-digest
ln -sfn "$PWD/.agents/skills/academic-digest" ~/.agents/skills/academic-digest
```

运行数据（`config.yaml`、`secrets.env`、`out/`、`state/`）留在执行命令的那个仓库根，不跟着
skill 走；推荐始终在你克隆的仓库根运行。客户端的发现规则见
[Claude Code skills](https://code.claude.com/docs/en/skills) 与
[Codex skills](https://developers.openai.com/codex/skills)。

## 配置

`config.yaml` 从 [`config.example.yaml`](config.example.yaml) 复制，已被 gitignore。
最常改的几项：

- `timezone`：IANA 时区，默认示例是 `Asia/Shanghai`；
- `topics`：六组关键词与每组 `max_items`（G2 最多 4 篇，G6 独立成块）；
- `sources`：PubMed、Europe PMC、arXiv、Research Square、GitHub 默认开；
  bioRxiv / medRxiv 默认关；
- `lookback.arxiv`：至少 4 天，否则配置校验失败（周五到周一的公告会合并）；
- `journal_filter`：可选期刊白名单，默认不限；
- `push.sendkey_env`：SendKey 所在的**环境变量名**，默认 `SERVERCHAN_SENDKEY`；
  SendKey 本身不写进配置。

完整字段、默认值与校验规则见 [docs/configuration.md](docs/configuration.md)。

## 每天定时跑

- **DSH**：用看板卡，cron `0 8 * * *`、时区 `Asia/Shanghai`；看板起会话加载 skill，
  不经过 wrapper。建卡字段与 Prompt 见
  [`references/scheduling/dsh.md`](skills/academic-digest/references/scheduling/dsh.md)。
- **Claude Code / Codex**：同一个无人值守入口
  `skills/academic-digest/scripts/run-daily.sh <claude|codex>`；它加载 `secrets.env`、
  加并发锁、写 `out/logs/run-daily.log`、透传退出码。systemd、launchd、crontab 的可粘贴
  片段分别在
  [`references/scheduling/claude.md`](skills/academic-digest/references/scheduling/claude.md)
  与
  [`references/scheduling/codex.md`](skills/academic-digest/references/scheduling/codex.md)。

错过触发不会补跑；各源自己的 `lookback`（默认 2–4 天）会在下一次运行时补上窗口。
云端定时与 GitHub Actions 定时不在 V1 范围内。

## 命令与退出码

| 命令 | 用途 |
|---|---|
| `collect` | 抓取各源，写出候选池 `out/candidates.json` |
| `fulltext` | 取单篇 OA 全文，抽取方法 / 结果 / 局限 |
| `digest check` | 校验模型写的 `selection.json` 与 `digest.md` |
| `push` | 把校验过的日报推到微信 |
| `doctor` | 检查配置、源连通性与状态库路径 |

`--fixtures DIR` 只读录制响应、绝不联网；给出时应同时固定 `--now`。完整参数、产物与
退出码见 [docs/cli.md](docs/cli.md)。

| 退出码 | 含义 |
|---|---|
| `0` | 成功（含空日报按配置发送 / 跳过、`push --dry-run`） |
| `1` | 源、状态库、输出文件、自检、日报校验或推送失败 |
| `2` | 配置或参数错误、缺少 SendKey（尚未发起网络请求） |

## 失败时会发生什么

- **单个源失败**：其余源继续产出，`collect` 退出 0，日报页脚如实标 `failed`。
- **全部源失败**：`collect` 退出 1，不推送假日报。
- **推送失败**：每条消息默认重试 2 次；仍失败则写入 SQLite `pending`，下一次 live run 先补发。
- **空日报**：默认发一条“今日没有匹配的检索条目”；`push.send_empty: false` 时跳过并退出 0。
- **完成标准**：只有 `push` 退出 0 且 stdout 出现 `[ok] push:` 才算当天完成。

日报生成步骤需要一个能读候选池、跑命令的模型；采集、全文抽取、`digest check`、`push`
与 `doctor` 都是确定性脚本。

## 安全与隐私

- `SERVERCHAN_SENDKEY` 与 `GITHUB_TOKEN` 只从环境变量读取，不写进日报、日志、状态库或 git。
- `secrets.env` 权限应为 `600`；`config.yaml`、`secrets.env`、`out/`、`state/` 都在
  `.gitignore` 里。
- 错误信息会先脱敏；候选池不包含 Unpaywall 邮箱。
- 微信没有个人号 API，V1 只支持 Server酱；额度与限制以 Server酱官网为准。
- 启用 GitHub 源需要一个免费 token；Unpaywall 邮箱可选，留空只是少一条 OA 全文路径。
- 除采集请求与 ServerChan 推送外，不额外上传运行数据；本项目没有遥测。

## 项目结构

```text
skills/academic-digest/        # 源 skill：SKILL.md、references/、scripts/、academic_digest/
.dsh|.claude|.agents/skills/academic-digest/   # 三份生成副本（勿手改）
docs/                          # 命令、配置、开发记录、ADR、调研
tests/                         # 离线 fixture 与测试
scripts/                       # check / sync / check-skills / review-patch
config.example.yaml            # 配置模板
```

运行数据 `config.yaml`、`secrets.env`、`out/`、`state/` 留在仓库根，不跟着 skill 走。

## FAQ 与已知限制

- **Windows？** 用 WSL2；`set -a; . ./secrets.env` 是 bash 语法。
- **需要 API key 吗？** 采集与推送不需要 LLM key；写 3 + 7 日报需要你已登录的 Claude /
  Codex 订阅，或 DSH 里已配置的模型。GitHub 源需要一个免费 token。
- **为什么 bioRxiv / medRxiv 默认关？** 它们按日期区间全量拉取再本地过滤，量大；
  需要全量覆盖时再打开。
- **为什么只有 Server酱？** 微信没有个人号 API；V1 只做 ServerChan。
- **有云端定时或 GitHub Actions 定时吗？** 没有；定时只做本机调度与 DSH 看板卡。
- **arXiv 偶尔超时？** 单个源失败仍会发日报并在页脚标注；不会为了重试而重跑整次采集。
- **PDF 解析用什么？** PyMuPDF（AGPL-3.0）；HTML 用 beautifulsoup4 + lxml。再分发前请自行确认许可证兼容性。
- **V1 没有什么？** Web UI、邮件、公众号、多用户、反馈闭环、动态补窗都不在范围内。

## 开发、致谢与许可

一次跑完全部检查（mypy、pyflakes、文档一致性、pytest）：

```bash
scripts/check.sh
```

测试全部离线且固定 `--now`；CLI 是唯一的测试缝。更多约定见
[CODING_STANDARDS.md](CODING_STANDARDS.md) 与
[docs/agents/code-review.md](docs/agents/code-review.md)。

感谢 PubMed E-utilities、Europe PMC、arXiv、Research Square、GitHub API、Server酱、
PyMuPDF、BeautifulSoup 与 DSH 提供的接口和工具。

本项目以 [MIT License](LICENSE) 发布，作者 `tf1993614`。完整文档入口见
[docs/README.md](docs/README.md)。
