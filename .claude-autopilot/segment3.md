# Segment 3: 01:00 → 06:00 (5h)

## 目标
close #2（pytest 全量迁移）和 #23（钱包抽象完整实现）。收尾 autopilot 分支。

## 前置检查
读 `.claude-autopilot/log-segment2.md`。如果 Segment 2 没 close 的 issue，优先补刀。

## 执行序列

### Step 1: 并行派 sub-agent

- **Agent G — #2 pytest 全量迁移**（general-purpose, isolation=worktree）
  - 把 `tests/` 下 83 个脚本从 nosetests 风格迁到 pytest
  - 策略：
    1. 先批量替换 assertion：`assert_equal(a, b)` → `assert a == b`（可能大多本来就是 bare assert）
    2. 移除 `if __name__ == '__main__': testxxx()` 样板
    3. 把 module-level 函数改成 `test_*` 命名约定（大多本来就是）
    4. 在 `conftest.py` 里加 fixtures：共享数据路径、默认 cerebro 等
  - 跑 `pytest tests/ --collect-only` 确认 discover 数量 ≥ 75
  - 跑 `pytest tests/` —— **红的不强求修**，只要 discover 绿且大多数 pass 即可，红的记 follow-up issue
  - 验收：pytest 能 collect 全部测试，pass 率 ≥ 70%
  - 返回：新增/修改文件数 + pass/fail 统计

- **Agent H — #23 LocalKeystoreWallet + ledger 接口预留**（general-purpose, isolation=worktree）
  - 新增 `backtrader/brokers/wallets/keystore.py`
  - 使用 `eth-account` 的 keystore 格式（SCrypt 加密 JSON）
  - 支持从文件路径读，启动时一次 prompt 密码（password 从 env `BT_KEYSTORE_PASSWORD` 读，没有再报错）
  - ledger 接口：占位 `backtrader/brokers/wallets/ledger.py`，类定义 + NotImplementedError，加 TODO 注释
  - 测试：`tests/test_wallet_keystore.py`（mock keystore JSON，至少 3 个用例）
  - 验收：所有 wallet 测试绿
  - 返回：文件清单

### Step 2: 主 turn 合并 + 收尾

1. merge worktree → autopilot 分支
2. 跑全量检查：
   - `ruff check` 绿
   - `pytest tests/test_wallet_*.py` 全绿
   - `pytest tests/ --tb=no -q` 产出 pass/fail 统计写入 `.claude-autopilot/log-segment3.md`
3. Conventional commits:
   - `chore(tests): migrate 83 tests from nosetests to pytest (#2)`
   - `feat(brokers/wallets): LocalKeystoreWallet + Ledger stub (#23)`
4. push

### Step 3: 关闭 issue

- #2: 如果 pass 率 ≥ 70%，close；否则留开并评论 pass/fail 统计
- #23: 验收清单全部打勾则 close

### Step 4: 生成早间交付摘要

写 `.claude-autopilot/DELIVERY.md`：
- 分支：`dev/autopilot-2026-04-23`
- 已 close 的 issue 列表
- 未 close 的 issue 及原因
- 建议的下一步操作（比如 "review PR and merge to main"）
- 总提交数、总改动行数

### Step 5: 打印给用户的最终消息

最后一次 turn 的文本输出应该简短、全中文、直接告诉用户分支名和 DELIVERY.md 路径。**不要问问题**。

## 失败兜底
- pytest 迁移超时：保住已完成的部分，其余文件留原样，issue 里评论说明未完成范围
- 加密库 `eth-account` 装不上：降级到只写 stub + skip 相关测试，不拦住 close
- 所有 push 失败：把 branch 保留在本地，在 DELIVERY.md 里明确标注"manual push needed"
