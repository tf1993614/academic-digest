# 08: 发布准备：正式 README、元数据与 v0.1.0

**What to build:** 把根目录的占位 README 换成面向访客的正式 README；补齐 `CHANGELOG.md`、仓库 description/topics、`v0.1.0` tag 与 GitHub Release；公开前做 secret 扫描与 HTTPS fresh clone 复核。这是 oss-release spec 的 Out of Scope 收尾，不改产品行为。

**Blocked by:** 06（已 done）。07（Claude Code 实测）不阻塞本票。

**Status:** ready-for-human

- [x] 正式 `README.md`：首屏说清“是什么、给谁、离线怎么跑”，完整命令/配置链到 `docs/`，不再复制开发记录。
- [x] `CHANGELOG.md` 的 `v0.1.0` 条目。
- [x] 仓库 description 与 topics。
- [x] `README.md` 与 `references/scheduling/dsh.md` 明确 DSH 看板卡依赖 dsh-web 的 task-board 插件，并给出安装命令。
- [x] `v0.1.0` annotated tag + GitHub Release；tag 打在 README/CHANGELOG 已通过 CI 的提交上。
- [x] 公开前：历史 secret 扫描、`git check-ignore`、无 SSH key 的 HTTPS fresh clone 四步复核。
- [ ] 仓库公开（需人工确认；`gh repo edit --visibility public` 前的最后一步）。

## Notes

- README 大纲来自 `.scratch/research/06c-readme.md`，但三处已过时：仓库已自带三份客户端副本（不再需要软链才能用）、已有 `run-daily.sh`、已有 LICENSE 与 ADR 0003。
- 这是发布收尾，不是新功能；不新增运行时行为。CI 必须绿，尤其是 GitHub 上更新的依赖 stub 下的 mypy。
- ticket 04 的“短占位、无代码块”检查随正式 README 一起退役，改为“链接 docs 索引且不退回开发记录”。
- 公开是不可逆动作，最后一步必须由用户明确确认；tag/Release 可先在私有期完成。

## Comments

- 2026-10-24：06 已收尾（私有远端、fresh clone、Codex/DSH 发现、生成标记）；07 只差 Claude 账号恢复。CI 在首次 GitHub 运行时暴露了 bs4 新 stub 下的 mypy 错误，已用 `1e947d3` 修复并通过 CI。现在开始 README + CHANGELOG + 元数据。

- 2026-10-24：第 1+2 步完成。`README.md` 重写为面向访客的版本（首屏定义、一期样例、5 分钟离线 quickstart、三客户端落点、配置/定时/命令/失败/安全/FAQ/许可），`CHANGELOG.md` 增加 `v0.1.0`。仓库 description 已设为英文一句话；topics 设为 `academic`、`literature`、`pubmed`、`europepmc`、`arxiv`、`research-square`、`github`、`wechat`、`serverchan`、`agent-skills`、`claude-code`、`codex`、`deepseek-harness`、`daily-digest`。`check-docs.py` 的“短占位/无代码块”断言随正式 README 退役，改为“链接 docs 索引、链接 LICENSE、不退回开发记录”；`CODING_STANDARDS.md` 同步。`scripts/check.sh` 绿。
- 待办：用户 review README 后打 `v0.1.0` tag + GitHub Release；公开前再做一次 secret 扫描与 HTTPS fresh clone 复核，最后公开仓库需明确确认。

- 2026-10-24：用户指出 DSH 原生不带定时任务，看板卡/`task_board_*`/cron 来自 dsh-web 的 task-board 插件。已补：README 的客户端表与「每天定时跑」写明 `@linxin666/dsh-client-ui-task-board`（或 `@linxin666/dsh-web-all`）的安装命令与重启步骤；`references/scheduling/dsh.md` 增加「前置：DSH Web 任务看板插件」并修正“DSH 没有 headless CLI”的旧表述；`tests/test_skill_copies.py` 增加断言防止再丢；`check-docs.py` 断言 README 必须提到插件。研究文档 `05`、`06` 加补注。

- 2026-10-24：按用户要求在 README 增加 `## Star History`，使用 star-history.com 的
  `tf1993614/academic-digest` Date 图表。私有期图表可能没有数据，公开后自动填充。

- 2026-10-24：`v0.1.0` annotated tag 打在 `74c4c99`（README 定稿、CI run `40096827296` 绿），tag 已推送；GitHub Release 已创建：<https://github.com/tf1993614/academic-digest/releases/tag/v0.1.0>（`isDraft: false`、`isPrerelease: false`，notes 用 `out/release-notes-v0.1.0.md`）。
- 公开前复核：HEAD 无 `secrets.env` / 根 `config.yaml`；`ghp_` / `github_pat_` / `sctp…` / 私钥模式扫描为空；`git check-ignore` 命中 `config.yaml`、`secrets.env`、`state/`、`out/`。用 token 走 HTTPS（不带 SSH key）clone `v0.1.0`，无 `config.yaml` / `secrets.env` 时四步全绿，三个扫描根都有 skill。真正“无任何凭据”的 HTTPS clone 要等公开后再跑一次。
- 待办：仓库公开（需用户明确确认），然后跑无凭据 HTTPS clone 与 release 页面/README 渲染检查。Claude Code 实测仍由 07 跟踪，不阻塞发布。
