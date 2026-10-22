# 10: Skill + 任务看板卡 + 端到端

**What to build:** 研究者通过 skill 的 setup 流程完成配置、doctor、dry-run 和测试推送，创建每天 08:00 的任务卡；从看板手动触发一次，微信收到真实日报。

**Blocked by:** 09.

**Status:** ready-for-agent

- [ ] SKILL.md 的 setup 流程能写出配置、跑 doctor、跑 dry-run、发测试推送、创建任务卡与 cron。
- [ ] 任务卡固定本仓库工作区与 workspace-write 权限；Prompt 明确加载 skill 与三步流程；不启用验收裁判。
- [ ] 从看板手动运行一次，微信收到真实日报，看板执行历史显示成功。
- [ ] 模拟发送失败时任务卡显示失败；下次运行优先重试 pending。
- [ ] skill 在项目级 skills 根目录可发现，并可通过用户级软链在任意工作区使用。
- [ ] 手工验收：日报 3+7、G6 独立区块、页脚源状态齐全。
