# 06: 私有远端与 fresh clone 验收

**What to build:** 在一个干净目录 clone 之后，没有 secrets、没有 `config.yaml` 也能跑通离线 fixture 四步；三家客户端都能在 clone 出来的树上发现 skill。这是发布前最后一道门。

**Blocked by:** 04.

**Status:** ready-for-agent

- [ ] 私有远端建立并推送当前历史；公开仓库名定为 `academic-digest`（只影响远端名，本地目录不改）。
- [ ] 在干净目录 clone 后跑通四步：doctor 自检 → fixture 采集 → 日报校验 → `push --dry-run`。
- [ ] `claude`、`codex`、DSH 三处各发现一次 skill（Claude Code 能 `/academic-digest`，Codex `/skills` 可见，DSH catalog 可见）。
- [ ] 副本在 GitHub 的 diff 中默认折叠（`.gitattributes` 的生成标记生效），语言统计不被三份副本翻倍。

## Notes

- 这一票才能回答"别人装得上吗"；在它之前，所有验证都发生在你自己的机器上。
- clone 验收时不要带 `secrets.env`；离线 fixture 的存在就是为了这一步。
