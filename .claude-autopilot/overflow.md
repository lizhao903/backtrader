# Overflow Queue

每个 Segment 完成主要任务后，如果还有 token 预算和 wall clock 时间，就从这个队列
依次取下一个 issue 继续做。每消化一个就在本文件里划掉。

## 选择标准
- **可做**：不需要真实外部依赖（无 testnet / 无链上 / 无多家 CEX 账号）就能 close
- **延后**：需要真实环境验证的，留给用户人工推进

## 队列（按优先级）

1. **#11** feat(analyzers): ResultStore — 纯 Python + SQLite，analyzer 子类，单测覆盖
2. **#12** feat: JSON contract — dataclass/Pydantic 模型 + JSON Schema 文件
3. **#13** feat: HTML report — Jinja2 模板 + plotly 内嵌 JS；用一份 fixture 结果跑通
4. **#9**  feat(commissions): crypto maker/taker fee — 纯算数 + 单测
5. **#16** perf: optimize() analyzers-only return — 基于 `samples/optreturn` 封装成 kwarg
6. **#6**  feat(feeds): CCXT OHLCV feed — 允许用 mock ccxt 单测；真连接 testnet 留 Segment 4 / 人工
7. **#7**  feat(stores): CCXT store — 同 #6
8. **#8**  feat(brokers): CCXT spot broker — 同 #6
9. **#14** perf: numpy-accelerated indicators — 先做 SMA / EMA 两个最热的
10. **#17** feat(plot): Plotly backend (骨架) — 只做最小 OHLC + buy/sell 图层

## 队列（延后 —— 需要人工环境）

- #10 perp funding rate（需要真实数据）
- #20 CEX matrix 验收（需要多家 testnet）
- #21 EVM DEX broker（需要链上节点 + 私钥）
- #22 Solana DEX broker（同上）
- #15 async cerebro（高风险实验，人工把关）
- #18 Jupyter（需要 notebook 手测）

## Agent 执行规则（overflow 情况）

- 一次只派 1 个 worktree agent，避免并发爆炸
- 单个 agent 任务上限 90 分钟
- 返回后：主 turn 合并 → commit → push → close issue → 从队列取下一个
- 检测到任一下列信号立即停止，进入 SEG 结束流程：
  - 当前时间已过本 Segment 结束时间
  - rate limit 错误连续出现 2 次
  - agent 返回空内容或明显故障
- 停止时在 log-segment{N}.md 里记录"消化到 #XX"
