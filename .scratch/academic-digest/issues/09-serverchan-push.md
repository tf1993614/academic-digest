# 09: Server酱 推送：分条 + pending/retry + runs

**What to build:** 把日报通过 Server酱 推到微信；超长按区块拆条；失败重试并在下次优先补发；运行结果写进 runs。

**Blocked by:** 08.

**Status:** ready-for-agent

- [ ] `push --dry-run` 输出 ServerChan payload：title ≤32 字符、markdown 正文、密钥脱敏。
- [ ] 正文 >30KB 时按区块拆成最多 2 条，带（1/2）后缀，不从论文中间截断。
- [ ] 成功条件为 HTTP 2xx + code 0；失败重试 2 次，仍失败写 pending 并以非零退出。
- [ ] pending 下次运行优先重试一次；超过 2 天丢弃并记录。
- [ ] runs 记录时间、计数、状态、错误摘要；空日报默认发送提示并退出 0，可用 `send_empty: false` 关闭。
- [ ] 测试覆盖 payload、拆分、重试、pending；真实测试推送由人工确认。

## Contract

### 新增/变更的 key

**`push` CLI**（Issue 08 的 `digest check` 之后、发送之前）

```text
push --config PATH [--fixtures DIR] [--now ISO8601] \
     --candidates PATH --selection PATH --digest PATH \
     [--state-db PATH] [--dry-run] [--out PATH]
```

- `--config` 默认 `config.yaml`；`--state-db` 默认取 `paths.state_db`。
- `--candidates/--selection/--digest` 必填，先复用 Issue 08 的校验；不合格时与
  `digest check` 一样输出 `[fail] selection:` / `[fail] digest:` 并退出 1，不发送、
  不写状态。
- `--dry-run` 只构建 payload：不联网、不读 SendKey、不写 `runs`/`pushes`/`pending`；
  payload JSON 打到 stdout，或写到 `--out`。`--out` 只能与 `--dry-run` 一起用。
  JSON 形状固定为：
  ```json
  {
    "schema_version": 1,
    "messages": [
      {"part": 1, "parts": 1, "title": "学术速递 · 2026-10-22", "desp": "…"}
    ]
  }
  ```
  拆分时 `messages` 按 part 顺序排列，`parts` 相同。空日报且 `send_empty=true`
  时输出那条提示消息；`send_empty=false` 时输出
  `{"schema_version":1,"messages":[],"skipped":"empty"}`。
- `--fixtures DIR` 回放 ServerChan 响应；第 n 次 HTTP 请求读
  `DIR/serverchan/send-<n>.json`（n 从 1 起，跨本次运行的所有消息与重试），响应形如
  `{"code":0,"message":"ok","data":{"pushid":"..."}}`。文件缺失视为传输失败。fixture
  模式不联网、不 sleep，也不需要 SendKey（不构造含 key 的 URL）。
- `--now` 固定运行时间与 pending 年龄；缺省用系统时钟。
- 退出码：`0` 已发送 / 空日报按 `send_empty` 发送或跳过 / dry-run 成功；`1` 校验
  失败、发送在重试后仍失败、拆分不可能、状态库打开/写入失败；`2` 参数、配置或
  缺失 SendKey。
- 成功时 stdout 一行：`[ok] push: sent N message(s), recorded M paper(s)`；空日报
  跳过时为 `[ok] push: skipped empty digest`；失败写 stderr `[fail] push: …`。
- live 发送前打开状态库；打不开时退出 1，不发送。dry-run 不打开状态库。

**`push` 配置**（顶层 `push`，全部可省略）

```yaml
push:
  sendkey_env: SERVERCHAN_SENDKEY
  channel: serverchan
  send_empty: true
  split_bytes: 30000
  max_bytes: 32768
  max_messages: 2
  title_max: 32
  retries: 2
  backoff_seconds: 1
  timeout: 30
  pending_days: 2
```

- `sendkey_env`：保存 SendKey 的环境变量名；live 发送前读取，空/缺失时退出 2。
  `--dry-run` 不读取它。
- `channel`：V1 只接受 `serverchan`。
- `send_empty`：候选与 GitHub/G6 都为空时是否发送空日报；默认 `true`：发送一条
  “今日没有匹配的检索条目”的提示，设 `false` 则静默。
- `split_bytes` ≤ `max_bytes`；`max_messages`、`title_max`、`timeout`、
  `pending_days` 为正整数；`retries`、`backoff_seconds` 为非负整数。
