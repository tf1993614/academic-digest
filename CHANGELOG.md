# Changelog

## v0.1.0 — 2026-10-24

首个公开版本。

### 新增

- 自包含的 `skills/academic-digest/` skill：`SKILL.md`、写作契约、setup 文档、五个入口脚本与 `academic_digest` 包；代码随 skill 走，入口脚本自己解析 `sys.path`。
- 三份客户端副本：`.dsh/skills/`、`.claude/skills/`、`.agents/skills/`，由 `scripts/sync-skills.sh` 生成，除 `references/scheduling.md` 外逐字节一致。
- 五个 CLI：`collect`、`fulltext`、`digest check`、`push`、`doctor`；统一退出码 `0` / `1` / `2`。
- 采集：PubMed、Europe PMC、arXiv、Research Square、可选的 bioRxiv / medRxiv 与 GitHub；跨源去重、分组配额、排序、期刊白名单。
- 日报：3 篇今日必读 + 7 篇其它速览，GitHub 新库 / 活跃库 / release 与 G6 独立成块；`digest check` 按固定契约校验。
- 全文：Europe PMC、arXiv HTML / PDF、预印本 PDF 与 Unpaywall；拿不到 OA 时明确降级为摘要。
- 推送：Server酱，标题与正文拆分、重试、`pending` 补发、空日报策略；`--dry-run` 不读 SendKey、不发送。
- 无人值守：`run-daily.sh <claude|codex>` 负责 secrets、并发锁、日志与退出码；三种调度器的可粘贴片段按客户端分别提供；DSH 走看板卡。
- 文档：`docs/cli.md`、`docs/configuration.md`、`docs/README.md` 索引；旧 README 迁为只追加的 `docs/development-log.md`。
- MIT `LICENSE`，`pyproject.toml` 的 `license` 字段。

### 说明

- 采集、全文抽取、`digest check`、`push`、`doctor` 都是确定性脚本；写 3 + 7 日报需要一个能读候选池、跑命令的模型。
- Windows 只承诺 WSL2；定时只做本机调度与 DSH 看板卡，不含云端定时或 GitHub Actions 定时。
- PDF 解析依赖 PyMuPDF（AGPL-3.0）；再分发前请自行确认许可证兼容性。
