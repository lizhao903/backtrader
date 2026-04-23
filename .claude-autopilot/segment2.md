# Segment 2: 20:00 → 01:00 (5h)

## 目标
close GitHub issue #1 / #3 / #4，给 #23 打好骨架。

## 执行序列

### Step 1: 并行派 3 个 sub-agent（worktree 隔离）

- **Agent C — #1 + #4 合并做**（subagent_type=general-purpose, isolation=worktree）
  - 写 `pyproject.toml`（PEP 621，`requires-python=">=3.10"`，dependencies 参考 setup.py）
  - 保留 `setup.py` 作兼容薄壳
  - 配 `[tool.ruff]` / `[tool.ruff.lint]`：select = ["E","F","I","UP","B","SIM"]
  - 跑 `uv sync`（如果 uv 未装，降级到 `pip install -e .` 验证可装）
  - 跑 `ruff check --fix`，单独 commit autofix 结果
  - 验收: `uv run python -c "import backtrader"` 能导入，`ruff check` 退出码 0
  - 返回：`pyproject.toml` 内容 + autofix 影响文件数

- **Agent D — #3 GH Actions**（subagent_type=general-purpose, isolation=worktree）
  - 新建 `.github/workflows/ci.yml`：
    - triggers: push + pull_request
    - matrix: Python 3.11 / 3.12
    - steps: checkout → setup-python → pip install -e . → ruff check → pytest（容忍 pytest 不绿，不挂 CI）
  - 删除 `.travis.yml`
  - **不推到 GitHub 触发实际 CI**（节省资源），只提交到分支让未来有 PR 时生效
  - 返回：workflow 内容 + 删除文件列表

- **Agent E — #23 钱包抽象骨架**（subagent_type=general-purpose, isolation=worktree）
  - 新建 `backtrader/brokers/wallets/__init__.py`（Wallet 抽象基类，暴露 sign_evm_tx / sign_sol_tx / address(chain)）
  - 新建 `backtrader/brokers/wallets/envvar.py`（读 env var `BT_EVM_PRIVKEY` / `BT_SOL_PRIVKEY`；空则抛清晰异常）
  - 新建 `backtrader/brokers/wallets/__init__.py` 的 `__all__`
  - 新建 `tests/test_wallet_envvar.py`（3-5 个单测，覆盖缺 env / 非法 key / address 格式）
  - 验收：`pytest tests/test_wallet_envvar.py -v` 全绿
  - 返回：新增文件清单

### Step 2: 主 turn 合并

1. 三个 worktree 全部返回后，用 `git merge --no-ff <worktree-branch>` 合并到 autopilot 分支
2. 如果有冲突（可能性低，三个 agent 改的文件不重叠），自动选 union 策略；无法 union 的写入日志并跳过
3. 提交 conventional commits:
   - `chore: migrate to pyproject.toml and uv (#1)`
   - `chore: add ruff lint config and one-shot fix (#4)`
   - `chore: replace Travis CI with GitHub Actions (#3)`
   - `feat(brokers): unified wallet/signer abstraction scaffold (#23)`
4. `git push origin dev/autopilot-2026-04-23`

### Step 3: 关闭 issue

对每个完成的 issue:
```
gh issue comment <N> --body "Closed by autopilot on dev/autopilot-2026-04-23. Commit: <sha>"
gh issue close <N>
```

对 #23：**不关闭**（只完成骨架，LocalKeystore 在 Segment 3）。评论说明"scaffold landed, Segment 3 will complete"。

### Step 4: Overflow — 继续消化 `overflow.md`
在 01:00 之前的剩余时间里，按 `overflow.md` 队列从 #11 开始依次派单 agent（worktree），
每完成一个 commit + push + close。直到触发停止条件（见 overflow.md 规则）。

### Step 5: 触发 Segment 3
无需手动——01:00 cron 会自动触发。但在本 Segment 末尾，把简短总结写进 `.claude-autopilot/log-segment2.md`，
记录已消化的 overflow 进度，供 Segment 3 参考。

## 失败兜底
- Agent 失败：记日志、跳过该 issue、继续下一个
- uv 不可用：改用 `python -m venv` + `pip`
- 网络超时 (gh push)：重试 3 次，再失败就写日志后放弃 push（commit 留本地）
