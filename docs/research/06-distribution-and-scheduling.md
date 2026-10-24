# 开源发布前的三个问题：Skill 落点、跨客户端定时、README 写法

> 2026-10-23。来源分三类：**官方文档原文**（agentskills.io、code.claude.com、learn.chatgpt.com、
> docs.github.com，均给出链接）、**本机安装的客户端实测**（`claude` 2.1.292、`codex` 0.163.0、
> DSH 0.2.1-rc.2 的包内 README 与 `--help`）、**本仓库现状核对**。凡是推断而非原文的，标 `[推断]`。

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 目录风格是否符合 skill 规范？ | **内容合规，落点不合规**。`name` 与目录同名、124 行、description 158 字，逐条过 agentskills.io 规范。但 `.dsh/skills/` 只有 DSH 扫；Claude Code 只扫 `.claude/skills/`，Codex 只扫 `.agents/skills/`。开源后别人克隆下来，三家里有两家看不见这个 skill。 |
| 没有 dsh-web 定时插件怎么办？ | **前提已经过期**：Claude Code 有云端 scheduled tasks（`/schedule`）、Desktop 定时、`/loop`；Codex 的定时在 ChatGPT/桌面端的 **Scheduled**。但真正稳的默认仍是**本机定时器（systemd timer / launchd）+ headless CLI**，原因不是"没有别的定时器"，而是本项目 `state/` 里的已推送集合必须跨天保留——云端任务每次都是全新 clone，去重状态会丢。 |
| README 怎么写？ | 借 Know-your-fate 的骨架（hero + 为什么 + 客户端安装 + 目录树），但**压到 200 行上下**：现在的 README 是 969 行、开头是 issue 进度流水账、没有 LICENSE、没有文档索引，这四条是发布前必须改的。 |

> 2026-10-24 补注：DSH 看板卡依赖 dsh-web 的 task-board 插件
> （`@linxin666/dsh-client-ui-task-board`），不是 DSH 核心；README 与
> `references/scheduling/dsh.md` 已补安装命令。

一句话：**先把 skill 放到三家都认的落点，再把"定时"拆成"谁定时 / 谁跑模型 / 状态存哪"三件事讲清楚，最后写一份 200 行、按客户端分列安装步骤的 README。**

## 1. Skill 规范与落点

### 1.1 官方标准是什么

