# 文档

自动学术速递的文档入口。访客先读仓库根的 [README](../README.md)；这里按“要做什么”索引。

## 使用

- [命令参考](cli.md)：五个入口命令、参数、产物与退出码。
- [配置参考](configuration.md)：配置项、默认值与校验规则。
- [术语表](../GLOSSARY.md)：日报、候选池、skill 等领域词汇。
- [已确认的需求与决定](decisions.md)：关键词、分组配额、推送与失败策略的原始决定。

## 每日运行与定时

- [SKILL.md](../skills/academic-digest/SKILL.md)：agent 的每日三步入口。
- [写作契约](../skills/academic-digest/references/digest.md)：selection 与 `digest.md` 的格式。
- [setup](../skills/academic-digest/references/setup.md)：secrets、`config.yaml` 与首次自检。
- 客户端定时方案在源 skill 的 `references/scheduling/` 下：
  [DSH](../skills/academic-digest/references/scheduling/dsh.md)、
  [Claude Code](../skills/academic-digest/references/scheduling/claude.md)、
  [Codex](../skills/academic-digest/references/scheduling/codex.md)。
  生成副本里的 `references/scheduling.md` 由 `scripts/sync-skills.sh` 写入。

## 设计

- [ADR 0001：文献源策略](adr/0001-literature-source-strategy.md)
- [ADR 0002：GitHub 仓库发现](adr/0002-github-repository-discovery.md)
- [ADR 0003：一个源 skill + 三份生成副本](adr/0003-one-skill-canonical-plus-generated-client-copies.md)
- [调研综合](research/00-synthesis.md)（其余分主题报告在同目录）

## 维护

- [开发记录](development-log.md)：重构前的仓库 README，只追加的历史记录。
- [代码审查](agents/code-review.md)：冻结补丁与两轴评审的流程。
- [Issue tracker](agents/issue-tracker.md)：`.scratch/` 下的工单约定。
- [领域文档](agents/domain.md)：单上下文、词汇表与 ADR 的位置。
- [Triage labels](agents/triage-labels.md)：工单状态标签。
- [编码规范](../CODING_STANDARDS.md)：测试、文档与实现的约定。
- [协作说明](../AGENTS.md)：并行 worktree 与 skill 目录规则。
