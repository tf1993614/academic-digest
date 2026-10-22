# DSH Skill 与任务看板集成调研

> 调研时间：2026-10-22。来源：本机安装的 DSH 包与任务看板插件源码/README，不是网络二手资料。

## TL;DR

- **Skill 就是一个目录**：`<root>/<name>/SKILL.md`，YAML frontmatter 至少要有 `name`（kebab-case）和 `description`；可以带 `scripts/`、`references/`、`assets/`。DSH 只在扫描根的**第一层**发现 skill，不递归。
- **扫描根**：项目根 `<projectRoot>/.dsh/skills`（rank 100）、`.agents/skills`（200）、自定义目录（300）、用户级 `~/.dsh/skills`（400）、`~/.agents/skills`（500）。项目根是最近的含 `.git` 的祖先；没有 `.git` 时就是当前 cwd。
- **任务看板是 Host 权威的 cron 调度器**：5 段 cron + IANA 时区，卡片可钉住工作区/预设/权限/模型；到点后新建（或复用）一个真实 DSH 会话，把卡片 Prompt 以 queue 模式发进去。
- **每日推送卡推荐**：`goalRun: true` + `skipVerification: true`，Prompt 明确要求“只有 push 脚本返回成功才调用 `update_goal(action: complete)`”。这样既有完成门，又不会每天烧 6 次验收裁判调用。
- **必须接受的运维约束**：Host 进程必须活着；机器睡眠/关机期间错过的 cron **不补跑**（跳过），卡在运行中也会跳过当次。因此采集脚本必须按“上次成功时间”做补窗，而不是固定只看昨天。
- **权限门**：卡片有效权限高于部署默认权限时，cron 会拒绝调度直到有人在看板 UI 里确认。稳妥做法是卡片权限钉 `workspace-write` 并确认它不高于当前部署默认值。

## 1. Skill 的格式与发现规则

来源：`@deepseek-ai/dsh-skill-filesystem` 的 `README.md`（本机 `.../dsh/node_modules/@deepseek-ai/dsh-skill-filesystem/README.md`）。

| 事实 | 内容 |
|---|---|
| 目录 bundle | `<root>/<name>/SKILL.md` |
| 扁平文件 | `<root>/<name>.md` |
| 递归 | **不递归**；嵌套的 `**/SKILL.md` 故意不发现 |
| frontmatter 必填 | `name`、`description` |
| 可选 | `whenToUse`、`metadata`、`disable-model-invocation`、`user-invocable` |
| name 约束 | kebab-case |
| 加载方式 | 目录只解析 frontmatter 进 catalog；每次调用重新读正文，改正文不需要重启 |
| 扫描根优先级 | `project-dsh` 100 → `project-agents` 200 → `custom` 300 → `user-dsh` 400 → `user-agents` 500 |

对本项目的含义：

1. 把 skill 放在仓库的 `.dsh/skills/academic-digest/`，只要任务看板卡片钉住的工作区是这个仓库，定时会话就能在 catalog 里看到它。
2. 想让任意工作区都能用，再软链到 `~/.dsh/skills/academic-digest`。
3. 不要把 skill 嵌在更深层目录（如 `.dsh/skills/group/academic-digest/`），不会被发现。
4. `description` 是唯一的触发面；定时卡片的 Prompt 里要显式写“加载 academic-digest skill”，不要依赖模型自己猜。

## 2. 任务看板的执行与调度语义

来源：`@linxin666/dsh-client-ui-task-board` 的 `README.zh.md`（本机 profile 的 `node_modules` 下）。

### 2.1 执行

- 手动运行和定时运行共用 Host runner：默认新建独立会话、重命名、应用 agent 预设和 `/permission <id>`，再以 queue 模式发送任务 Prompt。
- 卡片可钉住：工作区、agent 预设、权限、模型、思考强度、是否复用会话、是否以 `/goal` 开始、是否跳过验收。
- 子任务树会并发执行；本项目单卡即可，不需要子任务。

### 2.2 调度

- 5 段 cron，支持 `*`、`*/n`、范围、逗号列表、周日 `0/7`。
- 每条规则带自己的 IANA 时区，默认跟随 Host；本机账本当前是 `Asia/Shanghai`。
- 日期/星期遵循 Vixie 语义：两个字段都受限时是 OR，否则 AND。
- 循环 cron 可设 `maxRuns`；不限次就省略。
- **同一任务已在运行时，到点出现会被跳过并滚到下一个 cron 匹配点**，不排队、不并发。
- **Host 停机错过的触发点直接跳过，不补跑**；单次计划错过即结束。
- 定时预算只统计调度器真正开启的执行；手动执行不消耗次数。

### 2.3 验收（goal verification）

- 默认开启。以 goal 形式执行的任务，`update_goal(action: complete)` 会被看板拦截，必须先通过一次验收。
- 验收是 3 项 coding 判据 × 2 轮 = 6 次裁判请求；同一 execution 最多验收两次，最坏 12 次额外请求。
- 判据偏 coding（Specification Adherence、Output Match、Error Signal Detection），对“抓取+总结+推送”这种任务并不天然贴合，且每天跑一次成本不可忽略。
- 单卡可以勾“跳过本任务的验收”（`skipVerification: true`），执行记录标注 `applicability: skipped`。
- 若 `goalRun` 为 false，则根本不进入 goal 验收；但也就没有“必须调用 complete 才算完成”的完成门。

