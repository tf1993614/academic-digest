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

- 2026-10-23：README 用 `git mv` 迁到 `docs/development-log.md`，只改了标题、文件头历史
  记录说明，以及仓库根相对链接的前缀（`docs/decisions.md` 改成同目录的 `decisions.md`）；
  其余正文逐行保留，旧链接仍可点开。`docs/cli.md` 由原 `## 命令` 整段抽出（collect /
  fulltext / digest check / push / doctor 与退出码表，含候选池与日报契约），只把命令标题
  升到 `##` 并加通用约定；`docs/configuration.md` 重写成默认值表 + 分节说明。`docs/README.md`
  按“使用 / 每日运行与定时 / 设计 / 维护”索引；根 README 收成 5 行：一句项目说明 +
  文档入口（命令、配置两个链接），不再重复 LICENSE 或命令块。
- 与票面的有意偏差：票面要求把 README 断言“迁到开发记录上”，但开发记录的约束是“只追加、
  不再维护当前用法”。把 `Paper.to_dict` 键序、retry 常量、canonical skill 路径钉在历史文件
  上，会让下一次 payload/retry 变更必须先改历史，二者不可兼得。最终把当前契约断言放在
  `docs/cli.md`（候选池 sample、retry 文案）与 `docs/README.md`（canonical skill 路径），
  开发记录只由布局检查（存在且被索引）与全量相对链接检查覆盖；历史 sample 保持冻结。
- `check-docs.py` 的断言仍覆盖票面要求的文件与许可证，但当前文档一侧改为从代码推导，
  不再是两份手写清单互证：CLI 命令的 flags 来自各入口脚本的 `--help`，退出码来自
  `cli.py` 的 `EXIT_*` 常量，`configuration.md` 的顶层键来自 `config.py` 的
  `_TOP_LEVEL_KEYS`、默认值逐条对 `DEFAULT_*` 常量，候选池键序对 `Paper.to_dict`，
  retry 文案对 `base.py` 的 `_HTTP_ATTEMPTS` / `_HTTP_BACKOFF_SECONDS`；另外检查根 README
  ≤ 30 行且无代码块、指向 docs 索引、三个 docs 文件存在且被索引、`LICENSE` 与
  `pyproject.toml` 的 MIT 字段、`docs/` 下所有 Markdown 相对链接可解析。
- `LICENSE` 用 MIT 原文，版权行 `Copyright (c) 2026 tf1993614`；`pyproject.toml` 用
  `license = {text = "MIT"}`（与 `setuptools>=68` 兼容）。`AGENTS.md`、
  `CODING_STANDARDS.md`、`docs/agents/code-review.md` 里让 reviewer grep `README.md` 的
  指令改为 `docs/cli.md` + `docs/configuration.md`，并写明开发记录只追加——这三处是搬迁
  直接导致的失效引用，不更新会把 reviewer 指向错误位置。
- `scripts/check.sh` 绿（mypy、pyflakes、check-docs、pytest）。
