# 04: 文档重组与许可证

**What to build:** 访客第一屏不再是一份 969 行的开发流水账，而是一段短说明指向 `docs/`；现有用户能在 `docs/` 里查到完整命令与配置；仓库有可用的 MIT 许可证。

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] 现有 `README.md` 整体迁为 `docs/development-log.md`，作为只追加的历史记录，不再承载"当前用法"。
- [ ] `docs/cli.md`（命令、参数、退出码）与 `docs/configuration.md`（配置项与默认值）存在，且被 `docs/README.md` 索引链接。
- [ ] 根 `README.md` 是短占位，指向 `docs/`；不复制两份内容。
- [ ] 新增 MIT `LICENSE`（署名 `tf1993614`），`pyproject.toml` 增加 `license` 字段。
- [ ] `check-docs.py` 的 README 断言迁到开发记录上；文档内相对链接全部可点开；`scripts/check.sh` 绿。

## Notes

- 只拆用户真会查的两块（命令、配置）；测试 fixture 与状态库 schema 留在开发记录里。
- 新 README 的正文（章节、截图、双语）不在本票范围，见 spec 的 Out of Scope。
