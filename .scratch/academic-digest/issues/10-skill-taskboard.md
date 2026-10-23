# 10: Skill + 任务看板卡 + 端到端

**What to build:** 研究者通过 skill 的 setup 流程完成配置、doctor、dry-run 和测试推送，创建每天 08:00 的任务卡；从看板手动触发一次，微信收到真实日报。

**Blocked by:** 09.

**Status:** done

- [x] SKILL.md 的 setup 流程能写出配置、跑 doctor、跑 dry-run、发测试推送、创建任务卡与 cron。
- [x] 任务卡固定本仓库工作区与 workspace-write 权限；Prompt 明确加载 skill 与三步流程；不启用验收裁判。
- [x] 从看板手动运行一次，微信收到真实日报，看板执行历史显示成功。
- [x] 模拟发送失败时任务卡显示失败；下次运行优先重试 pending。
- [x] skill 在项目级 skills 根目录可发现，并可通过用户级软链在任意工作区使用。
- [x] 手工验收：日报 3+7、G6 独立区块、页脚源状态齐全。

## Comments

- 2026-10-22：实现完成。项目级 skill 在 `.dsh/skills/academic-digest/`，setup 在
  `references/setup.md`，日报契约在 `references/digest.md`；`scripts/setup-secrets.sh`
  向导写本地 `secrets.env`（600、gitignored），`config.example.yaml` 已是六组
  G1–G6 + GitHub 默认开。`doctor` 联网全绿；`push --dry-run` 用 fixture 产出
  `学术速递 · 2026-10-22` 单条消息且不含密钥；真实 fixture 测试推送成功。
  skill 的定位仓库改为 `git -C <base> rev-parse --show-toplevel`，从用户级软链
  `~/.dsh/skills/academic-digest` 或任意工作区都能解析回本仓库；collect 的提示补了
  “后台等待、部分源失败不要重跑”。

- 2026-10-22：生产卡 `每日学术速递` 为 `7dfb1e87-0c59-45a5-9028-08478950719a`，
  工作区 `8b8d83b0-a769-481a-9ddb-648dc9593014`（本仓库），权限
  `workspace-write`，`goalRun: true` + `skipVerification: true`，cron
  `0 8 * * *`、Host 时区 `Asia/Shanghai`。Prompt 明确加载 academic-digest skill、
  collect → 写日报（含 fulltext 与 digest check）→ push，只有 push 退出 0 才视为
  完成；旧卡 `00a737bf…` 三次因模型 transport 失败，已归档。

- 2026-10-22/23：看板端到端已跑通。手动执行 `ae0a2bb7…`（23:43–23:59）与
  08:00 定时执行 `0987fca0…`（2026-10-23 08:00–08:12）均为 succeeded；
  `runs` 里对应 `push` 行 `status=ok`、`selected_count=10`、`pushed_count=10`、
  `pending_count=0`，stdout 为 `[ok] push: sent 1 message(s), recorded 10 paper(s)`。
  08:00 日报经 `digest check`：3 篇今日必读 + 7 篇其它速览；GitHub 含新项目/活跃项目/
  关注 release，`## AI 工具 / Agent Harness` 独立；页脚覆盖 pubmed/europepmc/
  arxiv/researchsquare/github 五个源（arxiv failed 照实写）、候选 26、入选 10。
  推送成功不等于微信一定收到，最终仍需用户在微信确认当天消息。

- 2026-10-23：发送失败与 pending 补发演练。失败卡 `a1efde30…` 用
  `SERVERCHAN_SENDKEY=INVALID_KEY_FOR_DRILL` 对 fixture 日报执行 push，退出 1、
  `[fail] push: message 1/1: HTTP 400`，pending 新增一行；本机部署没有打开全局
  `/goal`，`goalRun` 被忽略，卡片按普通回合结算，因此按 setup.md 的兜底用
  `task_board_manage(action: "record-external-outcome", result: "failed")` 把这次
  演练记为 failed。补发卡 `b3bf0784…` 用同一工作区内的
  `out/.board-drill.sqlite3`（gitignored）预置 pending，再用真实 SendKey 跑同一条
  push，stdout 为 `[ok] push: sent 2 message(s), recorded 10 paper(s)`，pending
  归零、卡片 succeeded；证明下一次运行会先补发 pending。两张演练卡均带“演练”标签，
  可随时归档。

- 2026-10-23：端到端期间观察到代理/TLS 偶发 `SSLEOFError` 与 arXiv 读超时，给
  live GET 增加了 3 次尝试（2 次重试，1s/2s 退避）的传输层重试；读超时与 4xx 立即
  失败，避免慢主机把采集拖到十分钟。测试在 `tests/test_source_http.py`，ADR
  0001 已补 Issue 10 amendment；失败源仍按契约写进页脚，不阻断其它源与推送。

- 2026-10-23：code review 后收紧文档与测试：retry 文案改为“3 次尝试（2 次重试）”，
  `CODING_STANDARDS` 的 Tests 规则同时列入 `test_source_http.py`，setup 的配额表改为
  “G2 ≤ 4，G6 2，其它 6”，配置校验与失败演练都先加载/覆盖 secrets；backoff 与
  读超时不重试补了测试。spec.md 恢复原状（不再改写验收标准），Issue 10 的偏离只留在
  `docs/decisions.md` 与 ADR amendment。

- 2026-10-23：已知缺口（不在本票清单内）：(1) `last_success` 动态补窗未实现，当前
  按各源固定 lookback（默认 2–4 天）补窗，README/ADR 已如实标注；(2) 本机 Host 未开
  全局 `/goal`，`goalRun` 被忽略，发送失败靠 `record-external-outcome` 记录；
  (3) `config.example.yaml` 的 G5/G4 泛词是否按 `docs/decisions.md` §2.4 加生物锚点，
  属于用户关键词配置，待用户决定，不擅自改；(4) `未推送数` 按 Issue 09 契约只在
  pending>0 时由 `push` 追加，pending=0 时省略，spec 的页脚列表与 Issue 09 契约
  措辞不同，属契约层差异，本票不改。

- 2026-10-23：第二轮审查后再修：setup 增加逐项访谈问题、把失败演练改成真实的两张
  临时演练卡（状态库放工作区内的 `out/.board-drill.sqlite3`，不再假设生产卡会失败），
  429 重试至少等 2s 以尊重 GitHub 30 次/分钟节奏，读超时与其它 4xx 不重试，
  `base._sleep` 作为测试 seam，`setup-secrets.sh` 收尾文案与 `config.example.yaml`
  的 GitHub token 注释同步；`tests/test_source_http.py` 覆盖 backoff、429 等待、
  读超时与意外错误。
