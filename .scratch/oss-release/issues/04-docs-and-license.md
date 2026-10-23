# 04: 文档重组与许可证

**What to build:** 访客第一屏不再是一份 969 行的开发流水账，而是一段短说明指向 `docs/`；现有用户能在 `docs/` 里查到完整命令与配置；仓库有可用的 MIT 许可证。

**Blocked by:** 03.

**Status:** done

- [x] 现有 `README.md` 整体迁为 `docs/development-log.md`，作为只追加的历史记录，不再承载"当前用法"。
- [x] `docs/cli.md`（命令、参数、退出码）与 `docs/configuration.md`（配置项与默认值）存在，且被 `docs/README.md` 索引链接。
- [x] 根 `README.md` 是短占位，指向 `docs/`；不复制两份内容。
- [x] 新增 MIT `LICENSE`（署名 `tf1993614`），`pyproject.toml` 增加 `license` 字段。
- [x] `check-docs.py` 的 README 断言迁到开发记录上；文档内相对链接全部可点开；`scripts/check.sh` 绿。

## Notes

- 只拆用户真会查的两块（命令、配置）；测试 fixture 与状态库 schema 留在开发记录里。
- 新 README 的正文（章节、截图、双语）不在本票范围，见 spec 的 Out of Scope。

## Comments

- 2026-10-23：README 用 `git mv` 迁到 `docs/development-log.md`，只改了两处：标题与文件头
  历史记录说明；所有仓库根相对链接加了 `../`（`docs/decisions.md` 改成同目录的
  `decisions.md`），其余正文逐行保留，旧链接仍可点开。`docs/cli.md` 由原 `## 命令` 整段
  抽出（collect / fulltext / digest check / push / doctor 与退出码表，含候选池与日报契约），
  只把命令标题升到 `##` 并加通用约定；`docs/configuration.md` 重写成默认值表 + 分节说明，
  新增的默认值逐条对 `config.py` 的 `DEFAULT_*` 常量做机械校验。`docs/README.md` 按
  “使用 / 每日运行与定时 / 设计 / 维护”索引；根 README 只留一段说明和三个链接。
- `check-docs.py` 的断言拆成：布局（根 README ≤ 30 行、无代码块、指向 docs 索引；三个
  docs 文件存在且被索引）、MIT `LICENSE` 与 `pyproject` 的 `license = MIT`、`cli.md` 覆盖
  五个命令与退出码 0/1/2、`configuration.md` 覆盖全部顶层配置键与默认值表、`docs/` 下所有
  Markdown 相对链接可解析。原 README 的候选池 sample 与 retry 文案断言迁到开发记录；
  候选池 sample 同时在 `cli.md` 校验，因为它现在是用户侧契约。开发记录的历史 sample 与
  当前代码不一致时仍会红——这是按票面“断言迁到开发记录”执行的有意取舍。
- `LICENSE` 用 MIT 原文，版权行 `Copyright (c) 2026 tf1993614`；`pyproject.toml` 用
  `license = {text = "MIT"}`（与 `setuptools>=68` 兼容）。`AGENTS.md`、
  `CODING_STANDARDS.md`、`docs/agents/code-review.md` 里让 reviewer grep `README.md` 的
  指令改为 `docs/cli.md` + `docs/configuration.md`，并写明开发记录只追加。
- `scripts/check.sh` 绿（mypy、pyflakes、check-docs、253 个 pytest）。
