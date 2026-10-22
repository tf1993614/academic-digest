# 09: Server酱 推送：分条 + pending/retry + runs

**What to build:** 把日报通过 Server酱 推到微信；超长按区块拆条；失败重试并在下次优先补发；运行结果写进 runs。

**Blocked by:** 08.

**Status:** ready-for-agent

- [ ] `push --dry-run` 输出 ServerChan payload：title ≤32 字符、markdown 正文、密钥脱敏。
- [ ] 正文 >30KB 时按区块拆成最多 2 条，带（1/2）后缀，不从论文中间截断。
- [ ] 成功条件为 HTTP 2xx + code 0；失败重试 2 次，仍失败写 pending 并以非零退出。
- [ ] pending 下次运行优先重试一次；超过 2 天丢弃并记录。
- [ ] runs 记录时间、计数、状态、错误摘要；无新内容不发且退出 0。
- [ ] 测试覆盖 payload、拆分、重试、pending；真实测试推送由人工确认。
