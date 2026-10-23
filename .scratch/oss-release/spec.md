# 仓库重构 · Spec

Status: ready-for-agent

## Problem Statement

这个仓库只以 DSH 一种形态交付：skill 放在 `.dsh/skills/academic-digest/`，入口脚本和 Python 包在仓库根，`README.md` 是一份 969 行的开发进度记录。结果是三件事同时不成立：

- **Claude Code 与 Codex 用户装了也用不了。** 两家都只从自己的扫描根发现 skill（`.claude/skills/`、`.agents/skills/`），克隆仓库后看不到任何东西；即使手工把 skill 目录拷过去，它也会"被发现但一跑就找不到脚本"，因为代码不在 skill 里。
- **没有地方写各自的定时方案。** 三家客户端的无人值守入口完全不同（DSH 看板卡、`claude -p`、`codex exec`），而现在唯一的说明写在 `SKILL.md` 里，只讲看板卡。
- **仓库对外不可读。** 访客看到的第一屏是 issue 进度流水账，没有许可证，命令参考、配置说明、测试 fixture 清单全混在同一份文件里。

## Solution

把交付单位从"仓库 + 一个 DSH skill"改成"一个自包含的 skill + 三份各客户端的副本"：

- 仓库里有一个**源 skill 目录**，包含 `SKILL.md`、写作契约、入口脚本和 Python 包；把它整个拷走就能在对应客户端里直接工作，不需要安装 Python 包。
- 在三个客户端各自的扫描根下提交**生成的副本**；三份副本之间只允许 `references/scheduling.md` 不同，其余逐字节一致，由同步脚本生成、由校验脚本在 CI 里拦截漂移。
- 定时只做 CLI 形态，每个客户端在自己的 `scheduling.md` 里写清入口（看板卡 / `claude -p` / `codex exec`），共用一个无人值守 wrapper；云端定时任务与 GitHub Actions 不进这一版。
- 运行数据（配置、secrets、候选池、状态库）永远留在仓库根，不跟着 skill 走。
- 现有 `README.md` 作为开发记录迁入 `docs/`，用户真正会查的命令与配置拆成两份参考文档；面向访客的 README 在本 spec 之外单独写。

## User Stories

