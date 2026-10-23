# 02: 代码进 skill，副本变成自包含

**What to build:** 把某个副本目录整体拷进客户端扫描根（或把仓库 clone 到任意目录）之后，在任意工作目录都能跑通每日三步，不需要先 `pip install`。这是"整目录可拷走"从口号变成事实的一票。

**Blocked by:** 01.

**Status:** ready-for-agent

- [ ] 四个入口脚本、`setup-secrets.sh`、`academic_digest` 包都位于源 skill 目录内；每个入口脚本自行把所在 skill 目录加入 `sys.path`，不依赖 `PYTHONPATH`。
- [ ] 干净 venv（不 install）能跑通离线 fixture 采集；`pip install -e ".[dev]"` 与 `academic-digest` 命令行入口仍然可用。
- [ ] 测试的 `cli` 缝改为调用源 skill 目录里的入口脚本，不再用 `-m`、不再注入 `PYTHONPATH`——bootstrap 必须自己成立。
- [ ] 用 `.claude` 副本（不是源目录）跑一次采集，产物与断言通过。
- [ ] 重跑同步后三份副本一致；`check-docs.py` 里指向源码的常量更新到新位置；`scripts/check.sh` 绿。

## Notes

- 决策依据：ADR 0003（代码随 skill 走、运行数据留在仓库根）。
- 运行数据（`config.yaml`、`secrets.env`、`out/`、`state/`）**不要**搬进 skill 目录。
- 每个入口脚本的 bootstrap 写成 `sys.path.insert(0, Path(__file__).resolve().parents[1])` 一类的自解析，不要硬编码绝对路径。
