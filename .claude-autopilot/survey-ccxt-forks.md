# bt-ccxt / backtrader-binance 社区 Fork 调研报告 (issue #5)

调研日期：2026-04-23
调研者：autopilot agent (Explore)

## 项目对比表

| 项目 | 仓库链接 | 最近提交 | Stars/Forks | 许可证 |
|------|---------|---------|------------|-------|
| **bt-ccxt-store** | [Dave-Vallance/bt-ccxt-store](https://github.com/Dave-Vallance/bt-ccxt-store) | 2021-09 | 446 / 189 | MIT |
| **WISEPLAT/backtrader_binance** | [WISEPLAT/backtrader_binance](https://github.com/WISEPLAT/backtrader_binance) | 2026-01 | 227 / 76 | MIT |
| **bartosh/backtrader (ccxt 分支)** | [bartosh/backtrader@ccxt](https://github.com/bartosh/backtrader/tree/ccxt) | ~2021 | 160 / 52 | GPL-3.0 |
| **cloudQuant/backtrader** | [cloudQuant/backtrader](https://github.com/cloudQuant/backtrader) | 2026 活跃 | 75 / 23 | GPL-3.0 |

## 详细分析

### 1. bt-ccxt-store (Dave-Vallance)
- **耦合**：Plugin 式，独立 `ccxtbt/` 模块
- **规模**：核心 `ccxtstore.py` ~185 LOC
- **结构**：`ccxtbt/{ccxtstore,ccxtbroker,ccxtfeed}.py` + `samples/binance/`
- **能力**：OHLCV / 订单管理 / 钱包余额 / 沙箱模式 / 私有端点调用
- **局限**：2021-09 后无更新

### 2. WISEPLAT/backtrader_binance
- **耦合**：模块化插件
- **覆盖**：**币安专用**（现货 + 50x 杠杆演示；期货需另行确认）
- **结构**：`backtrader_binance/binance_store.py` + `ConfigBinance/` + 示例库
- **能力**：市价 / 限价 / 止损；精度处理；API 重试最多 5 次；时间框架映射
- **优势**：最近活跃（2026-01）

### 3. bartosh/backtrader (ccxt 分支)
- **耦合**：硬 fork
- **覆盖**：通用 CCXT（设计层面）
- **局限**：GPL-3.0（copyleft，和 MIT 上游冲突）；Python 2.7-3.6 时代

### 4. cloudQuant/backtrader
- **耦合**：增强 fork（20+ 数据源含 CCXT）
- **能力**：HTML/PDF/JSON 报告、TradeLogger、Plotly 可视化，性能比原版快 45%
- **局限**：CCXT 是通用特性之一，无专项深化；GPL-3.0

## 交易所与交易对支持矩阵

| 项目 | 现货 | 永续 | 支持范围 |
|------|-----|------|---------|
| bt-ccxt-store | ✓ 通用 | ✓ 通用 | 所有 CCXT 支持的 |
| backtrader_binance | ✓ 币安 | ? 待确认 | 币安专用 |
| bartosh@ccxt | ✓ 通用 | ✓ 通用 | 所有（实验级） |
| cloudQuant | ✓ | ✓ | CCXT 为其中之一 |

## 拣 vs 重写 建议

### 可直接拣 (≥80% 复用)
- **bt-ccxt-store**:
  - `ccxtbt/ccxtstore.py` — CCXT Store 通用框架
  - `ccxtbt/ccxtfeed.py` — OHLCV Feed 实现
  - `test/ccxtbt/` — 测试框架（需适配）
- **WISEPLAT/backtrader_binance**:
  - `ConfigBinance/` — API 凭证管理模式
  - `samples/` — 集成示例参考

### 需改造后拣 (30-80%)
- `ccxtbt/ccxtbroker.py` — 适配新的订单/风控逻辑
- `binance_store.py` — 币安专用重构为通用 CCXT 参数映射
- 精度处理 / 时间框架映射 — 统一到多交易所模型

### 必须重写
- 上游 backtrader 最新 API 兼容层
- 期货专项订单模型（现有多聚焦现货）
- 风险管理框架（杠杆/期货）
- 多交易所兼容性测试套件

## 许可证影响

- bt-ccxt-store (MIT) + WISEPLAT (MIT) 可直接拣入本 fork（上游 backtrader 是 GPL-3.0，但作为 GPL fork 自身，拣 MIT 代码不冲突）
- bartosh / cloudQuant 是 GPL-3.0，和当前仓库一致

## 结论（决策材料，非决策）

- 基础框架以 **bt-ccxt-store** 的三层结构为起点（MIT + 最成熟）
- 现货下单细节参考 **WISEPLAT** 的 binance_store
- 期货 / 风险管理 / 多交易所矩阵 需自行设计
- 报告层面可以参考 **cloudQuant** 的 HTML/PDF 产出（对应 issue #13）