- 不新增 endpoint 配置：SendKey 以 `sctp` 开头且匹配 `^sctp(\d+)t` 时使用
  `https://<uid>.push.ft07.com/send/<key>.send`，否则使用
  `https://sctapi.ftqq.com/<key>.send`。key 与含 key 的 URL 不写日志、不写状态、
  不进 `--dry-run` 输出；错误信息必须脱敏。

**ServerChan payload**

- 每次发送 `POST` 表单字段 `title` 与 `desp`（Markdown），不带其他字段。
- `title`：`学术速递 · <candidates.date>`；拆成 n 条时在末尾加 `（i/n）`。长度按
  Unicode 字符计，超过 `title_max` 时退出 2，不截断。
- `desp`：`digest.md` 去掉标题行（首个 `# 学术速递 · …`）后的全文，换行统一为 LF。
  最后一条消息在页脚追加 `未推送数：P`（P 为本次运行开始、处理完过期 pending 后、
  发送当前日报前的 pending 行数；P=0 时省略；dry-run 省略）。
- 成功条件：HTTP 2xx 且响应 JSON 的 `code` 为整数 `0`。HTTP 失败、非 JSON、
  `code != 0` 都算失败。

**拆分**

- 按 UTF-8 字节数判断：`desp` ≤ `split_bytes` 发 1 条；超过时在顶层区块边界拆分，
  区块是 `## ` 开头的顶层 section，**不在 section/论文中间切**。
- 第 1 条带 `> 关键词…` 前言，最后 1 条带 `---` 页脚；中间 section 按顺序贪心装填，
  每条 ≤ `max_bytes`。单个 section 自身超过 `max_bytes` 时退出 1，不截断。
- 最多 `max_messages` 条；需要更多时退出 1，不发送部分日报。
- 拆分后 title 分别加 `（1/n）`…`（n/n）`，保证 ≤ `title_max`。

**`pending` 表**（新增）

```sql
CREATE TABLE pending (
    channel TEXT NOT NULL,
    digest_date TEXT NOT NULL,
    part INTEGER NOT NULL,
    parts INTEGER NOT NULL,
    title TEXT NOT NULL,
    desp TEXT NOT NULL,
    items_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (channel, digest_date, part)
);
```

- 只存**尚未发送成功**的消息；已成功的前几条不存。`part`/`parts` 从 1 起。
- `items_json` 是本次逻辑日报所有入选论文的 `[{"id":"…","topic":"…"}]`，用于整份
  日报最终成功后写 `pushes`；GitHub/G6 不写入 `pushes`（跨天 release 去重仍留给
  后续 issue）。
- 当前日报所有消息成功后写 `pushes`；失败时把失败消息及其后未发送的消息写入
  `pending`，不写 `pushes`，退出 1。

**`pushes` 写入**

- 仅在**整份逻辑日报**（含拆分后的所有消息）成功送达后写入：每篇入选论文一行
  `(item_id, topic=group, channel='serverchan', digest_date, pushed_at=now)`；
  已存在则忽略。
- 若消息已送达但 `pushes` 写入失败：退出 1、不写 `pending`（避免把已发送内容再次
  当未发送重发），并记录 failed run。

**`runs` 变更**

- 保留既有列；新增三列，默认 0，旧库用 `ALTER TABLE` 迁移并把
  `PRAGMA user_version` 升到 3：
  `selected_count INTEGER NOT NULL DEFAULT 0`、
  `pushed_count INTEGER NOT NULL DEFAULT 0`、
  `pending_count INTEGER NOT NULL DEFAULT 0`。
- 每次 live `push`（含跳过、失败）写一行：`command='push'`，`status` 为
  `ok` / `skipped_empty` / `failed`，`sources_json='{}'`，`candidate_count` 取
  `candidates.candidate_count`，`selected_count` 取 selection 论文数，
  `pushed_count` 取本次实际新增的 `pushes` 行数，`pending_count` 取运行结束后的
  `pending` 行数，`error` 为脱敏后的错误摘要。dry-run 不写 `runs`。

### 重试与 pending

- 每条消息最多尝试 `1 + retries` 次（默认 3 次），第 k 次失败后等待
  `backoff_seconds × 2^(k-1)` 秒；fixture 模式不等待。
- 当前日报某条最终失败：把该条及后续未发送的消息写入 `pending`（`created_at=now`，
  `attempts` 为已尝试次数，`last_error` 脱敏），退出 1。
