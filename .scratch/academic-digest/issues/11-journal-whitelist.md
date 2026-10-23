# 11: 期刊白名单：配置 + PubMed/Europe PMC JOURNAL 过滤 + 加分

**What to build:** 用户给出期刊名单后，用 `journal_filter` 配置把采集限定在白名单期刊，并在候选池排序里给白名单期刊加分；不给名单时保持当前的“不限期刊”。

**Blocked by:** 04.

**Status:** done

- [x] 配置新增 `journal_filter`（期刊名列表，默认空 = 不限），并在 doctor 中展示。
- [x] PubMed / Europe PMC 查询用 `JOURNAL` 过滤，不抓期刊官网。
- [x] 候选池排序对白名单期刊加分，且 README、ADR 与测试同步覆盖。
- [x] 名单由用户提供；未提供前保持不限期刊，不影响 3+7 的入选逻辑。

## Contract

- 配置新增顶层 `journal_filter`：完整期刊名列表，默认省略或 `[]` = 不限期刊。
- 候选池 `papers[]` 新增 `journal_match: bool`，位置在 `is_preprint` 之后；仅当
  `journal_filter` 非空且该论文 `venue` 与名单名称大小写不敏感地完整匹配时为 `true`，
  否则为 `false`。
- 命中时 `score` 在现有相关性 + 新鲜度之上额外 +2；`relevance`、`score` 在名单为空
  时的含义与数值完全不变。其余候选键、来源区块与 GitHub/G6 区块不变。
- 未配置或空名单时：PubMed / Europe PMC 查询语义不变，`journal_match` 均为 `false`，
  不影响候选池排序和 3 + 7 入选。
- 非空名单只改 PubMed 的 `[Journal]` 与 Europe PMC 的 `JOURNAL:` 查询子句，不抓取
  期刊官网，也不改变 arXiv、Research Square、bioRxiv/medRxiv 或 GitHub 的查询。

## Comments

- 2026-10-22：Spec §Implementation Decisions 提到“期刊白名单加分”，但已确认决定 §6
  是“默认不限期刊；要限定再给名单”。Issue 04 只实现相关性 + 新鲜度排序与分组配额，
  因此把白名单的配置、过滤与加分留在这里跟踪；需要用户先给出期刊名单。
- 2026-10-23：实现 `journal_filter`（空 = 不限）、PubMed `[Journal]` / Europe PMC
  `JOURNAL:` 过滤、白名单候选 +2 分与 `journal_match` 标记，doctor 展示当前名单；
  README、`config.example.yaml`、ADR、decisions 与 setup 访谈同步。白名单参考
  [Nature Index 期刊列表](https://www.nature.com/nature-index/faq)，但按用户要求
  **未写入 `config.yaml`**：当前 `journal_filter` 仍为空，行为与默认“不限期刊”一致。
