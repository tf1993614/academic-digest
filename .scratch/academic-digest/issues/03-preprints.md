# 03: 预印本：arXiv RSS + Research Square RSS + 可选 bioRxiv/medRxiv

**What to build:** 日报能纳入当天真正新公告的 arXiv 论文和 Research Square 预印本；bioRxiv/medRxiv 可按配置开启；所有预印本参与去重并打标。

**Blocked by:** 02.

**Status:** done

- [x] arXiv fixture 同时含 `new` 与 `replace` 时，只保留 `new`；lookback 至少 4 天。
- [x] Research Square RSS 的 `<abstract>`、作者、DOI 进入候选，不调用官方 API。
- [x] bioRxiv/medRxiv 默认关闭；开启后按日期区间 fixture 产出候选并本地过滤。
- [x] 预印本带来源与“预印本”标记；与其他源同一 DOI 时只保留一条。
- [x] 测试覆盖 new/replace、RS 摘要、bioRxiv 开关。

## Comments

- 2026-10-22：已实现。新增三个预印本采集路径：`arxiv` 按 `arxiv.categories` 读
  RSS，只保留 `announce_type=new`（`replace`/`cross` 与窗口外条目丢弃），作者取自
  `dc:creator`，`oa_url` 指向 PDF；API 另按配置分类与关键词回看 `lookback`
  窗口补上错过的公告批次（跳过 `updated != published`），同 ID 与 RSS 合并；
  `researchsquare` 读公开 RSS，使用
  `<abstract>`、`<authors>`、`<doi>` 并从 `created on` 解析日期，不调用官方 API；
  `biorxiv`/`medrxiv` 共用同一按日期分页的 `details` 读取器，默认关闭，开启后先按
  窗口过滤再由关键词组本地筛选。`lookback.arxiv` 在配置层强制 ≥ 4 天；启用
  arXiv 时必须给出非空 `arxiv.categories`。所有预印本保留 `is_preprint` 并在
  `tags` 中加入 `预印本`；与期刊版本或另一预印本源共用 DOI 时只保留一条，已发表
  版本的摘要与期刊优先且合并记录不再标预印本。`doctor` 同步校验新源的录制响应。
  新增 `preprints`、`preprint-dedupe`、`preprint-no-abstract` fixture 与 `arxiv-lookback`、
  `arxiv-no-categories` 坏配置，覆盖 new/replace/cross、lookback、RS 摘要/作者/
  DOI、bioRxiv/medRxiv 开关与同 DOI 合并。验收：`python3 -m pytest`
  （34 passed，全部经 CLI 子进程、离线、固定 `--now`）；`mypy` / `pyflakes` 无问题。
