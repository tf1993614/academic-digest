# 07: Claude Code 客户端实测

**What to build:** Claude Code 登录恢复后，在 fresh clone 里确认 `/academic-digest` 能被发现并触发；记录账号恢复日期与 Claude Code 版本，作为 06 三客户端验收的收尾。

**Blocked by:** None（私有远端与 fresh clone 已就绪，只等账号）。

**Status:** ready-for-human

- [ ] `claude` 登录后，在 fresh clone 里用 `claude -p "List the names of the skills available in this project. Output only the names." --permission-mode plan` 能看到 `academic-digest`；交互会话里 `/academic-digest` 可触发。
- [ ] 记录账号恢复日期与 `claude --version`。
- [ ] 若未加载：检查 `.claude/skills/academic-digest/SKILL.md` 的 frontmatter 与 `skills/academic-digest/SKILL.md` 是否一致；改源目录后跑 `scripts/sync-skills.sh`，不要手改副本。

## Notes

- 这是 06 第 3 项拆出的客户端实测。仓库结构已由 06 验证：clone 里 `.claude/skills/academic-digest/SKILL.md` 存在，三份副本逐字节一致，Codex 已发现同一份。
- 阻塞原因是个人 Claude 账号过期（`OAuth token revoked`），不是 skill 结构问题；不要为了这个把 06 的其余验收挂住。
- headless 测试用 `claude -p`，不要加 `--bare`；若用长期 token，先 `claude setup-token` 再导出 `CLAUDE_CODE_OAUTH_TOKEN`。
- 本机 `claude doctor` 正常（Claude Code 2.1.292），说明是账号侧不是安装侧。

## Comments

- 2026-10-24：06 收尾时 `claude -p` 返回 `Failed to authenticate: OAuth token revoked`，交互登录也不可用。为避免账号续费阻塞发布，把 Claude 实测从 06 拆到本票。06 的 Codex 实测与 DSH 结构验证已完成；fresh clone 在 `out/fresh-clone`（gitignored、无 `config.yaml` / `secrets.env`），四步验收再次通过。