- 下次 live run 在发送当前日报前：
  1. 先丢弃年龄 `> pending_days` 的行并记录摘要（按配置时区的日历日差；默认 2 天，
     D 创建、D+2 运行仍保留，D+3 丢弃）。过期行按整个
     `(channel, digest_date)` 逻辑日报一起删除，不写 `pushes`，避免把未发送的部分
     当成已完成；
  2. 取剩余 `pending` 中最早的 `digest_date`，按 `part` 顺序每条**只重试一次**
     （不再走 3 次重试循环）；成功即删行，失败则 `attempts+1`、更新
     `last_error`，仍保留；
  3. 当该 `digest_date` 的最后一行成功（该组已无 pending）时，按 `items_json`
     写 `pushes`；
  4. 处理完后继续发送当前日报。pending 重试失败不阻塞当前日报；若当前日报发送
     成功，退出 0，但在 `runs.error` 记录 pending 失败；若当前日报为空跳过且
     pending 重试也失败，退出 1，`runs.status='failed'`。
- pending 重试成功而当前日报为空跳过时，`runs.status='ok'`（本次确实发送了 pending），
  `pushed_count` 含该 pending 组写入的论文数。
- pending 重试直接发送表中保存的 `title`/`desp`，不重新排版。

### 空/缺省行为

- 空日报定义：`selection.papers` 为空且 `candidates.github` 的
  `new/active/g6/releases.starred/g6_releases` 全为空。
- 空日报且 `send_empty=false`：不发 HTTP、不写 `pending`，写
  `runs(status='skipped_empty')`，退出 0。
- 空日报且 `send_empty=true`（默认）：发送 1 条消息；`desp` 在页脚前插入
  `今日没有匹配的检索条目`（若正文有 `> 关键词…` 前言则保留），标题与正常日报相同；
  写 `runs(status='ok')`，`pushed_count=0`，退出 0。空提示发送失败时按普通失败
  处理（重试、failed run、退出 1），但**不写 pending**——第二天的“今日没有条目”
  没有再补发的意义。
- 没有 `push` 配置：全部用默认值；live 仍要求 `sendkey_env` 指向非空值。
- 没有 pending：跳过重试。`--fixtures` 未给出：走真实 HTTP。

### 旧 key 不能变

- `candidates.json`、`selection.json`、`digest.md`、Issue 08 的 `digest check`
  行为与错误前缀不变；`fulltext` 输出不变。
- `state_db` 的 `papers`、`pushes` 既有列与含义不变；`runs` 既有列不变，只新增
  上述三列。`collect` 继续用 `pushed_keys()` 排除已推送论文。
- 不新增 `paths` / `candidates` / `digest` 配置；`push` 的三个文件路径只由 CLI 给出。
- 本 issue 不扩展 `doctor` 的通道自检；真实连通性与测试推送由 Issue 10 的 setup
  流程负责。
- `未推送数` 只由 `push` 在发送内容中追加，不回写 `digest.md`，`digest check`
  不要求也不校验它。

### 测试

- 全部离线：`--fixtures` + 固定 `--now`，不 sleep、不碰网络。
- 覆盖：dry-run payload（title、markdown、无 key、空日报 `skipped`）、单条/拆分/`（1/2）`/字节上限/
  section 不截断/超过 `max_messages` 失败、HTTP 2xx+`code=0`、失败重试、
  pending 写入与下次优先重试、>2 天丢弃、`send_empty` 两种行为、`runs` 计数与
  `pushes` 记账、密钥不出现在 stdout/stderr/状态。
- 真实测试推送由人工确认；不把 SendKey 放进测试、fixture 或 Prompt。

## Comments

- 2026-10-22：按 `docs/agents/issue-tracker.md` 补 `## Contract`，钉死 push CLI、
  `push.*` 配置、ServerChan payload 与端点、拆分、pending/retry、`pushes`/`runs`
  记账与退出码。实现时以本节为准；真实测试推送仍需人工确认本地 SendKey。

- 2026-10-22：用户确认空日报也要推送：`push.send_empty` 默认改为 `true`，空日报发送
  一条“今日没有匹配的检索条目”的提示（带页脚），仍退出 0；设 `false` 才静默。
  这覆盖 spec/decision record 里“默认静默”的旧默认，spec、docs/decisions.md 与
  本 ticket 的 checklist 已同步。