1. 作为一个只用 Claude Code 的研究者，我想克隆仓库后直接 `/academic-digest` 就能触发，这样我不用读源码就知道它被正确安装。
2. 作为一个只用 Codex CLI 的研究者，我想克隆后在 `/skills` 里看到 `academic-digest`，这样我不需要额外配置就能用。
3. 作为一个 DSH 用户，我想保持现有的看板卡继续工作，这样这次重构不会中断我每天 08:00 的日报。
4. 作为一个不想装 Python 包的用户，我想克隆后直接跑 skill 里的脚本，这样我不必理解 `pip install` 与 `pyproject.toml`。
5. 作为一个已经装过包的用户，我想继续用 `academic-digest` 命令行入口，这样我的旧习惯不被打断。
6. 作为一个只看得到 `SKILL.md` 的 agent，我想在该文件里找到"每日三步"和"定时去哪看"，这样我不用猜仓库结构。
7. 作为一个配置定时的用户，我想在对应客户端的 `scheduling.md` 里复制一段就能用，这样我不用把三家的命令都读一遍。
8. 作为一个用 systemd 的用户，我想 wrapper 已经处理好 secrets 加载、并发锁、日志和退出码，这样我的 timer 单元只需要一行 `ExecStart`。
9. 作为一个用 launchd 的 macOS 用户，我想看到 `StartCalendarInterval` 的完整片段，这样我不必把 cron 语义翻译过来。
10. 作为 Codex 用户，我想 `scheduling.md` 明确写出"网络默认关闭、需要打开 sandbox 网络"，这样我的第一次运行不会卡在采集超时。
11. 作为 Claude Code 用户，我想 `scheduling.md` 明确写出"用 `-p` 不要加 `--bare`"，这样我不会踩到 skill 不被加载的坑。
12. 作为一个只想拿一个目录的用户，我想把某个副本目录整个拷进自己的 dotfiles，这样它离开本仓库也能跑。
13. 作为 Windows 用户，我想文档明确说"用 WSL2"，这样我不会花时间在一条不被支持的路上。
14. 作为维护者，我想改 skill 只改一个地方，这样我不会在三份文件之间来回对齐。
15. 作为维护者，我想忘记同步时 CI 立刻变红，这样漂移不会活过一个 PR。
16. 作为维护者，我想新增第四个客户端只需要加一份 `scheduling.md` 和一行同步配置，这样扩展不是重写。
17. 作为维护者，我想副本文件在 diff 里被折叠显示，这样评审时三份重复内容不会淹没真正的改动。
18. 作为评审者，我想在 PR 里只看到源目录的改动 + 一份调度文档，这样我能逐行读完关键部分。
19. 作为贡献者，我想 `scripts/check.sh` 仍然是唯一的检查入口，这样我不需要记住五个命令。
20. 作为贡献者，我想测试用"用户会敲的命令"来验证，这样我不会写出只对内部导入有效的测试。
21. 作为贡献者，我想 CI 证明"不装包也能跑"和"副本真的能跑"，这样我改动 bootstrap 时立刻知道有没有弄坏。
22. 作为一个复盘的人，我想读到为什么是三份副本而不是软链，这样我不会把刻意的设计当成疏忽去"修复"。
23. 作为一个读术语表的人，我想知道 `skill` 在这份文档里指什么，这样我不会把它和"插件"或"命令"混用。
24. 作为一个新访客，我想看到一份短 README 而不是 969 行流水账，这样我能在两分钟内判断要不要用。
25. 作为一个要查参数的现有用户，我想在 `docs/` 里找到完整的命令与配置参考，这样我不用翻开发记录。
26. 作为一个要给这个项目提 PR 的人，我想知道测试怎么跑、fixture 在哪，这样我能复现你的检查。
27. 作为作者，我想发布前确认许可证存在且署名正确，这样别人可以合法复用。
28. 作为作者，我想先在私有远端验证"fresh clone 能不能跑"，这样公开后的第一次反馈不是"装不上"。

## Implementation Decisions

- **单一源 skill。** 仓库根新增一个源 skill 目录，内含 `SKILL.md`、`references/`、入口脚本与 Python 包。它是唯一的编辑对象；任何副本都是生成物。
- **代码随 skill 走。** 采集、写作校验、推送、自检四个入口以及 `academic_digest` 包整体搬进源 skill 目录。每个入口脚本自行把所在 skill 目录加入 `sys.path`，因此"克隆即跑、不装包"成立。
- **三份提交到仓库的副本。** 副本落在 `.dsh/skills/`、`.claude/skills/`、`.agents/skills/` 三个客户端扫描根下。这三个路径是协议契约（各客户端的发现规则），不是实现细节，因此保持不变。
- **差异边界只有一个文件。** 三份客户端方案写在源 skill 的 `references/scheduling/` 下（对维护者可见、不随副本分发）；同步时把对应那份落成副本内的 `references/scheduling.md`，文件头留一行"由同步脚本生成"的标记。除此之外的任何字节差异都视为错误。
- **同步与校验是一对。** 同步脚本：拷整棵树、排除 `references/scheduling/`、写入对应 `scheduling.md`。校验脚本：把同步结果生成到临时目录，与已提交副本逐字节比较（只放过 `scheduling.md`），并断言每份 `scheduling.md` 里出现该客户端的启动命令。校验进 CI。
- **副本在 diff 里被折叠。** 用 `.gitattributes` 把三个副本目录标记为生成代码，使 GitHub 折叠它们并排除出语言统计。
- **运行数据不搬。** `config.yaml`、`secrets.env`、`out/`、`state/` 始终在仓库根；命令形态是"在仓库根执行 skill 目录内的入口脚本"。代码跟着 skill 走、数据跟着仓库走，这条边界写进文档。
- **只用 CLI 定时。** 提供一个无人值守 wrapper，参数是 `claude` 或 `codex`；它负责加载 secrets、加并发锁、写日志、传递退出码，并调用对应的 headless 命令。DSH 不经过 wrapper（看板卡直接起会话）。云端定时任务与 GitHub Actions 不在本版。
- **文档重组。** 现有 `README.md` 整体迁为 `docs/development-log.md`（历史记录，只追加）；用户会查的两块拆成 `docs/cli.md`（命令与退出码）与 `docs/configuration.md`（配置项与默认值）；新增 `docs/README.md` 索引。根 README 在重构期只保留一段占位指向，正式内容另行编写。
- **许可证。** 新增 MIT `LICENSE`，署名 `tf1993614`；`pyproject.toml` 增加 `license` 字段。
- **词汇表。** `GLOSSARY.md` 增加 `skill` 一条（"遵循 Agent Skills 格式的目录包"）；"源目录 / 副本 / 同步"属于仓库结构，不进词汇表。
- **不再保留的旧形态**：根 `SKILL.md` 软链、根目录入口脚本薄壳、任何软链共享。
- **发布顺序。** 先建私有远端并推送当前状态，重构在私有期完成；公开仓库名为 `academic-digest`。
- **仓库外的一步**：看板卡的 Prompt 改为"加载 academic-digest skill，按它的每日运行执行"，不再出现脚本路径；若卡片已冻结则新建一张、归档旧的。这一步不在 git 里，但属于验收条件。

