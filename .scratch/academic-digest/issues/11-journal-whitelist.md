# 11: 期刊白名单：配置 + PubMed/Europe PMC JOURNAL 过滤 + 加分

**What to build:** 用户给出期刊名单后，用 `journal_filter` 配置把采集限定在白名单期刊，并在候选池排序里给白名单期刊加分；不给名单时保持当前的“不限期刊”。

**Blocked by:** 04.

**Status:** needs-info

- [ ] 配置新增 `journal_filter`（期刊名列表，默认空 = 不限），并在 doctor 中展示。
- [ ] PubMed / Europe PMC 查询用 `JOURNAL` 过滤，不抓期刊官网。
- [ ] 候选池排序对白名单期刊加分，且 README、ADR 与测试同步覆盖。
- [ ] 名单由用户提供；未提供前保持不限期刊，不影响 3+7 的入选逻辑。

## Comments

- 2026-10-22：Spec §Implementation Decisions 提到“期刊白名单加分”，但已确认决定 §6
  是“默认不限期刊；要限定再给名单”。Issue 04 只实现相关性 + 新鲜度排序与分组配额，
  因此把白名单的配置、过滤与加分留在这里跟踪；需要用户先给出期刊名单。