### 2.4 权限确认门

- 卡片有效权限（钉住字段或交接包）高于部署 `sessionDefaultPermission` 时，处于待确认状态：手动执行被拒绝，cron 跳过该卡。
- 变更钉住权限会重新武装确认门。
- 因此定时卡片的权限应尽量与部署默认一致；本机文件策略是 `workspace-write`，采集脚本要写状态文件，不能用 `read-only`。

## 3. 推荐的任务卡配置

```jsonc
{
  "title": "每日学术速递",
  "description": "按 config.yaml 的关键词抓取 PubMed/Europe PMC/arXiv/bioRxiv/Research Square/GitHub，总结后推送到微信。",
  "prompt": "加载 academic-digest skill，执行今日推送：先运行 scripts/collect.py，再按 references/digest-template.md 写 digest.md，最后运行 scripts/push.py。只有 push.py 退出码为 0 且返回 success=true 时才调用 update_goal(action: complete)；任何一步失败都不要调用 complete。",
  "permission": "workspace-write",
  "goalRun": true,
  "skipVerification": true,
  "schedule": {
    "enabled": true,
    "mode": "cron",
    "cron": "0 8 * * *",
    "timeZone": "Asia/Shanghai"
  }
}
```

说明：

- `goalRun: true` 让执行有明确的完成门：没调用 `update_goal(complete)` 的卡会被判失败，而不是“回合结束就算成功”。
- `skipVerification: true` 避免每天 6–12 次裁判调用；真正的验收交给 `push.py` 的返回值和 `state/runs.jsonl` 日志。
- 如果部署默认权限低于 `workspace-write`，第一次需要人在看板 UI 确认；否则 cron 不跑。

## 4. 推荐的能力分层：Skill + 脚本，而不是纯 Prompt

纯 skill（让模型每天用 curl 抓十几个源、读几百条摘要、再总结）的问题是：

- 抓取量不可控：几百条摘要塞不进上下文；
- 不确定性高：每天路径不同，失败难复现；
- 贵：大量 token 花在搬运而不是总结。

推荐分层：

| 层 | 谁做 | 产出 |
|---|---|---|
| 采集/归一化/去重/打分 | `scripts/collect.py`（确定性 Python） | `out/candidates.json`（top N，含摘要） |
| 总结/选题/写日报 | 会话里的模型（按 skill 模板） | `out/digest.md` |
| 排版/分条/推送/记账 | `scripts/push.py`（确定性 Python） | 微信消息 + `state/pushed.jsonl` |
| 定时/执行/完成门 | 任务看板 | 每天 08:00 一个 execution |

这样模型每天只读 10–15 条候选、写 1 篇日报，token 可控；采集失败、推送失败都是脚本的非零退出码，可复现。

## 5. 目录布局建议

```
academic-digest/
├── SKILL.md
├── scripts/
│   ├── collect.py        # 多源抓取 + 归一化 + 去重 + 排序
│   ├── push.py           # 排版 + 微信通道 + 记录已推送
│   ├── doctor.py         # 网络/密钥/通道自检 + 测试推送
│   └── state.py          # 已推送/运行日志（SQLite 或 JSONL）
├── references/
│   ├── sources.md        # 各源查询语法与限制（来自调研）
│   └── digest-template.md
└── assets/
    └── config.example.yaml
```

运行时文件放仓库根的 `config.yaml`、`secrets.env`、`state/`、`out/`，不要放进 skill 目录（skill 可能被软链/只读）。

## 6. 凭据与安全

- `secrets.env` 权限 600，`.gitignore` 掉；skill 只从环境变量或该文件读取，不打印、不写进 digest、不写进任务卡 Prompt。
- Server酱 SendKey 以 `sctp` 开头时端点是 `https://{uid}.push.ft07.com/send/{key}.send`，否则 `https://sctapi.ftqq.com/{key}.send`。
- GitHub token 只给 public repo 读权限即可（classic PAT 不需要任何 scope 就能读 public；fine-grained 给 Public repositories read）。
- 任务卡 Prompt 和看板 transcript 会留存，**绝不要把 key 放进 Prompt**。

## 7. 已知风险清单

1. **Host 不在线 = 当天不推**。解决：collect 按 `state/last_success` 补窗（最多 7 天），下次运行把漏掉的补进摘要；不要假设每天都有触发。
2. **cron 到点时卡还在跑** → 当次跳过。解决：单次运行控制在 10 分钟内；加运行锁，避免手动+定时并发。
3. **权限确认门** → cron 静默不跑。解决：首次配置后手动跑一次，确认看板执行记录正常；权限尽量用 `workspace-write`。
4. **验收成本** → 每天 6–12 次裁判调用。解决：`skipVerification: true`，用脚本退出码做真实门禁。
5. **skill 不被发现** → 定时会话看不到 skill。解决：skill 必须在 `<workspace>/.dsh/skills/<name>/SKILL.md` 或 `~/.dsh/skills/<name>/SKILL.md`，且目录只有一层。
6. **模型不调用 skill** → 每天路径漂移。解决：Prompt 第一句显式“加载 academic-digest skill”，并给出固定的三步命令。