## Testing Decisions

- **好测试的样子**：只验证外部行为——命令行的退出码、stdout 的关键行、落盘产物的内容、目录树的逐字节一致性；不 import 内部函数、不断言私有实现。现有测试已经按这个标准写（`tests/conftest.py` 的 `cli` fixture：fresh subprocess、固定 `--now`、fixture 目录、从 `cwd` 跑）。新增测试沿用同一形态。
- **唯一的新缝**：按文档里的命令行起子进程。`cli` fixture 从 `python3 -m academic_digest` 改为调用源 skill 目录里的入口脚本，并且不再注入 `PYTHONPATH`——bootstrap 必须自己成立。
- **三组断言**：
  1. 源目录能跑：用 fixture 跑一次采集，断言候选池内容（沿用现有 `test_collect` 的断言形态）。
  2. 副本能跑：同步到临时目录 → 逐字节比较（只放过 `scheduling.md`）→ 从副本再跑一次采集，断言产物。
  3. wrapper 会派发：`PATH` 里放一个写 marker 的假 `claude` / `codex`，跑 wrapper，断言 stub 收到的参数与 wrapper 的退出码透传。
- **不新增第二份实现**：`scripts/check.sh` 调 pytest；`scripts/check-skills.sh` 调同一个测试，不重写比较逻辑。
- **不做的事**：不单元测试同步脚本的内部函数；不为三份副本各写一套测试；不 mock 文件系统。

## Out of Scope

- 新 README 的正文（章节、截图、badge、英文版）——结构落地后单独写。
- 发布元数据：仓库 description、topics、`v0.1.0` tag、GitHub Release。
- 云端定时（Claude Code 云端 scheduled tasks）与 GitHub Actions 定时工作流。
- 插件/marketplace 分发（单 skill 命名空间化，暂不做）。
- Windows 原生（PowerShell）支持；只承诺 WSL2。
- 日报写作契约、数据源、排序、推送协议的任何行为变化。
- 把 `.scratch/` 内部工单移出仓库或改路径。

## Further Notes

- 决策依据见 `docs/adr/0003-one-skill-canonical-plus-generated-client-copies.md`；调研与来源见 `docs/research/06-distribution-and-scheduling.md`。
- 验收必须包含"看板卡照常跑通"与"fresh clone 在无 secrets、无 `config.yaml` 的情况下能跑离线 fixture"两条；前者防重构打断生产，后者防"只有作者机器能跑"。
- 迁移期有一个已知的失败模式：`check-docs.py` 现在断言根 `SKILL.md` 是软链、README 链接旧路径。重构必须同时改这些断言，否则第一个提交就会红。
