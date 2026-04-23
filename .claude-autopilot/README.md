# autopilot 2026-04-23

本目录是 2026-04-23 晚间自动化开发会话产生的任务指令包。
用户睡觉期间 cron 会在 20:00 与 01:00 自动触发新一轮 turn，读取本目录里的
`segment2.md` / `segment3.md` 作为执行规范。

## 规则（对未来 turn 的 assistant）

1. 分支始终是 `dev/autopilot-2026-04-23`。不要动 main。
2. 每完成一个 issue 的实质工作：
   - conventional commit：`chore|feat|docs(...): xxx (#<issue-no>)`
   - push 到 origin 同名分支
   - 在对应 GitHub issue 评论 commit 链接
   - **只有在 issue 的验收清单全部打勾后**才 `gh issue close`
3. 任何步骤失败：**不要询问用户**。把错误写入 `.claude-autopilot/log-segment{N}.md`，继续下一个 agent 任务。
4. 并行 agent 统一用 `isolation="worktree"`，完成后主 turn 负责 merge 回 autopilot 分支。
5. 尊重上层约束：实盘/链上交易代码默认关闭，不要在配置里埋真私钥或 mainnet endpoint。
6. Token 节流 / 账户级限额：
   - **尊重 Anthropic 5h session window 与 weekly 配额**
   - Seg 1 结束时配额状态：session 94%（20:40 重置），week 60%（Apr 29 重置）
   - 并行 sub-agent 数量上限（修订）：Seg 2 = 2，Seg 3 = 2
   - sub-agent 不要读 `backtrader/backtrader/linebuffer.py` / `lineseries.py` 全文，靠 grep 定点
   - **单次 agent prompt ≤ 2K tokens**，报告 ≤ 1500 字
   - 主 turn 不要把 agent 返回的原文全量粘到下一个 agent 的 prompt，做总结后再转发
   - **周配额守门**：每个 Segment 结束前检查周配额，若 >80% 立即停工并记 log，未做完的 issue 留到用户手工接手
   - **触发 rate limit 时**：记日志、sleep 600s、最多重试 2 次；仍失败就跳过本 issue 写入 log
7. 完成本 Segment 所有工作后：
   - 如果仍有时间 + 预算，读 `overflow.md` 拿下一个 issue 继续做
   - 否则 `git push`，结束 turn 等下一次 cron
8. **"尽可能多做"原则**：只要账户额度和 wall clock 允许，就不停派 agent 消化 `overflow.md`。
   overflow 队列尊重依赖顺序；每做完一个就划掉它。
