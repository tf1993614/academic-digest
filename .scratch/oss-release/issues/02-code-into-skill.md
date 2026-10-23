# 02: 代码进 skill，副本变成自包含

**What to build:** 把某个副本目录整体拷进客户端扫描根（或把仓库 clone 到任意目录）之后，在任意工作目录都能跑通每日三步，不需要先 `pip install`。这是"整目录可拷走"从口号变成事实的一票。

**Blocked by:** 01.

**Status:** done

- [x] 四个入口脚本、`setup-secrets.sh`、`academic_digest` 包都位于源 skill 目录内；每个入口脚本自行把所在 skill 目录加入 `sys.path`，不依赖 `PYTHONPATH`。
- [x] 干净 venv（不 install）能跑通离线 fixture 采集；`pip install -e ".[dev]"` 与 `academic-digest` 命令行入口仍然可用。
- [x] 测试的 `cli` 缝改为调用源 skill 目录里的入口脚本，不再用 `-m`、不再注入 `PYTHONPATH`——bootstrap 必须自己成立。
- [x] 用 `.claude` 副本（不是源目录）跑一次采集，产物与断言通过。
- [x] 重跑同步后三份副本一致；`check-docs.py` 里指向源码的常量更新到新位置；`scripts/check.sh` 绿。

## Notes

- 决策依据：ADR 0003（代码随 skill 走、运行数据留在仓库根）。
- 运行数据（`config.yaml`、`secrets.env`、`out/`、`state/`）**不要**搬进 skill 目录。
- 每个入口脚本的 bootstrap 写成 `sys.path.insert(0, Path(__file__).resolve().parents[1])` 一类的自解析，不要硬编码绝对路径。

## Comments

- 2026-10-23：代码搬进 `skills/academic-digest/`（五个入口脚本 + `setup-secrets.sh` +
  `academic_digest/`）。入口脚本的 `sys.path` bootstrap 指向 skill 根，因此 `pip install`
  不再是运行前提；`setup-secrets.sh` 与 SKILL.md 用 `git -C <skill>` 找仓库根，运行数据
  仍留在该仓库根（skill 拷进另一个仓库时就是那个仓库），不在仓库里就明确失败、不把数据
  写到当前目录；fixture 缺失时跳过可选的真实测试推送。pyproject 改为
  `package-dir = {"" = "skills/academic-digest"}`，editable 安装与 `academic-digest`
  命令行的导入目标都落在 skill 内。
- `tests/conftest.py` 的 `cli` 缝改成直接跑 skill 里的入口脚本，清掉 `PYTHONPATH`；
  `tests/test_skill_copies.py` 覆盖两件事：同步结果生成到临时目录后，三份副本（含
  `.claude`）都在仓库外跑一次离线采集并断言候选池；用 `PYTHONPATH` 放一个会抛错的假
  `academic_digest`，证明每个入口脚本都先加载自己的包。`_tree` 忽略运行时缓存
  （`__pycache__`/`.pyc`/`*.egg-info`/`.pytest_cache`），与 `sync-skills.sh` 的排除项
  保持一致，否则跑过副本后 `check-skills.sh` 会误报漂移。CI 增加
  `academic-digest --version` 与一次离线 `academic-digest collect`，守住 pyproject 映射
  与命令行入口。
- 验收：干净 venv（只装依赖、不装本项目，`import academic_digest` 失败）从 `/` 跑通
  `collect`；`pip install -e ".[dev]"` 后 `academic-digest --version` 与
  `academic-digest collect` 正常；`.claude` 副本从 `/` 跑出的候选池与源目录一致；
  `scripts/sync-skills.sh` 重生成三份副本后 `scripts/check.sh` 绿。
- 验收：干净 venv（只装依赖、不装本项目，`import academic_digest` 失败）从 `/` 跑通
  `collect`；`pip install -e ".[dev]"` 后 `academic-digest --version` 与
  `academic-digest collect` 正常；`.claude` 副本从 `/` 跑出的候选池与源目录一致；
  `scripts/sync-skills.sh` 重生成三份副本后 `scripts/check.sh` 绿。
