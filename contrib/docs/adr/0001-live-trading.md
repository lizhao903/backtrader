# ADR 0001: Live Trading Architecture — CEX Matrix + DEX Abstraction

## Status
Proposed — 2026-04-23 (tracking issue: #19)

## Context
Backtrader fork 目前仅支持传统经纪商 (IB / Oanda / VisualChart) 与内部回测 broker，无法覆盖加密货币市场。Issue #19 要求在不破坏现有 `Cerebro / Broker / Order` 状态机的前提下，接入 CEX (Binance / OKX / Bybit 等) 与 DEX (EVM 链上的 Uniswap 家族 + Solana 上的 Jupiter 生态)，以支持多策略实盘。

约束：
- 现有 broker 全部基于同步调用，仓库无 `asyncio` 痕迹，也无 `ccxt` 依赖。
- Order 生命周期固定为 `Submitted → Accepted → Partial → Completed / Canceled / Rejected` (`order.py`)，新 broker 必须映射到此状态机。
- 现有参考结构为 `stores/oandastore.py` + `brokers/oandabroker.py` + 对应 feed 的三层模型。
- 私钥与 API key 属于高敏感资产，必须与 broker 解耦以便审计与权限隔离。

## Decision

### 1. CEX 侧
- 采用 `ccxt` (同步 `ccxt` 包，非 `ccxt.pro`) 作为统一底层。
- 复用 oanda* 三层拆分：
  - `stores/ccxtstore.py`：维护交易所连接、API key、rate limiter、symbol 映射、余额与持仓缓存。
  - `brokers/ccxtbroker.py`：实现 `BrokerBase` 接口，负责下单、撤单、状态回写，把 ccxt 的 order status 映射到 backtrader 状态机。
  - `feeds/ccxtfeed.py`：OHLCV / trade 流，优先走 REST 轮询，WS 作为后续增强。
- 多交易所共用同一套代码，通过构造参数 `exchange_id` (`'binance'`, `'okx'`, `'bybit'`…) 与 `params` 区分；每个 Cerebro 实例允许挂多个 `ccxtbroker` (broker alias)。
- Spot / U-perp / Coin-perp **共用一个 broker 类**，但通过 `market_type` 枚举 (`spot` / `swap_linear` / `swap_inverse`) 与 `defaultType` ccxt 参数切换。理由：ccxt 已抽象了这三类市场的 unified API；强拆会重复大量撤单/余额/杠杆配置代码。仓位方向与保证金模式由 broker 内部根据 `market_type` 分派到不同 handler。

### 2. DEX 侧
- EVM 与 Solana **两套 broker、一个共同父类** `brokers/dexbroker.py::DEXBroker`，定义 `swap()` / `quote()` / `wait_for_confirmation()` / `map_tx_status()` 骨架。
  - `brokers/dex_evm.py`：基于 `web3.py`，面向 EVM (Ethereum / Arbitrum / Base / BSC)，聚合器后端默认 1inch v6。
  - `brokers/dex_sol.py`：基于 `solana-py` + `solders`，聚合器后端默认 Jupiter v6。
- 聚合器采用 **pluggable 但有 sane default**：`DEXBroker` 暴露 `aggregator` 策略对象，默认 `OneInchAggregator` / `JupiterAggregator`；允许后续注入 0x / Kyber / Raydium 直连。TBD：具体接口签名由 #21 决定。
- Store 层拆为 `stores/evmstore.py` (RPC 池、nonce manager、gas oracle) 与 `stores/solstore.py` (RPC、priority fee、blockhash 缓存)；broker 通过 store 访问链，不直接持有 RPC client。
- 订单生命周期映射：
  - `Submitted`：本地构造 tx / swap 报价锁定。
  - `Accepted`：tx 已签名并广播，拿到 tx hash / signature。
  - `Partial`：不适用 (swap 原子执行)，保留未使用。
  - `Completed`：链上 confirmed 且 `status == success`，按实际 filled amount 回写。
  - `Rejected`：广播前失败 (余额/授权/quote 过期) 或链上 revert。
  - `Canceled`：用户在广播前主动撤销，或 EVM 通过同 nonce 自替换 tx 取消。

### 3. Wallet / Signer 抽象
- Wallet 独立于 broker，存于 `brokers/wallets/` 目录（与现有 brokers 结构对齐），经依赖注入传给 `DEXBroker` (CEX 不需要)。
- 抽象接口 `WalletBase`：
  - `address(chain: str) -> str`
  - `sign_evm_tx(tx: dict) -> bytes`
  - `sign_sol_tx(tx: VersionedTransaction) -> bytes`
  - `supports(chain) -> bool`
- 实现：
  - `EnvVarWallet` (dev，私钥读 `BT_EVM_PRIVKEY` / `BT_SOL_PRIVKEY` 环境变量)
  - `LocalKeystoreWallet` (prod，加密 keystore + passphrase)
  - `LedgerWallet` (预留，接口先定，实现延后)

### 4. 公共能力
- Rate limit / retry：
  - CEX 放在 `ccxtstore` (复用 ccxt 的 `enableRateLimit` + 自研指数退避)。
  - DEX 放在 `evmstore` / `solstore` (RPC 侧) 与聚合器 client (报价侧)。
- Nonce / gas：EVM 专属，放 `evmstore`，提供 `reserve_nonce()` 与 `suggest_fees()`；broker 不自行管理。
- Slippage：放 `DEXBroker` 参数 (`slippage_bps`)，由聚合器调用时强制传入，默认 50 bps 并允许策略覆盖。
- 余额同步：
  - CEX：`ccxtstore` 周期性 `fetch_balance()` + 下单后主动刷新。
  - DEX：`evmstore` / `solstore` 通过 `balanceOf` / `getTokenAccountsByOwner` 查询，`PortfolioAggregator` 跨链合并，供 `cerebro.broker.getvalue()` 读取。
- 实盘开关：
  - 全局 `TRADING_LIVE_ENABLED=1` 环境变量为硬开关，默认 `0`。
  - 每个 broker 构造参数 `live=True` + allowlist (`live_allow=['binance:spot']`) 双重确认，任一缺失即 fallback 到 paper 模式。

## Consequences

### 正面
- 复用 oanda* 三层模式，新 broker 的加入路径对老用户友好。
- 单一 `ccxtbroker` 覆盖数十个 CEX 与三种合约类型，维护面最小。
- Wallet 独立抽象，硬件钱包 / MPC / 远程 KMS 都可后续无痛接入。
- 实盘开关双保险 (env + allowlist) 降低误触发真金白银风险。
- DEX 公父类 + pluggable aggregator，保留对接新聚合器 (Odos / CoW) 的演进空间。

### 负面 / 需要接受的妥协
- `ccxt` 同步模式在高频场景下性能不足，后续若需 WS 私有流可能要引入 `ccxt.pro` 或异步层，届时 broker 接口需二次抽象。
- Swap 的原子性让 `Partial` 状态闲置，与 backtrader 状态机略有阻抗失配；对部分成交的 TWAP 策略需在策略层自行拆单。
- Spot / perp 共用 broker 意味着仓位、保证金、funding 的内部分支逻辑较重，单测矩阵会膨胀。

## Alternatives Considered

- **DEX 用 `ethers-rs` + Python FFI (PyO3 binding)**：性能更好、类型更严。放弃理由：构建链复杂、跨平台 wheel 维护成本高、团队 Rust 储备不足；`web3.py` 在 RPC 吞吐上足以满足策略级 (非 MEV) 实盘需求。
- **EVM 与 Solana 各自独立 broker，无公共父类**：实现最简单。放弃理由：slippage / quote 过期 / confirmation 轮询 / aggregator 抽象这几块逻辑高度同构，独立实现会导致两边行为漂移，破坏策略可移植性。
- **为 Spot / U-perp / Coin-perp 各拆一个 broker**：状态机更清晰。放弃理由：ccxt 已统一三类市场 API，强拆会让 `CcxtStore` 的连接、余额、symbol 映射代码重复三份，且用户在单策略多市场场景下需手动挂三个 broker，易用性差。

## Open Questions
1. 聚合器失败时是否直接落地到原生 DEX (Uniswap V3 / Raydium)？由 #21 决定接口与 fallback 策略。
2. CEX 合约的 funding fee、资金费率如何计入 `cerebro.broker.getvalue()` 的 PnL？是否单独走一条 cash adjustment 流？
3. 多链余额在 `getvalue()` 中以何种计价币种聚合？USD 价格源走 CEX 现货中位数还是链上 oracle？
4. 是否支持同一策略在 CEX + DEX 之间做对冲套利的 atomic group order？若支持，撤单语义如何定义？
5. Ledger / 远程 KMS 的 UX (签名等待、超时重试) 是否需要引入 `asyncio` 或仅靠线程 + 超时？
