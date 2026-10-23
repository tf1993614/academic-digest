# 01: 源 skill 目录与三份客户端副本

**What to build:** 克隆仓库后，Claude Code 的 `/academic-digest` 与 Codex 的 `/skills` 里都能看到并调用这个 skill（在仓库根可跑通），而 DSH 看板卡的行为不变。同时把"三家各写各的定时方案"落成三份独立文件——这是本次重构的地基。

**Blocked by:** None (can start immediately).

**Status:** done

- [x] 源 skill 目录 `skills/academic-digest/` 存在，含 `SKILL.md`、`references/{digest,setup}.md`、`references/scheduling/{dsh,claude,codex}.md`；`setup.md` 不再包含建卡步骤，改为指向 `references/scheduling.md`。
- [x] 同步脚本生成 `.dsh/skills/`、`.claude/skills/`、`.agents/skills/` 三份副本；校验脚本逐字节比较、只放过 `references/scheduling.md`，并断言每份里出现该客户端的启动命令。
- [x] 根 `SKILL.md` 软链已删除；`.gitattributes` 把三个副本目录标为生成代码。
- [x] `check-docs.py` 指向新路径且不再断言根软链；`GLOSSARY.md` 增加 `skill` 词条；`AGENTS.md` 改用 canonical 措辞。
- [x] `scripts/check.sh` 绿；DSH catalog 仍能发现 skill；看板卡手动跑一次通过。

## Notes

- 决策依据：ADR 0003。spec：`../spec.md`。
- 中间态是刻意的：代码仍在仓库根，所以副本"能被发现、但只能在仓库根运行"；自包含由 02 兑现。不要在本票里顺手搬代码。
- 生成的副本禁止手改；任何差异都应回到源目录改、再跑同步。

## Comments

- 2026-10-23：`scripts/check.sh` 通过；DSH catalog 重新发现 `academic-digest`（新 description）。
  生产卡手动执行 `7fbcc765-8698-4c0a-b99a-80412e8434be` 成功，`runs` 记录 push/ok；三份副本
  由 `scripts/sync-skills.sh` 生成，`tests/test_skill_copies.py` 逐字节校验（含各客户端
  `references/scheduling.md` 与禁止软链）。