Anthropic 把 Agent Skills 的格式开放成了 [agentskills.io](https://agentskills.io/specification)，
Claude Code 和 Codex 都明确说自己遵循它（[Claude Code skills 文档](https://code.claude.com/docs/en/skills)
第 19 行；[Codex build skills](https://learn.chatgpt.com/docs/build-skills) 第 6 行）。规范本身很短：

| 项 | 要求 | 本仓库 |
|---|---|---|
| 目录 | `<name>/SKILL.md` 必需；`scripts/`、`references/`、`assets/` 可选 | ✅ `.dsh/skills/academic-digest/SKILL.md` + `references/` |
| `name` | ≤64 字符；仅小写字母/数字/连字符；首尾不能是 `-`；不能有 `--`；**必须与父目录同名** | ✅ `academic-digest`，目录同名 |
| `description` | 非空，≤1024 字符，写清"做什么 + 何时用" | ✅ 158 字符 |
| 可选字段 | `license`、`compatibility`（≤500）、`metadata`、`allowed-tools`（实验性） | ⚪ 未用；`license` 值得加 |
| 体积 | SKILL.md < 500 行；细节放 `references/`，引用只到一层 | ✅ 124 行 / 6.0 KB；两个 reference 都是一层 |
| 渐进披露 | 启动只读 name+description（~100 tokens），命中后才读正文，`references/` 按需读 | ✅ 结构就是按这个分的 |

所以**不存在"层级不符合规范"这回事**：规范只要求"一个目录 + SKILL.md"，`references/` 在下面
一层也正是它推荐的组织方式。真正跟客户端不匹配的是**扫描根**。

### 1.2 三家的扫描根（决定落点）

| 客户端 | 仓库内落点 | 用户级落点 | 发现规则 | 软链 |
|---|---|---|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` | `~/.claude/skills/` | 从启动目录向上到仓库根逐层合并；`--add-dir` 目录也算；enterprise > personal > project；plugin 技能命名空间为 `/plugin:skill` | ✅ 允许，且同一目标只加载一次 |
| Codex | `.agents/skills/<name>/SKILL.md`（从 CWD 向上到仓库根） | `~/.agents/skills/`、`/etc/codex/skills/` | 同名不合并，两个都出现在选择器；`/skills` 或 `$name` 显式触发；隐式触发看 description | ✅ 支持并跟随目标 |
| DSH | `.dsh/skills/`（rank 100）、`.agents/skills/`（rank 200） | `~/.dsh/skills/`（400）、`~/.agents/skills/`（500） | 只扫第一层，不递归；目录 bundle 或扁平 `<name>.md` | ✅ 目录可以是指向别处的软链 |

三家交集只有一个：**`.agents/skills/`**（Codex 原生、DSH rank 200 也读）。Claude Code 不读它，
只认 `.claude/skills/`。

### 1.3 除了落点，还有两处"DSH 方言"

1. **正文写死了 DSH 的路径和概念**：`SKILL.md` 第 10 行"本 skill 在 `<repo>/.dsh/skills/...`"，
   以及"每日运行"里"看板卡每天 08:00 触发的固定三步"；`references/setup.md` 第 5–6 步整段是
   `task_board_create` / `update_goal` / `skipVerification`。Claude Code / Codex 用户读到会困惑，
   而且这套字段在别的客户端不存在。
2. **仓库根的 `SKILL.md` 软链**是给人看的，不是规范的一部分；规范和三家客户端都不认识"仓库根
   放一个 SKILL.md"。留着无害，但要在 README 里说明它是软链，别让用户以为要装它。

处理办法：正文改成"本 skill 的目录（`$(dirname SKILL.md)`）→ 用 `git -C` 找仓库根"这类**与落点无关**
的定位方式（现在的 `git -C` 写法已经是对的，只是前面那句路径要改），把 DSH 看板卡的内容整段挪到
`references/scheduling-dsh.md`，SKILL.md 只留一句"定时见 references/scheduling-*.md"。

### 1.4 三种落地方式（可选）

| 方案 | 做法 | 代价 |
|---|---|---|
| A. 仓库自带软链（推荐） | 真实目录留在 `.dsh/skills/academic-digest/`，仓库里提交 `.agents/skills/academic-digest` 与 `.claude/skills/academic-digest` 两条相对软链 | 克隆下来三家都能发现；Windows 需开发者模式或 `core.symlinks`，否则软链退化成文本文件（此时 `CLAUDE.md`/README 要给复制命令） |
| B. 搬成规范目录 | 真实目录搬到 `.agents/skills/academic-digest/`，`.dsh/skills` 与 `.claude/skills` 软链回去 | 同样三条路径，但改 `.dsh` 这个隐藏目录的语义，`SKILL.md` 里"本 skill 在 …"那句要跟着改 |
| C. 复制 + 校验 | 三个目录各放一份真实文件，`scripts/check-skills.sh` 比对哈希 | 跨平台稳；改一处要同步三处（CI 能兜住） |
| D. 只给指令 | 仓库存 `.dsh/skills/`，README 让用户自己 `ln -s` | 最省事，但"装 Claude Code 版"多一步手工，且第一次用大概率失败 |

软链要注意 `.dsh/skills/` 是**隐藏目录**：`ls` 看不见，`cp -r` 默认带上但容易漏，README 里要写明。
两个落点同时指向同一份文件不会让 DSH 报错：`dsh-skill` 注册表的规则是"同一层内同名 candidate
按 rank 决胜"（rank 100 的 `.dsh/skills` 盖住 rank 200 的 `.agents/skills`），最终只出现一个条目、
加载的仍是同一个文件（本机 `@deepseek-ai/dsh-skill/README.md` 第 84 行）。

### 1.5 分发单位是"仓库"，不是"skill 目录"——这是最难搬的一处

Know-your-fate 能写"只取某个技能目录，接到自己的 agent 里"，因为它的脚本放在**技能目录内部**
（`<skill>/scripts/*.py`）。本仓库不是：SKILL.md 要跑的是仓库根的 `scripts/collect.py` / `push.py`
和 `academic_digest/` 包，`references/digest.md` 只是写作契约。所以：

- 用户**不能**只 `cp -r academic-digest ~/.claude/skills/`，那样 skill 会被发现但一跑就找不到脚本。
- 正确的安装单位是 **clone 整个仓库**，再把 skill 目录软链进客户端的扫描根（§1.4 方案 A）。
- 如果希望"单目录可分发"，得把 `scripts/` + `academic_digest/` 挪进 skill 目录（`<skill>/scripts/`），
  并让入口脚本自己 `sys.path` 加自己所在目录——这是一次真实的目录重构，不只是移动文件。

这条直接决定 README 的写法：安装章节的第一句应该是 `git clone`，而不是"复制这个目录"。
（这个结论也解释了为什么 Claude Code 的 `${CLAUDE_SKILL_DIR}` 在本仓库"帮不上忙"——脚本不在 skill 目录里。）

### 1.6 要不要做成插件（V1：不要）

| 通道 | 一条命令装 | 代价 |
|---|---|---|
| Claude Code 插件 | `/plugin marketplace add owner/repo` + `claude plugin install <plugin>@<marketplace>` | 单 skill 也要包一层 `.claude-plugin/plugin.json`；技能名变成 `/academic-digest:academic-digest`；每轮上下文都带插件的组件清单 |
| Codex 插件 | `codex plugin marketplace add owner/repo`（仓库级清单在 `.agents/plugins/marketplace.json`） | 官方文档里**没有 `codex plugin install`**（CLI 只有 marketplace add/list/upgrade/remove）：装的动作在 ChatGPT 桌面 app 里，或手写 `.codex/config.toml` 的 `[plugins."p@market"]`——对"就想跑个日报"的人是负体验 |

结论：**一个 skill 不值得上插件**，`.agents/skills/` + `.claude/skills/` 的软链已经够零安装。
等有第二个 skill、或需要版本化发版时再说。顺带记两条以后会用到的规则：
Claude Code 上传/打包只接受标准 6 个字段，多一个字段是**硬失败**（本地加载则静默忽略未知字段）；
frontmatter 的 `name` 会覆盖目录名成为 `/` 菜单里的命令，但规范要求两者相同，别依赖这个差异。

## 2. 定时：三家各自有什么、缺什么

### 2.1 Claude Code 的四种"定时"（官方三选一 + 自己搭）

[官方对比表](https://code.claude.com/docs/en/scheduled-tasks#compare-scheduling-options)：

| | 云端 scheduled tasks | Desktop scheduled tasks | `/loop` |
|---|---|---|---|
| 跑在哪 | Anthropic 云（或自托管环境） | 本机 | 本机 |
| 要开机吗 | 不要 | 要 | 要 |
| 要会话开着吗 | 不要 | 不要 | **要** |
| 能读本机文件吗 | 不能（每次全新 clone） | 能 | 能 |
| 最小间隔 | 1 小时 | 表单 1 小时 / Claude 自设 1 分钟 | 1 分钟 |
| 计划 | Pro / Max / Team / Enterprise，research preview | 随 Desktop | 随会话，7 天过期 |

- 创建入口：`claude.ai/code/routines`、Desktop 的 **Scheduled**、或 CLI 里 `/schedule`
  （[routines 文档](https://code.claude.com/docs/en/routines)）。
- 云端任务 = "保存下来的 Claude Code 配置"：prompt + 一个或多个仓库 + connectors，在云上跑完整会话，
  **会用到 clone 下来的仓库里提交过的 skills**（routines 文档第 53 行）。也就是说：**先把仓库推到
  GitHub，云端定时才有意义**——这正好是你要做的事。
- 云端任务有两个坑，直接决定它能不能跑本项目：
  1. **网络**：默认 Trusted 只放行包仓库、GitHub、云 SDK。PubMed / Europe PMC / arXiv /
     ResearchSquare / ServerChan 都不在白名单里，必须把环境改成 **Custom**（列域名）或 **Full**
     （[cloud environments](https://code.claude.com/docs/en/cloud-environments#access-levels)）。
  2. **状态**：每次 run 都重新 clone，"上一次推到哪了"的 SQLite 不会跟着走（详见 §2.5）。
- 第三个坑是**批准**：云端 run 默认从 auto mode 开始，但撞上 ask 规则或反复被拦时，会话会停下来
  等人回答（[routines 文档](https://code.claude.com/docs/en/routines#permission-prompts-during-a-run)）。
  无人值守的日更任务要提前把 `python3 scripts/*.py` 放进 allow 规则，否则某天会卡在"等批准"。
- 管理入口：网页、Desktop、以及 CLI 的 `/schedule list|update|run`（routines 文档 "Manage scheduled
  tasks from the CLI"）。

### 2.2 Codex 的定时在别处

- **Scheduled tasks 在 ChatGPT 侧**：web/桌面端创建和管理；CLI 明确"不提供 Scheduled 管理界面"
  （[automations 文档](https://learn.chatgpt.com/docs/automations) 的 `cli` 段落）。桌面端的定时任务
  可以跑本地项目（要开机、app 开着）；web 端的任务**读不到本机文件夹**。
- 触发方式是 `$skill` 或 `/skills` 选择器（[build skills](https://learn.chatgpt.com/docs/build-skills)
  "Explicit invocation" 一段），隐式触发同样靠 description。
- 所以 Codex 用户有两条路：① 桌面端/网页端建一个 Scheduled task，prompt 里 `$academic-digest`；
  ② 不用它的定时，`codex exec` + 本机 cron。

### 2.3 本机定时器 + headless（不依赖任何客户端的定时功能）

这是三家都能用的公共底座，也是**唯一不丢状态**的方案。命令骨架：

```bash
# Claude Code：无人值守跑一次，/skill-name 在 print 模式下会被展开成技能
claude -p "/academic-digest" \
  --permission-mode acceptEdits \
  --allowedTools "Bash(python3 *),Read,Write,Edit" \
  --permission-prompts none \
  --max-turns 60 --output-format json

# Codex：exec 没有 --full-auto 了；默认沙箱是 read-only，网络默认关闭
codex exec -C /path/to/repo --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=true \
  --skip-git-repo-check --json -o /tmp/digest-last.md \
  "读取 .dsh/skills/academic-digest/SKILL.md 并照做：collect、写日报、digest check、push。"
```

几个容易踩的点（都是官方文档原文，不是经验）：

- **别用 `--bare` 跑 skill**。headless 文档写得很直白：不加 `--bare` 时"`claude -p` discovers and loads
  them as an interactive session would"；加了 `--bare` 则 Claude "doesn't get the list of available skills"。
  （`claude --help` 里"Skills still resolve via /skill-name"那句和 cli-reference 的"skip auto-discovery of
  skills"互相打架，按 headless 正文理解：**裸跑 `-p` 能按名字调 skill，`--bare` 不能**。）
  代价是 `--bare` 才不读 `CLAUDE_CODE_OAUTH_TOKEN`，所以订阅用户本来就不该加 `--bare`；CI 里要用
  `--bare`，就改走 `ANTHROPIC_API_KEY` 并把 prompt 写成"读某个 SKILL.md 路径"。
- `--permission-prompts none`（v2.1.259+）是"没人能回答批准"时的正解，比 `--dangerously-skip-permissions`
  安全；`--allowedTools` 的前缀匹配要求写 `Bash(python3 *)`，空格不能省。
- `--permission-mode` 六个取值（实测 `claude --help`）：`acceptEdits`、`auto`、`bypassPermissions`、
  `manual`、`dontAsk`、`plan`。`bypassPermissions` 官方标注"仅隔离容器/VM"。
- **Codex 的 `exec` 不会自己开网络**："By default, the agent runs with network access turned off"，
  必须显式 `-c sandbox_workspace_write.network_access=true`，否则 `collect.py` 连 PubMed 都到不了。
- **Codex 用 exec 按名字调 skill 没有文档保证**：`.agents/skills` 的发现规则写在交互界面那套文档里，
  `codex exec` 是否同样加载没说。稳妥写法是 prompt 里直接给 SKILL.md 路径（如上），别写 `$academic-digest`。

鉴权：Claude Code 订阅用户 `claude setup-token` 拿一年的 `CLAUDE_CODE_OAUTH_TOKEN`（`--bare` 下不读）；
API key 走 `ANTHROPIC_API_KEY` 且优先级高于 OAuth。Codex 用 `CODEX_API_KEY`（非交互专用）或
`printenv OPENAI_API_KEY | codex login --with-api-key`（不是 `--api-key`，实测没有这个 flag）。

调度侧（08:00 要落在 **Asia/Shanghai**）：

```cron
# crontab -e；flock 防止上一次没跑完就叠上来
0 8 * * * cd /path/to/repo && flock -n /tmp/academic-digest.lock \
  ./scripts/run-daily.sh >> /tmp/academic-digest.log 2>&1
```

时区是这里最容易出错的一处：`CRON_TZ` 只有 **cronie**（RHEL/Fedora 系）支持并写进 man page；
Debian/Ubuntu 的 vixie cron 文档和源码里都没有这个变量（本机就是 `cron 3.0pl1`，贴了等于没写），
FreeBSD/macOS 也没有。可行做法只有三种：机器本来就是 `Asia/Shanghai`（直接 `0 8 * * *`）、
按 UTC+8 换算成 `0 0 * * *`（中国 1991 年后没有夏令时）、或者用 systemd 的
`OnCalendar=*-*-* 08:00:00 Asia/Shanghai`（日历表达式自带时区）。

错过补跑的行为也不同：**cron 直接跳过**；**launchd 会在唤醒后补一次**（Apple man page：多个错过区间
"coalesced into one event upon wake from sleep"）；**systemd 要 `Persistent=true`** 才补，且只对
`OnCalendar=` 生效。三者都要显式设 `WorkingDirectory` 与 `PATH`——定时器的环境变量跟登录 shell 不是一套，
这是"手动能跑、定时失败"的头号原因。

（上面的 `flock` / `>>` 骨架是调研记录。Issue 03 落地后的形态是 skill 内的
`scripts/run-daily.sh <claude|codex>`：它自己解析仓库根并 `cd`、加载 `secrets.env`、用
`state/run-daily.lock` 的内核文件锁防止叠加、把输出写进 `out/logs/run-daily.log`、透传客户端
退出码，所以调度片段只需要一行 wrapper 调用。）

### 2.4 GitHub Actions（能跑，但有三处会咬人）

```yaml
# .github/workflows/daily.yml
on:
  schedule:
    - cron: "0 8 * * *"
      timezone: "Asia/Shanghai"   # 不写就是 UTC
  workflow_dispatch:
jobs:
  digest:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/cache/restore@v4     # state/ 被 gitignore，只能靠 cache 跨 run
        with: { path: state, key: digest-state-${{ github.run_id }}, restore-keys: digest-state- }
      - uses: anthropics/claude-code-action@v1
        with:
          claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          prompt: "/academic-digest"
          claude_args: '--allowedTools "Bash(python3 *),Read,Write,Edit" --max-turns 60'
        env:
          SERVERCHAN_SENDKEY: ${{ secrets.SERVERCHAN_SENDKEY }}
      - uses: actions/cache/save@v4
        if: always()
        with: { path: state, key: digest-state-${{ github.run_id }} }
```

注意这里没走 `claude -p --bare`：`--bare` 不加载 skill 目录（§2.3），而官方的 Actions 入口本来就是
`claude-code-action`，它接 `CLAUDE_CODE_OAUTH_TOKEN` 或 `ANTHROPIC_API_KEY` 两个 secret，
`prompt: "/academic-digest"` 直接展开技能。

三个代价：① **公共仓库 60 天无活动，scheduled workflow 会被自动禁用**（GitHub 官方原文）；
② 调度会被延迟、高峰期甚至丢队列（官方原文 "some queued jobs may be dropped"），不适合要求"正好 08:00"；
③ `state/` 只能靠 cache/提交，而它现在在 `.gitignore` 里——这是设计决定，不是遗漏。
所以 Actions 适合"求稳的云端兜底"，不适合当唯一方案。

### 2.5 本项目特有的五个约束（比选哪个定时器更重要）

1. **`state/` 必须跨天存活**。`collect.py` 用 `store.pushed_keys()` 过滤"已经推过的条目"
   （`academic_digest/collect.py:139`）。云端任务 / GitHub Actions 每次都是干净 clone，
   状态为空 → 最近 2–4 天的 paper 会再进候选池 → **日报重复**。
   取舍：① 本机跑（状态天然保留）；② 让任务把 `state/*.sqlite3` 提交回一个私有仓库/分支；
   ③ GitHub Actions 用 `actions/cache`（缓存可能被驱逐，不算可靠）；④ 改代码，把状态库路径做成
   `ACADEMIC_DIGEST_STATE` 环境变量并指向持久卷（只有自托管 runner 才有）。
2. **云端会话不读你机器上的 `~/.claude/skills/`**：官方明确说 cloud sessions（含云端定时任务）
   只加载"claude.ai 账号里的技能"和"clone 下来的仓库里提交过的技能"，个人目录里的技能会报
   "skill not found"。所以云端方案的前提是 `.claude/skills/academic-digest` **在仓库里**——
   这正好是 §1.4 方案 A 要提交的那条软链（软链在 fresh clone 里能否解析没有官方说明，属 `[推断]`；
   最稳的是复制一份真实目录）。
3. **网络域名**：`pubmed.ncbi.nlm.nih.gov`、`www.ebi.ac.uk`、`export.arxiv.org`、`rss.arxiv.org`、
   `api.github.com`、`sctapi.ftqq.com`（ServerChan），外加 Unpaywall 与预印本源。云端环境要逐个放行；
   Codex 的 `exec` 还要额外开 `sandbox_workspace_write.network_access=true`。
4. **时区**：看板卡/云端任务都按 IANA 时区；GitHub Actions 的 cron 支持 `timezone:` 字段
   （[官方](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)：
   "You can optionally specify a timezone using an IANA timezone string"），不写就按 UTC；
   crontab 的 `CRON_TZ` 只在 cronie 上有效（见 §2.3）。
5. **错过是否补跑取决于调度器**：cron 不补；launchd 唤醒后合并补一次；systemd 需 `Persistent=true`；
   看板卡与云端任务不补。真正的兜底是 `lookback`（arXiv 默认 4 天，因为周五到周一的投稿合成一批）。
   README 要把这句写出来，否则用户会以为漏一天就断更。

### 2.6 该推荐哪一种

| 人群 | 推荐 | 理由 |
|---|---|---|
| 只想每天收到微信、不折腾 | **systemd timer / launchd + `claude -p "/academic-digest"`** | 状态不丢、复用订阅、域名不设限；systemd 的 `Persistent=true` 与 launchd 的合并补跑还顺带解决"错过一天" |
| macOS 用户 | **launchd**（同上，`StartCalendarInterval`） | 唤醒后补一次，比 cron 稳 |
| 经常合盖 / 想脱离本机 | **Claude Code 云端 scheduled task**（仓库必须已推 GitHub，且 `.claude/skills/` 要提交） | 不要开机；代价是网络白名单、`.claude/skills` 必须进仓库、状态要另想办法 |
| 有 GitHub 仓库、愿意配 secrets | GitHub Actions + `claude-code-action` | 有运行历史、可手动触发；但公共仓库 60 天无活动会被禁用，调度延迟甚至丢队列，状态要 cache |
| 当前作者本人 | 保持 DSH 看板卡 | 已经跑通，有执行历史和权限门 |

一句话版：**"本机定时器"当默认，"云端/CI"当进阶，"纯脚本无模型"不是降级方案**——第 2 步写日报
本来就是产品本身，没有模型就没有日报可推。

**README 里"已实现"和"方案"必须分开写**，否则又变成 KYF 那种会被时间打脸的断言：

| 路径 | 现在仓库里有什么 | 该怎么措辞 |
|---|---|---|
| DSH 看板卡 | 已实现：`setup.md` 第 5–6 步 + 一张真跑过的卡 | "已实现，作者自用" |
| 本机 cron + headless | 已实现（Issue 03）：skill 内的 `scripts/run-daily.sh <claude\|codex>` | "已实现，复制即用" |
| GitHub Actions | `ci.yml` 只有 push/PR，没有 `schedule` | "示例，未启用" |
| 云端 scheduled task | 客户端功能，仓库不需要代码 | "在客户端里建，参考 §2.1" |

### 2.7 需要在仓库里补的东西（工程 TODO，不是文档）

- `scripts/run-daily.sh`：headless 入口（加载 secrets、调 CLI、日志、退出码），README 直接引用它。
  **已落地**（Issue 03）：实际位置是 `skills/academic-digest/scripts/run-daily.sh`（随 skill 分发，
  不在仓库根），参数是 `<claude|codex>`。
- `references/scheduling-{dsh,claude,codex}.md`：把现在写死在 `SKILL.md`/`setup.md` 里的 DSH 看板卡步骤
  挪成"可选后端"，SKILL.md 只留一句"定时见 references/"。
- 状态库路径可配置（`--state-db` 已有，但需要环境变量/文档化的持久化建议）。
- 可选：`digest` 的纯脚本降级（无模型时按分数出 10 条摘要表格）——**目前不存在**，不要在 README
  里承诺"不需要模型"。

## 3. README 怎么写

### 3.1 借什么、不借什么

[Know-your-fate](https://github.com/tf1993614/Know-your-fate) 的可迁移手法：一行说清"形态 + 数量 +
平台"；"让脚本负责事实、让模型负责表达"这类可复述的架构主张；安装按 **方式 A / 方式 B** 分，
方式 B 就是"只要技能文件，自己接到 Claude Code / Codex"；每个客户端给"路径 + 是否原生 + 触发方式"；
根 README 明确让位给子文档（`app/README.md` 是"操作层权威文档"）。

不要借的：营销腔（"真正跑起来""该算的没算准"）；同一内容在三处重复（技能表 + `<details>` + 英文版）；
以及**未核实的客户端断言**——它写"Codex CLI 无原生 skill 加载器"，在 2026-10 已经不成立
（Codex 官方文档明确有 skills、扫描 `.agents/skills`）。这正好说明 README 里每条客户端声明都要附官方链接。

### 3.2 建议的 H2 骨架（目标 ≤250 行）

| # | H2 | 内容 | 素材 |
|---|---|---|---|
| 1 | 这是什么 | 一句话 + 4 个 badge + 一张日报截图 | 重写 |
| 2 | 为什么做 | 每天翻 5 个源的痛点 + "脚本管事实、模型管表达、Server酱管到达" | `docs/research/00-synthesis.md` |
| 3 | 日报长什么样 | 3+7 + GitHub 三块 + G6；一期真实日报折叠 | `tests/fixtures/digest/valid/` |
| 4 | 快速开始（离线 5 分钟） | doctor → collect(fixture) → digest check → push --dry-run，每条给预期输出 | 现有 L17–107 压缩 |
| 5 | 接到你的客户端 | **先 clone 整个仓库**（脚本在仓库根，见 §1.5），再三家落点表 + 两条软链 + 每家 `<details>` | §1.2 / §1.4 |
| 6 | 配置 | 六组关键词、`lookback.arxiv≥4`、`journal_filter`、SendKey 只走环境变量 | `config.example.yaml` |
| 7 | 每天定时跑 | 三方式对比表（本机 / 云端 / DSH 卡）+ 每方式一个 `<details>` | §2 |
| 8 | 命令与退出码 | 5 条命令 + 0/1/2；完整参数移 `docs/cli.md` | 现有 §命令 |
| 9 | 失败时会发生什么 | 单源失败仍发、全失败不发、pending 次日补发 | `SKILL.md` 末段 |
| 10 | 安全与隐私 | 只读环境变量、600、gitignore、日志脱敏 | `references/setup.md` |
| 11 | 项目结构 | 12 行 tree | 实际目录 |
| 12 | FAQ / 已知限制 | Windows、要不要 API key、Server酱额度、为什么只有 Server酱 | 散落各处 |
| 13 | 开发与贡献 | `scripts/check.sh`、pytest、ADR；细节移 `CONTRIBUTING.md` | 现有 §开发 |
| 14 | 致谢与许可 | MIT（**需新增 LICENSE**）、数据源致谢 | 新写 |

### 3.3 必须说清的四件事（现在 README 里分散、容易漏）

1. **第 2 步需要一个模型**：collect / digest check / push 都是确定性 Python；把候选池变成 3+7 日报
   要模型读文件、跑 `fulltext`。没有模型，"不需要 API key"就是假的。
2. **微信要 Server酱**：个人微信没有官方 API；免费 5 条/天、单条 32 KB；不配 SendKey 时 `push` 退出 2。
3. **三种客户端的路径要落到命令**，不要写"支持三家"了事；并说明"支持"指的是**发现 SKILL.md**，
   不包含定时——定时是 §7 的事。
4. **安装单位是整个仓库**（§1.5）：脚本在仓库根，`cp -r` 一个 skill 目录跑不起来。

顺带两条 skill 文案的规范：`description` 用**第三人称**写"做什么 + 何时用"（官方 best practices 要求，
因为描述会被注入系统提示）；四家客户端都**没有语言限制**（158 字符远低于 Claude Code 的 1536 截断与
Codex 的 2% 上下文预算），但隐式触发靠语义匹配，若要面向英文用户，description 里补几个英文关键词
（`PubMed, arXiv, WeChat, daily digest`）比写一份英文版 README 便宜得多。

### 3.4 发布前清单

- [ ] 新增 `LICENSE`（MIT），`pyproject.toml` 补 `license`（**当前缺失**）
- [ ] 根 README 从 969 行压到 ≤250 行，issue 进度流水账移走
- [ ] `docs/README.md` 索引，根 README 每段"移走"处留一行相对链接
- [ ] `.gitignore` 覆盖 `config.yaml`、`secrets.env`、`state/`、`out/`（已覆盖）
- [ ] `git grep -nE "SCT[0-9]"` 为空；示例里只有占位符
- [ ] 截图/日志脱敏（SendKey、openid、邮箱）
- [ ] 三客户端 smoke：Claude Code 能列出 `/academic-digest`、Codex `/skills` 能看到、DSH catalog 能看到
- [ ] 仓库 topics：`claude-skills`、`codex`、`academic`、`pubmed`、`arxiv`、`wechat`、`serverchan`
- [ ] 打 `v0.1.0` tag；CI 里加"软链/复制一致性"检查（若选方案 A/B）

## 4. 需要你拍板的问题

1. **skill 落点**：保留 `.dsh/skills/academic-digest/` 当真实目录、仓库提交两条软链（改动最小），
   还是搬成 `.agents/skills/academic-digest/`（"两家原生"更正统，但要改 SKILL.md 里那句路径）？
2. **要不要把 `scripts/` + `academic_digest/` 搬进 skill 目录**，让"只拷一个目录"成为可能？
   这是唯一能让本仓库像 Know-your-fate 那样"方式 B：只要技能文件"的改法，但会动包结构和所有入口。
3. **软链还是复制**：软链（省事、Windows 要开发者模式）vs 复制 + CI 校验（跨平台稳、三处同步）。
   云端定时任务那条路还要考虑"fresh clone 里软链能不能解析"（官方没写）。
4. **定时默认推荐谁**：本机 systemd/launchd 当默认 + 云端/CI 当进阶，还是反过来？
   README 要不要把 DSH 看板卡降级成"作者自用"？
5. **要不要为云端/CI 改代码**（状态库可外部持久化 + 可复现的 `run-daily.sh`），还是只在文档里写
   "云端会重复、请用本机"？
6. **README 语言**：只中文，还是中文 + `README.en.md`（后者要考虑谁来同步）。
7. **skill 的 description 要不要中英混写**：现在纯中文；加 `PubMed / arXiv / WeChat / daily digest`
   这类英文关键词能扩大隐式触发面，成本只是几十个字符（离 1024 还远）。

我的倾向（供讨论，不是结论）：1 选"保留 + 两条软链"，2 暂不做，3 选软链 + Windows 说明，
4 本机为默认，5 先只写文档，6 只中文 + 一段 English summary，7 加英文关键词。

## 5. 来源

- 规范：[agentskills.io specification](https://agentskills.io/specification)（目录、frontmatter 约束、
  渐进披露、文件引用、校验）
- Claude Code：[skills](https://code.claude.com/docs/en/skills)（落点/优先级/软链/插件）、
  [scheduled tasks 对比](https://code.claude.com/docs/en/scheduled-tasks#compare-scheduling-options)、
  [routines（云端定时）](https://code.claude.com/docs/en/routines)、
  [cloud environments](https://code.claude.com/docs/en/cloud-environments#access-levels)、
  [headless](https://code.claude.com/docs/en/headless)、[cli-reference](https://code.claude.com/docs/en/cli-reference)
  （`--bare` 跳过 skill 自动发现）、`claude --help`（2.1.292 实测：`--permission-mode
  acceptEdits|auto|bypassPermissions|manual|dontAsk|plan`；`--bare` 段又写 "Skills still resolve via
  /skill-name"，与 cli-reference 冲突，需实测）、[authentication](https://code.claude.com/docs/en/authentication)
  （`setup-token` → `CLAUDE_CODE_OAUTH_TOKEN`，`--bare` 不读）、[permission-modes](https://code.claude.com/docs/en/permission-modes)
- Codex：[build skills](https://learn.chatgpt.com/docs/build-skills)（`.agents/skills` 扫描根、`/skills`、
  `$name`、`agents/openai.yaml`、软链）、[scheduled tasks](https://learn.chatgpt.com/docs/automations)
  （CLI 无 Scheduled 界面）、[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
  （`--full-auto` 已移除，用 `--sandbox workspace-write`）、
  [agent-approvals-security](https://learn.chatgpt.com/docs/agent-approvals-security)（网络默认关闭）、
  [config-reference](https://learn.chatgpt.com/docs/config-file/config-reference)
  （`sandbox_workspace_write.network_access`）、[auth](https://learn.chatgpt.com/docs/auth)
  （`codex login --with-api-key`；`CODEX_API_KEY`）；`codex exec --help` / `codex features list`（0.163.0 实测）
- 本机定时器：[cronie crontab(5)](https://man7.org/linux/man-pages/man5/crontab.5.html)（`CRON_TZ`）、
  Debian [cron 源码 crontab.5](https://salsa.debian.org/debian/cron/-/raw/master/crontab.5)（无 `CRON_TZ`）、
  [launchd.plist(5)](https://raw.githubusercontent.com/apple-oss-distributions/launchd/main/man/launchd.plist.5)
  （唤醒后合并补跑）、[systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
  （`Persistent=true`）、[systemd.time](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html)
  （`OnCalendar` 带时区）、[schtasks create](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create)
- GitHub Actions 补充：[workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、
  [claude-code-action](https://code.claude.com/docs/en/github-actions)
- DSH：本机 `@deepseek-ai/dsh-skill-filesystem/README.md`（扫描根与 rank、只扫第一层、软链）
- GitHub Actions：[events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
  （UTC 默认、`timezone:` 字段、公共仓库 60 天无活动自动禁用、最小 5 分钟）
- README：[about-readmes](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)、
  [Know-your-fate](https://github.com/tf1993614/Know-your-fate)、[anthropics/skills](https://github.com/anthropics/skills)、
  [obra/superpowers](https://github.com/obra/superpowers)、[arxiv-sanity-lite](https://github.com/karpathy/arxiv-sanity-lite)
