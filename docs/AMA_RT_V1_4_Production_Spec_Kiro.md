# AMA-RT V1.4 Production Specification  
# 妖币右尾捕获系统：生产级实施规格书 / Kiro 交付文档

版本：V1.4  
代号：AMA-RT / Altcoin Momentum Agent - Right Tail Edition  
中文名：妖币右尾捕获系统  
用途：交付给 Kiro / AI Coding Agent 作为完整项目开发蓝图  
重要说明：本文档是**自包含规格书**。即使在没有任何前文上下文的情况下，Kiro 也应能根据本文档完成项目骨架、核心模块、测试、验收流程与落地部署。

---

## 目录

1. 项目总纲  
2. 给 Kiro 的最高执行指令  
3. 项目定位与非目标  
4. 系统最高铁律  
5. 项目版本路线图  
6. 目标函数与收益定位  
7. 总体架构  
8. 技术栈与预算  
9. 项目目录结构  
10. 配置系统规范  
11. 核心数据模型  
12. 事件驱动与 Event Sourcing  
13. Exchange Gateway 交易所接入层  
14. Market Data Buffer 市场数据缓冲层  
15. Regime Engine 市场周期闸门  
16. Universe Filter 标的资格过滤  
17. Pre-Anomaly Scanner 预异动扫描器  
18. Anomaly Scanner 显性异动扫描器  
19. Liquidity Filter 流动性过滤器  
20. Real Trade Confirmation 真实成交确认器  
21. Manipulation Detector 反操纵检测器  
22. LLM Interpreter / DeepSeek 情报压缩层  
23. Right Tail Scoring 右尾评分系统  
24. Opportunity Grading 机会评级系统  
25. Strategy Engine 策略引擎  
26. State Machine 交易状态机  
27. Risk Engine 风险引擎  
28. Capital Flow Engine 资金流与提现重算  
29. Position & Tail Manager 持仓与尾仓管理  
30. Execution FSM 执行状态机  
31. Reconciliation 对账与状态一致性  
32. Telegram Command Center  
33. Database 设计  
34. Replay Engine 回放系统  
35. Reflection Engine 标签化复盘系统  
36. Monitoring / Observability 监控告警  
37. Security / 权限与密钥安全  
38. Incident Response Runbook 事故响应手册  
39. Testing Matrix 测试矩阵  
40. Backtest / Paper Trading / Live 上线分级  
41. Go / No-Go Checklist  
42. Change Control 变更管理  
43. 开发阶段路线图  
44. 最终验收标准  
45. Kiro 实施顺序与禁止事项  
46. 附录：核心枚举、事件类型、评分等级、状态转移表

---

# 1. 项目总纲

## 1.1 项目名称

```text
AMA-RT
Altcoin Momentum Agent - Right Tail Edition
妖币右尾捕获系统
```

## 1.2 项目一句话定义

本系统不是“币安广场情绪机器人”，不是“AI 自动预测涨跌系统”，不是“高频交易系统”。

它是：

```text
市场异动驱动
+ 信息面解释
+ 真实成交确认
+ 反操纵过滤
+ 状态机执行
+ 风险预算约束
+ 浮盈右尾放大
+ 可回放、可审计、可暂停、可恢复
```

的小本金高风险右尾捕获系统。

## 1.3 最高目标

```text
在限定账户死亡概率内，
最大化短期 2x / 5x / 10x 的账户右尾爆发概率。
```

百倍收益只能作为彩票仓极端尾部奖励，不能作为主 KPI，不能让百倍目标污染系统规则。

## 1.4 当前文档定位

本文档不是单纯策略想法，而是 Kiro 可以直接执行的生产级实施规格书。

它要求 Kiro：

1. 先搭建生产级底座。
2. 再搭建数据、状态机、风控、执行、回放、监控。
3. 最后才接策略、LLM、右尾放大。
4. 禁止一开始直接写“自动下单赚钱策略”。

---

# 2. 给 Kiro 的最高执行指令

Kiro 必须严格遵守以下执行顺序：

```text
第一优先级：账户安全、状态一致、止损可确认、可暂停、可回放。
第二优先级：数据稳定、风控可靠、异常可恢复。
第三优先级：策略正确、信号有效、可复盘。
第四优先级：右尾捕获、收益放大。
```

Kiro 不得为了“快速完成交易策略”而跳过以下模块：

```text
Execution FSM
Event Sourcing
Reconciliation
Risk Engine
No-Trade Gate
Capital Flow Engine
Replay Engine
Monitoring
Incident Response
Testing Matrix
```

## 2.1 Kiro 禁止事项

Kiro 不得实现以下内容：

```text
AI 自主下单
AI 自主改仓位
AI 自主改杠杆
AI 自主修改止损
AI 自主绕过风控
强化学习实盘探索
多模型 Agent 决策链
GPU 训练
Kubernetes
微服务拆分
全市场 Tick 级 HFT
默认市价裸追单
Cross Margin
无止损仓位
亏损加仓
右尾放大使用本金
```

## 2.2 Kiro 默认模式

初始系统必须默认运行在：

```text
MODE = paper
LIVE_TRADING_ENABLED = false
RIGHT_TAIL_AMPLIFICATION_ENABLED = false
```

只有通过 Go / No-Go Checklist 后，才允许进入小资金受限实盘。

---

# 3. 项目定位与非目标

## 3.1 项目定位

本项目构建一个：

```text
低频 AI 增强型
事件驱动型
风险优先型
半自主量化操作系统
```

核心对象：

```text
Binance USDT 永续合约 Top 200
```

核心时间尺度：

```text
1m ~ 15m
```

核心主线：

```text
发现妖币预异动
→ 过滤流动性与市场周期
→ 验证真实成交
→ 检测反操纵
→ 用 DeepSeek 解释信息面
→ 状态机决策
→ 风控裁决
→ 执行 FSM 下单
→ 右尾管理
→ Replay / Reflection 复盘
```

## 3.2 明确非目标

本项目不做：

```text
稳定年化 40%
低波动稳健复利
每日固定盈利
纯币安广场情绪交易
LLM 预测涨跌
AI 自动决定方向
AI 自动决定杠杆
全自动无监督交易
高频 Tick HFT
无风控追涨杀跌
```

---

# 4. 系统最高铁律

## 4.1 策略铁律

```text
没有浮盈，不准疯狗。
没有退出通道，不准重拳。
没有结构确认，不准幻想。
```

## 4.2 工程铁律

```text
没有回测，不准扩大资金。
没有仿真，不准自动执行。
没有强退协议，不准谈十倍。
止损未确认，不准继续交易。
持仓状态未知，不准新开仓。
本地状态与交易所状态不一致，立刻保护。
```

## 4.3 风控铁律

```text
Risk Engine 拥有最高裁决权。
任何策略不能绕过 Risk Engine。
任何 LLM 输出不能绕过 Risk Engine。
任何 Telegram 指令不能绕过安全权限。
任何右尾放大必须来自浮盈。
亏损仓绝不加仓。
```

## 4.4 AI 权限铁律

LLM 只能做：

```text
叙事解释
事件归因
风险标签
KOL 集中度判断
Bot 风险判断
传播阶段判断
反向证据摘要
```

LLM 不允许做：

```text
下单
平仓
改杠杆
改仓位
改止损
给目标价
输出最终交易方向
绕过风控
```

---

# 5. 项目版本路线图

```text
AMA-RT V1.3 — Production Blueprint
生产级项目蓝图

AMA-RT V1.4 — Production Specification
生产级实施规格书，本文件

AMA-RT V1.5 — Paper Trading Acceptance
模拟盘验收版

AMA-RT V2.0 — Limited Live Production
小资金受限实盘生产版
```

---

# 6. 目标函数与收益定位

## 6.1 正确目标函数

本系统不是最大化胜率，也不是最大化年化收益。

目标函数：

```text
Maximize:
P(Account >= 2x within T)
P(Account >= 5x within T)
P(Account >= 10x within T)

Subject to:
P(Account <= 0.5x) <= limit_A
P(Account <= 0.3x) <= limit_B
No ghost position
No unstopped position
No untracked order
No uncontrolled leverage
```

## 6.2 收益层级

```text
短期 1x：理论上可追求
短期 5x：右尾目标
短期 10x：极端优秀结果
短期百倍：彩票仓尾部奖励，不能作为主 KPI
```

## 6.3 重要现实

Kiro 不得在任何 README、日志、Telegram 推送中宣称系统可以保证收益。系统只能描述为：

```text
右尾捕获系统
高风险投机系统
未验证前不得称盈利系统
```

---

# 7. 总体架构

## 7.1 总流程

```text
Exchange WebSocket / REST
        ↓
Exchange Gateway
        ↓
Market Data Buffer
        ↓
Regime Engine
        ↓
Universe Filter
        ↓
Pre-Anomaly Scanner
        ↓
Anomaly Scanner
        ↓
Liquidity Filter
        ↓
Real Trade Confirmation
        ↓
Manipulation Detector
        ↓
LLM Interpreter
        ↓
Right Tail Scoring
        ↓
Opportunity Grading
        ↓
Strategy Engine
        ↓
State Machine
        ↓
Risk Engine
        ↓
Capital Flow Engine
        ↓
Execution FSM
        ↓
Position / Tail Manager
        ↓
Reconciliation
        ↓
Telegram Center
        ↓
Replay Engine
        ↓
Reflection Engine
        ↓
Monitoring / Alerts
```

## 7.2 核心顺序

系统必须先判断：

```text
能不能交易
```

再判断：

```text
值不值得交易
```

最后判断：

```text
怎么交易
```

禁止：

```text
看到舆情 → 找理由 → 开仓
```

必须是：

```text
市场异动 → 成交确认 → 风险过滤 → 信息解释 → 状态机 → 风控 → 执行
```

---

# 8. 技术栈与预算

## 8.1 技术栈

```text
Language: Python 3.12
Concurrency: asyncio
WebSocket: aiohttp / websockets
Exchange SDK: ccxt / ccxt.pro
DataFrame: polars
TA: pandas-ta 或自实现轻量指标
State Machine: transitions 或自实现 FSM
Config: pydantic-settings
Logging: loguru
Database: SQLite WAL
Backtest: vectorbt / 自定义 replay
Telegram: python-telegram-bot
LLM: DeepSeek API
Deployment: Ubuntu VPS
Process Manager: systemd 或 supervisor
```

## 8.2 服务器

```text
4 CPU
8GB RAM
Ubuntu 22.04 / 24.04
Tokyo / Singapore VPS
Budget: 20-30 USD/month
```

## 8.3 API 预算

```text
DeepSeek API: 50 USD
备用: 20 USD
总预算: 100 USD
```

---

# 9. 项目目录结构

Kiro 必须创建如下目录结构：

```text
ama_rt/
│
├── app/
│   ├── main.py
│   ├── bootstrap.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   ├── defaults.yaml
│   │   ├── risk.yaml
│   │   ├── strategy.yaml
│   │   ├── secrets.example.yaml
│   │   └── schema.py
│   │
│   ├── core/
│   │   ├── clock.py
│   │   ├── enums.py
│   │   ├── events.py
│   │   ├── models.py
│   │   ├── errors.py
│   │   └── constants.py
│   │
│   ├── exchanges/
│   │   ├── base.py
│   │   ├── binance.py
│   │   ├── orderbook.py
│   │   ├── trades.py
│   │   └── account.py
│   │
│   ├── market_data/
│   │   ├── buffer.py
│   │   ├── candles.py
│   │   ├── cvd.py
│   │   ├── oi.py
│   │   ├── funding.py
│   │   └── liquidation.py
│   │
│   ├── regime/
│   │   ├── engine.py
│   │   └── models.py
│   │
│   ├── universe/
│   │   ├── filter.py
│   │   └── models.py
│   │
│   ├── scanner/
│   │   ├── pre_anomaly.py
│   │   ├── anomaly.py
│   │   └── models.py
│   │
│   ├── liquidity/
│   │   ├── filter.py
│   │   ├── slippage.py
│   │   └── models.py
│   │
│   ├── confirmation/
│   │   ├── real_trade.py
│   │   └── models.py
│   │
│   ├── manipulation/
│   │   ├── detector.py
│   │   └── models.py
│   │
│   ├── llm/
│   │   ├── deepseek.py
│   │   ├── prompts.py
│   │   ├── schemas.py
│   │   ├── guardrails.py
│   │   └── cache.py
│   │
│   ├── scoring/
│   │   ├── right_tail.py
│   │   ├── opportunity.py
│   │   └── models.py
│   │
│   ├── strategies/
│   │   ├── base.py
│   │   ├── breakout_momentum.py
│   │   ├── liquidation_reversal.py
│   │   ├── squeeze_follow.py
│   │   ├── distribution_short.py
│   │   └── meta_allocator.py
│   │
│   ├── state_machine/
│   │   ├── trade_state.py
│   │   ├── transitions.py
│   │   └── timeout.py
│   │
│   ├── risk/
│   │   ├── engine.py
│   │   ├── no_trade_gate.py
│   │   ├── leverage.py
│   │   ├── heat.py
│   │   ├── circuit_breaker.py
│   │   └── models.py
│   │
│   ├── capital/
│   │   ├── flow.py
│   │   ├── profit_harvest.py
│   │   ├── rebase.py
│   │   └── models.py
│   │
│   ├── execution/
│   │   ├── fsm.py
│   │   ├── order_manager.py
│   │   ├── stop_manager.py
│   │   ├── execution_policy.py
│   │   └── models.py
│   │
│   ├── positions/
│   │   ├── manager.py
│   │   ├── tail.py
│   │   ├── pnl.py
│   │   └── models.py
│   │
│   ├── reconciliation/
│   │   ├── reconciler.py
│   │   └── models.py
│   │
│   ├── telegram/
│   │   ├── bot.py
│   │   ├── commands.py
│   │   ├── auth.py
│   │   └── formatter.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   ├── repositories.py
│   │   └── schema.sql
│   │
│   ├── replay/
│   │   ├── engine.py
│   │   ├── loaders.py
│   │   ├── diff.py
│   │   └── report.py
│   │
│   ├── reflection/
│   │   ├── engine.py
│   │   ├── tags.py
│   │   └── report.py
│   │
│   ├── monitoring/
│   │   ├── metrics.py
│   │   ├── alerts.py
│   │   ├── health.py
│   │   └── watchdog.py
│   │
│   └── utils/
│       ├── math.py
│       ├── time.py
│       ├── json.py
│       └── retry.py
│
├── data/
│   ├── sqlite/
│   ├── logs/
│   ├── replay/
│   ├── cache/
│   └── reports/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── replay/
│   ├── stress/
│   └── fixtures/
│
├── scripts/
│   ├── init_db.py
│   ├── run_paper.py
│   ├── run_live_limited.py
│   ├── replay_day.py
│   └── emergency_flatten.py
│
├── docs/
│   ├── PRD.md
│   ├── HLD.md
│   ├── LLD.md
│   ├── RUNBOOK.md
│   ├── TEST_MATRIX.md
│   ├── GO_NO_GO.md
│   └── CHANGELOG.md
│
├── requirements.txt
├── pyproject.toml
├── README.md
└── .env.example
```

---

# 10. 配置系统规范

## 10.1 配置原则

所有阈值必须配置化，不得写死在代码中。

配置文件：

```text
app/config/defaults.yaml
app/config/risk.yaml
app/config/strategy.yaml
.env
```

## 10.2 核心配置项示例

```yaml
mode:
  trading_mode: "paper"   # paper | live_limited | live
  live_trading_enabled: false
  right_tail_enabled: false

exchange:
  name: "binance"
  market_type: "usdt_perpetual"
  symbols_limit: 200
  isolated_margin_only: true
  cross_margin_allowed: false

risk:
  max_daily_loss_pct: 0.05
  max_consecutive_losses: 5
  max_single_trade_loss_pct:
    scout: 0.005
    attack: 0.015
  stop_required: true
  stop_confirmation_required: true

liquidity:
  max_spread_pct: 0.003
  max_slippage_pct: 0.005
  min_depth_multiplier: 5

llm:
  provider: "deepseek"
  enabled: true
  max_calls_per_hour: 100
  allow_trade_decision: false

telegram:
  enabled: true
  command_confirm_required:
    resume: true
    change_config: true
    kill_all: false
```

---

# 11. 核心数据模型

Kiro 必须用 Pydantic 或 dataclass 定义以下核心模型。

## 11.1 MarketSnapshot

```python
class MarketSnapshot:
    symbol: str
    timestamp: int
    last_price: float
    mark_price: float | None
    bid: float
    ask: float
    spread_pct: float
    volume_1m: float
    volume_5m: float
    oi: float | None
    funding_rate: float | None
    cvd_1m: float | None
    cvd_5m: float | None
    atr_1m: float | None
    atr_5m: float | None
    orderbook_depth_usdt: float | None
```

## 11.2 SignalSnapshot

```python
class SignalSnapshot:
    symbol: str
    timestamp: int
    regime: str
    pre_anomaly_score: float
    anomaly_score: float
    liquidity_score: float
    trade_confirmation_level: str
    manipulation_level: str
    right_tail_score: float
    opportunity_grade: str
    no_trade_reason: list[str]
```

## 11.3 TradeDecision

```python
class TradeDecision:
    symbol: str
    timestamp: int
    action: str  # observe | scout | attack | amplify | lock_profit | exit | reject
    direction: str | None  # long | short | none
    state: str
    grade: str
    entry_zone: list[float] | None
    stop_price: float | None
    take_profit_plan: dict
    risk_budget_pct: float
    leverage: float
    reasons: list[str]
    reject_reasons: list[str]
```

## 11.4 PositionState

```python
class PositionState:
    position_id: str
    symbol: str
    direction: str
    qty: float
    entry_price: float
    mark_price: float
    stop_price: float | None
    stop_confirmed: bool
    margin_mode: str
    leverage: float
    unrealized_pnl: float
    realized_pnl: float
    tail_qty: float
    state: str
```

## 11.5 CapitalState

```python
class CapitalState:
    initial_capital: float
    exchange_equity: float
    withdrawn_profit: float
    lifetime_equity: float
    trading_capital: float
    account_life_tier: str
    risk_budget_total: float
    last_rebase_ts: int
```

公式：

```text
lifetime_equity = exchange_equity + withdrawn_profit
risk_budget = trading_capital
trading_capital = exchange_equity
```

---

# 12. 事件驱动与 Event Sourcing

## 12.1 核心原则

每一个重要动作都必须写入事件日志，系统必须可以通过事件日志回放。

事件必须包含：

```text
event_id
timestamp
event_type
source_module
symbol
position_id
order_id
payload
```

## 12.2 事件类型

```text
MARKET_SNAPSHOT
REGIME_UPDATED
UNIVERSE_FILTERED
PRE_ANOMALY_DETECTED
ANOMALY_DETECTED
LIQUIDITY_CHECKED
TRADE_CONFIRMED
MANIPULATION_DETECTED
LLM_INTERPRETED
RIGHT_TAIL_SCORED
OPPORTUNITY_GRADED
STATE_TRANSITION
RISK_APPROVED
RISK_REJECTED
ORDER_SENT
ORDER_ACK
ORDER_PARTIAL_FILLED
ORDER_FILLED
ORDER_CANCELLED
STOP_SENT
STOP_CONFIRMED
STOP_FAILED
POSITION_OPENED
POSITION_UPDATED
POSITION_CLOSED
EXIT_TRIGGERED
CAPITAL_DEPOSIT
CAPITAL_WITHDRAWAL
PROFIT_HARVEST
CAPITAL_REBASE
RISK_BUDGET_RECALCULATED
RECONCILIATION_STARTED
RECONCILIATION_MISMATCH
RECONCILIATION_RESOLVED
PROTECTION_MODE_ENTERED
PROTECTION_MODE_EXITED
TELEGRAM_COMMAND_RECEIVED
INCIDENT_OPENED
INCIDENT_RESOLVED
```

---

# 13. Exchange Gateway 交易所接入层

## 13.1 职责

```text
连接 WebSocket
订阅行情
订阅成交流
维护订单簿
查询账户
查询持仓
下单
撤单
查询订单状态
设置杠杆
设置保证金模式
```

## 13.2 强制规则

```text
必须使用 isolated margin
禁止 cross margin
API Key 禁止提现权限
所有下单必须带 client_order_id
所有止盈止损必须 reduce-only
所有下单必须经过 Risk Engine
所有下单必须经过 Execution FSM
```

## 13.3 数据源可靠性等级

```text
A: WebSocket 原始成交 / 订单事件
B: 交易所 REST 官方数据
C: 第三方聚合数据
D: 文本 / 社区 / LLM 推断
```

低可靠性数据不得单独触发进攻仓。

---

# 14. Market Data Buffer 市场数据缓冲层

## 14.1 职责

```text
缓存最近 N 分钟 trades
缓存最近 N 分钟 candles
缓存 orderbook 快照
维护 CVD
维护 volume rolling window
维护 ATR
维护 funding / OI 最新值
```

## 14.2 异常处理

```text
WebSocket 断线：标记数据不可信，暂停新开仓
Orderbook gap：重新拉快照
Trade stream 停止：暂停该 symbol 信号
REST 与 WS 冲突：触发 reconciliation
```

---

# 15. Regime Engine 市场周期闸门

## 15.1 输出

```json
{
  "market_regime": "MEME_RISK_ON",
  "btc_trend": "UP",
  "btc_volatility": "HIGH",
  "alt_liquidity": "EXPANDING",
  "risk_permission": "ALLOW_ATTACK"
}
```

## 15.2 状态

```text
M1 MEME_RISK_ON        妖币狂热期
M2 SECTOR_ROTATION     板块轮动期
M3 BTC_ABSORPTION      主流币吸血期
M4 ALT_RISK_OFF        山寨退潮期
M5 SYSTEMIC_RISK       系统性风险期
```

## 15.3 动作映射

```text
M1：允许侦察、进攻、右尾放大
M2：只打板块龙头
M3：降低小币做多，只观察
M4：禁止追多，只允许极少数事件空
M5：全天禁交易，只允许平仓
```

---

# 16. Universe Filter 标的资格过滤

## 16.1 输入

```text
symbol list
24h volume
spread
depth
trade continuity
contract status
```

## 16.2 通过条件

```text
Spread <= max_spread_pct
Estimated Slippage <= max_slippage_pct
Depth >= planned_order_size * min_depth_multiplier
最近 5 分钟成交连续
合约状态正常
交易所 API 正常
```

## 16.3 输出

```json
{
  "symbol": "PEPEUSDT",
  "eligible": true,
  "reject_reasons": []
}
```

---

# 17. Pre-Anomaly Scanner 预异动扫描器

## 17.1 目的

发现“还没刷屏但正在变强”的标的。

## 17.2 信号

```text
低位成交量温和放大
价差收窄
主动买单增加
OI 温和上升
Funding 未过热
小幅上涨但未大幅拉升
独立社区讨论源增加
```

## 17.3 输出

```json
{
  "symbol": "XXXUSDT",
  "pre_anomaly_score": 76,
  "reason_tags": [
    "volume_base_expansion",
    "oi_soft_rise",
    "spread_compression"
  ]
}
```

---

# 18. Anomaly Scanner 显性异动扫描器

## 18.1 指标

```text
OI Spike
CVD Spike
Volume Spike
ATR Expansion
Funding Extreme
Liquidation Spike
Sweep
Multi-Timeframe Breakout
```

## 18.2 初始公式

```text
anomaly_score =
OI_score * 0.25
+ CVD_score * 0.25
+ Volume_score * 0.20
+ ATR_score * 0.10
+ Funding_score * 0.10
+ Liquidation_score * 0.10
```

Kiro 必须让权重可配置。

---

# 19. Liquidity Filter 流动性过滤器

## 19.1 指标

```text
Spread
Orderbook depth
Estimated market impact
Exit time estimate
Slippage
Depth collapse
```

## 19.2 退出通道判断

必须实现函数：

```text
can_exit_position(symbol, qty, max_slippage_pct, max_seconds)
```

如果无法在 30-60 秒内以可接受滑点退出，仓位过大，不允许进攻仓。

---

# 20. Real Trade Confirmation 真实成交确认器

## 20.1 目的

识别真实买盘推动价格，而不是成交量诱多。

## 20.2 指标

```text
Trade Efficiency = price_change / traded_volume
CVD Price Agreement
Breakout Hold Time
Large Trade Follow Through
Volume Up Price Move
```

## 20.3 等级

```text
T0 无确认
T1 弱确认
T2 中等确认
T3 强确认
T4 极强确认
```

## 20.4 T3 示例条件

```text
CVD 与价格同向持续 >= 3 根 1m K
突破后 >= 3 分钟不跌回突破位
大额主动买入后价格继续上移
成交效率高于过去 30 分钟均值
```

---

# 21. Manipulation Detector 反操纵检测器

## 21.1 目的

识别伪右尾、诱多、派发。

## 21.2 检测项

```text
价格先拉，舆情后爆
KOL 同时喊单
文案高度重复
买墙频繁撤单
主动买很多但价格推不动
OI 暴增但价格停滞
成交巨大但价格不再创新高
上影线变长
Funding 快速过热
社区满屏目标价
多交易所价差异常
盘口深度突然消失
```

## 21.3 等级

```text
M0 无明显操纵
M1 轻度异常，只允许观察或侦察
M2 明显诱多，禁止进攻
M3 高度操纵，禁止交易
```

## 21.4 硬规则

```text
M2：禁止进攻仓
M3：禁止交易
M1：最多侦察仓
```

---

# 22. LLM Interpreter / DeepSeek 情报压缩层

## 22.1 输入

```text
帖子内容
信息源
时间戳
相关 symbol
价格变化
OI 变化
Funding 变化
anomaly_score
```

## 22.2 输出 JSON Schema

```json
{
  "narrative": "string",
  "catalyst": "real | weak | none | unknown",
  "evidence_quality": "A | B | C | D",
  "source_diversity": 0,
  "kol_concentration": 0,
  "bot_risk": 0,
  "hype_stage": "early | spreading | climax | decay | unknown",
  "contradictions": ["string"],
  "risk_tags": ["string"],
  "confidence": 0.0
}
```

## 22.3 LLM Guardrails

```text
禁止输出 direction
禁止输出 leverage
禁止输出 position_size
禁止输出 target_price
非法字段直接丢弃
JSON schema 不通过则降级
LLM 超时默认降级，不默认放行
LLM 不得覆盖 Risk Engine
```

## 22.4 Token 节流

```text
anomaly_score < 60：不调用 LLM
60-75：轻量标签
75-90：标准解释
90+：完整解释 + 风险标签
```

---

# 23. Right Tail Scoring 右尾评分系统

## 23.1 核心分数

```text
Explosion Score        爆发分
Continuation Score     延续分
Trap Score             陷阱分
Liquidity Exit Score   可退出分
Narrative Leader Score 龙头分
Squeeze Score          逼空分
Right Tail Validity    右尾有效性
```

## 23.2 右尾有效性

判断：

```text
上涨后是否继续承接
突破后是否回踩不破
成交量放大是否带来价格效率
新资金是否持续进入
社群是扩散而不是狂欢
大户是否在派发
价格创新高是否顺畅
```

---

# 24. Opportunity Grading 机会评级系统

```text
S 级：允许进攻 + 浮盈右尾放大
A 级：允许进攻，不允许右尾放大
B 级：只允许侦察
C 级：观察
D 级：禁止交易
```

## 24.1 S 级条件

```text
市场周期允许
标的是叙事龙头
真实成交 T3/T4
操纵等级 M0/M1
流动性退出分高
叙事处于 early/spreading
结构未过热
已有浮盈可用于右尾放大
```

---

# 25. Strategy Engine 策略引擎

## 25.1 第一阶段只实现两个策略

```text
Breakout Momentum 主升浪追击
Liquidation Reversal 爆仓反弹
```

## 25.2 第二阶段再实现

```text
Squeeze Follow 逼空跟随
Narrative Leader 龙头轮动
Distribution Short 高位派发短空
```

## 25.3 策略输出

策略只输出候选，不得直接下单。

```json
{
  "strategy": "breakout_momentum",
  "symbol": "XXXUSDT",
  "direction": "long",
  "score": 87,
  "entry_zone": [1.21, 1.24],
  "invalid_price": 1.18,
  "reason_tags": ["breakout", "cvd_confirmed", "oi_rising"]
}
```

---

# 26. State Machine 交易状态机

## 26.1 状态

```text
NO_TRADE
OBSERVE
SCOUT
CONFIRM
ATTACK
RIGHT_TAIL_AMPLIFY
LOCK_PROFIT
DISTRIBUTION_ALERT
FORCED_EXIT
```

## 26.2 不允许跳级

禁止：

```text
OBSERVE → RIGHT_TAIL_AMPLIFY
SCOUT → HEAVY_ATTACK
DISTRIBUTION_ALERT → ADD_POSITION
FORCED_EXIT → CANCEL_EXIT_BY_LLM
LOSS_POSITION → RIGHT_TAIL_AMPLIFY
```

## 26.3 正常路径

```text
OBSERVE → SCOUT → CONFIRM → ATTACK → LOCK_PROFIT / RIGHT_TAIL_AMPLIFY → TAIL / FORCED_EXIT
```

## 26.4 状态超时

```text
OBSERVE 超过 30 分钟未确认 → 移出候选池
SCOUT 10-15 分钟无成交推动 → 平仓
CONFIRM 连续 2 次突破失败 → 降级
ATTACK 盈利未延续且 CVD 转弱 → 锁利
DISTRIBUTION_ALERT 持续 3 根 K → 减仓或退出
RIGHT_TAIL_AMPLIFY 任一核心条件失效 → 锁利
```

---

# 27. Risk Engine 风险引擎

## 27.1 职责

```text
最终裁决
仓位预算
杠杆计算
止损校验
No-Trade Gate
Circuit Breaker
Portfolio Heat
Account Life Tier
```

## 27.2 No-Trade Gate

任一条件触发，禁止新开仓：

```text
BTC/ETH 快速下跌
全市场山寨退潮
交易所数据延迟或断连
候选币点差过大
候选币深度不足
Funding 极端异常
社群热度过热但价格不涨
同类妖币集体退潮
连续亏损达到阈值
单日回撤达到阈值
操纵 M3
重大新闻未确认
系统无法确认持仓/止损状态
```

## 27.3 杠杆计算

不得固定说“激进用几倍”。

必须：

```text
先定结构失效点
再定止损距离
再定单笔可亏金额
再考虑滑点
最后反推仓位与杠杆
```

## 27.4 账户生命值档位

```text
A: >= 1.5x   允许进攻，允许浮盈右尾放大
B: 1.0-1.5x 正常模式
C: 0.7-1.0x 降低试错频率
D: 0.5-0.7x 禁止右尾放大
E: 0.3-0.5x 只允许观察 / paper
F: < 0.3x    停机复盘
```

---

# 28. Capital Flow Engine 资金流与提现重算

## 28.1 必须实现

用户盈利后提现部分金额，系统不得误判为亏损或回撤。

## 28.2 四个账户概念

```text
Initial Capital 初始本金
Exchange Equity 当前交易所权益
Withdrawn Profit 已提现利润
Lifetime Equity 生命周期总权益
Trading Capital 当前可交易本金
```

公式：

```text
Lifetime Equity = Exchange Equity + Withdrawn Profit
Trading Capital = Exchange Equity
Risk Budget = Trading Capital
Performance = Lifetime Equity
```

## 28.3 提现事件

必须记录：

```text
CAPITAL_WITHDRAWAL
PROFIT_HARVEST
CAPITAL_REBASE
RISK_BUDGET_RECALCULATED
```

## 28.4 提现后流程

```text
1. 暂停新开仓
2. 记录提现事件
3. 查询交易所权益
4. 更新 Withdrawn Profit
5. 计算 Lifetime Equity
6. 重新计算 Trading Capital
7. 重新计算账户生命值
8. 重新计算仓位弹药
9. 重新计算单笔最大风险
10. 确认无持仓/止损异常
11. 完成 Rebase
12. 恢复交易
```

## 28.5 利润收割建议

```text
账户 2x：提现 30%-50% 利润
账户 5x：提现 50%-70% 利润
账户 10x：提现大部分本金 + 部分利润
```

硬规则：

```text
提现不是亏损。
提现是资金基准重置。
Rebase 前禁止新开仓。
已提现利润不得重新纳入风险预算。
```

---

# 29. Position & Tail Manager 持仓与尾仓管理

## 29.1 分层止盈

```text
第一段：回收风险本金
第二段：锁定部分利润
第三段：移动止盈
第四段：极小尾仓博极端延伸
```

## 29.2 右尾放大前置条件

必须全部满足：

```text
已有浮盈
已回收部分风险本金
已锁定部分利润
趋势结构未破
承接仍然存在
流动性仍可退出
Trap Score 没有升高
Manipulation 未升至 M2/M3
```

## 29.3 禁止

```text
本金直接右尾放大
亏损仓右尾放大
未回收本金前加仓
派发警戒态加仓
流动性不足时加仓
```

---

# 30. Execution FSM 执行状态机

## 30.1 状态

```text
IDLE
SIGNAL_RECEIVED
RISK_CHECKED
ORDER_SENT
ACK_RECEIVED
PARTIAL_FILLED
FULL_FILLED
STOP_SENT
STOP_CONFIRMED
POSITION_OPEN
EXIT_TRIGGERED
POSITION_CLOSING
POSITION_CLOSED
ERROR_PROTECTION
```

## 30.2 执行铁律

```text
默认禁止裸市价追单
优先限价单
必须设置最大滑点
部分成交必须重算风险
止盈止损必须 reduce-only
必须 isolated margin
禁止 cross margin
止损未确认前禁止加仓
```

## 30.3 执行失败处理

```text
下单未成交：超时撤单
部分成交：重新计算风险与止损
止损挂不上：立即保护平仓
WebSocket 断线：暂停新开仓
REST 与 WS 冲突：触发 Reconciliation
API timeout：进入保护模式
order latency 超阈值：禁止新开仓
价格越过止损但未执行：保护退出
```

---

# 31. Reconciliation 对账与状态一致性

## 31.1 目的

防止：

```text
本地以为空仓，交易所有仓
本地以为止损已挂，实际没挂
本地以为订单已撤，实际成交
本地权益与交易所权益不一致
```

## 31.2 对账对象

```text
本地订单 vs 交易所订单
本地持仓 vs 交易所持仓
本地止损 vs 交易所挂单
本地权益 vs 交易所权益
WebSocket 状态 vs REST 状态
```

## 31.3 硬规则

```text
任意不一致 → 暂停新开仓
止损状态未知 → 保护模式
持仓未知 → 禁止交易
无法修复 → Telegram P0 告警
```

---

# 32. Telegram Command Center

## 32.1 指令

```text
/status          当前系统状态
/positions       当前持仓
/pnl             盈亏统计
/pause           暂停新开仓
/resume          恢复交易，需要二次确认
/kill_all        全部平仓
/risk            当前风险状态
/capital         当前资金状态
/rebase          手动触发资金重算，需要确认
/incidents       当前事故
```

## 32.2 权限

```text
Telegram 用户白名单
管理员权限分级
resume 需要二次确认
change_config 需要二次确认
kill_all 可快速执行，但必须记录
```

---

# 33. Database 设计

SQLite WAL。

## 33.1 数据库

```text
market.db
events.db
orders.db
positions.db
trades.db
capital.db
reflection.db
llm_cache.db
incidents.db
```

## 33.2 必须实现 migration

Kiro 必须提供：

```text
scripts/init_db.py
app/database/migrations.py
app/database/schema.sql
```

---

# 34. Replay Engine 回放系统

## 34.1 回放对象

```text
市场数据
信号数据
LLM 输出
状态机转移
风控裁决
订单事件
持仓变化
资金事件
TG 指令
系统异常
```

## 34.2 输出

```text
决策差异报告
状态转移报告
订单执行报告
风控拒绝报告
事故报告
```

---

# 35. Reflection Engine 标签化复盘系统

## 35.1 禁止自由反思

LLM 不得自由长篇总结，必须结构化标签。

## 35.2 复盘字段

```json
{
  "symbol": "XXXUSDT",
  "setup": "breakout_momentum",
  "result": "loss",
  "mistake_tags": [
    "late_entry",
    "weak_trade_confirmation",
    "trap_score_ignored"
  ],
  "mfe": 0.12,
  "mae": -0.04,
  "tail_contribution": 0.0
}
```

---

# 36. Monitoring / Observability 监控告警

## 36.1 市场数据监控

```text
WebSocket 延迟
断线次数
Orderbook 更新时间
成交流中断时间
OI 延迟
Funding 延迟
REST 失败率
```

## 36.2 执行监控

```text
下单 ACK 延迟
撤单延迟
部分成交数量
未确认订单
孤儿订单
止损挂单成功率
reduce-only 失败
滑点超阈值
```

## 36.3 账户监控

```text
本地持仓 vs 交易所持仓差异
本地权益 vs 交易所权益差异
保证金占用
未实现盈亏
最大单币敞口
Meme 相关敞口
当日亏损
连续亏损
```

## 36.4 系统监控

```text
CPU
RAM
磁盘
数据库写入失败
日志写入失败
Telegram 指令延迟
LLM 调用失败率
保护模式触发次数
```

---

# 37. Security / 权限与密钥安全

## 37.1 API Key

```text
禁止提现权限
只允许交易权限
IP 白名单
密钥不得写入代码
密钥使用环境变量或加密配置
日志不得打印密钥
```

## 37.2 Telegram

```text
用户白名单
管理员角色
二次确认
指令审计日志
异常指令告警
```

## 37.3 LLM 安全

```text
输入源不可信
防提示词注入
JSON schema 校验
字段白名单
非法字段丢弃
LLM 失败默认降级
LLM 不得进入交易动作链
```

---

# 38. Incident Response Runbook 事故响应手册

## 38.1 事故等级

```text
P0：可能造成账户重大损失
P1：交易功能异常
P2：数据延迟或局部模块异常
P3：非关键功能异常
```

## 38.2 P0 示例

触发：

```text
止损未挂上
持仓未知
交易所连接异常但存在持仓
本地与交易所持仓不一致
Kill All 失败
```

动作：

```text
暂停新开仓
进入保护模式
尝试确认或平仓
Telegram 紧急通知
记录事故
要求人工确认恢复
```

## 38.3 P1 示例

```text
WebSocket 断线
REST 高失败率
订单 ACK 延迟过高
Replay 写入失败
```

动作：

```text
暂停新开仓
已有持仓保护监控
恢复后先观察，不自动进攻
```

---

# 39. Testing Matrix 测试矩阵

必须实现以下测试：

```text
单元测试
集成测试
回放测试
断线重连测试
部分成交测试
重复下单测试
止损失败测试
API timeout 测试
WebSocket 延迟测试
数据库写入失败测试
Telegram 误指令测试
LLM 超时测试
LLM 非法输出测试
No-Trade Gate 测试
Kill All 测试
Capital Rebase 测试
Reconciliation 测试
Go / No-Go 测试
```

每个测试必须有：

```text
输入场景
预期行为
通过标准
失败处理
```

---

# 40. Backtest / Paper Trading / Live 上线分级

## 40.1 L0 只读模式

```text
接行情
打信号
不下单
```

## 40.2 L1 纸面交易

```text
记录假订单
假仓位
假盈亏
Replay 可用
```

## 40.3 L2 小资金手动确认

```text
系统给信号
人工下单
验证信号与执行建议
```

## 40.4 L3 小资金半自动

```text
系统下单
右尾放大禁用
仓位极小
```

## 40.5 L4 小资金全自动

```text
完整状态机
完整风控
仓位上限极低
```

## 40.6 L5 扩大资金

必须通过连续周期验收。

---

# 41. Go / No-Go Checklist

## 41.1 Go 条件

```text
14 天 paper trading
无幽灵仓位
无重复下单
无未挂止损
Replay 可复现
Kill All 成功
Pause / Resume 成功
Capital Rebase 成功
Reconciliation 成功
No-Trade Gate 生效
LLM 非法输出被拦截
P0 Runbook 测试通过
```

## 41.2 No-Go 条件

```text
任意一次未知持仓
任意一次止损未确认且未保护
任意一次重复下单
任意一次本地与交易所状态不一致未处理
任意一次 Telegram 未授权指令通过
任意一次 LLM 输出影响交易动作
```

---

# 42. Change Control 变更管理

## 42.1 规则

```text
任何参数修改必须记录版本
任何风控阈值修改必须写明原因
盘中不得放宽风控
右尾放大条件不得人工绕过
实盘参数必须与回测参数绑定
参数变更必须先通过 replay
参数版本必须写入每笔交易日志
```

---

# 43. 开发阶段路线图

## Phase 1：安全底座

```text
项目目录
配置系统
数据库
Event Sourcing
Execution FSM
Telegram /pause /resume /kill_all
Risk Engine 骨架
```

## Phase 2：数据底座

```text
Exchange Gateway
Market Data Buffer
CVD
OI
Funding
Orderbook
Reconciliation
```

## Phase 3：风控底座

```text
No-Trade Gate
Circuit Breaker
Account Life Tier
Liquidity Filter
Execution Protection
```

## Phase 4：Replay / Monitoring

```text
Replay Engine
Monitoring
Incident Runbook
Test Matrix
```

## Phase 5：Scanner / Confirmation

```text
Pre-Anomaly
Anomaly
Real Trade Confirmation
Manipulation Detector
```

## Phase 6：Strategy / State Machine

```text
Breakout Momentum
Liquidation Reversal
Opportunity Grading
State Machine
```

## Phase 7：Capital / Tail

```text
Capital Flow Engine
Profit Harvest
Capital Rebase
Tail Manager
Right Tail Amplification
```

## Phase 8：LLM

```text
DeepSeek API
Prompt
Schema
Guardrails
Cache
```

## Phase 9：Paper Trading

```text
L0
L1
L2
```

## Phase 10：Limited Live

```text
L3
L4
L5
```

---

# 44. 最终验收标准

## 44.1 工程验收

```text
全部核心模块有单元测试
关键流程有集成测试
Replay 可复现
数据库可重建
异常可保护
Telegram 可控制
```

## 44.2 风控验收

```text
无幽灵仓位
无无止损仓位
无重复下单
无未知订单
无 LLM 越权
无未授权 Telegram 指令
```

## 44.3 交易验收

```text
Paper trading >= 14 天
所有强制退出可解释
所有亏损可归因
所有提现 Rebase 正确
所有资金统计正确
```

---

# 45. Kiro 实施顺序与禁止事项

## 45.1 Kiro 第一轮只做

```text
requirements.txt
项目目录
配置系统
数据库 schema
Event Sourcing
Execution FSM
Telegram 基础控制
Risk Engine 骨架
Monitoring 骨架
测试框架
```

## 45.2 第一轮禁止

```text
禁止写自动盈利策略
禁止接入右尾放大
禁止 live trading
禁止复杂 LLM
禁止 RL
禁止多 Agent
```

## 45.3 第二轮再做

```text
Exchange Gateway
Market Data Buffer
Reconciliation
Replay
No-Trade Gate
```

## 45.4 第三轮再做

```text
Scanner
Liquidity
Real Trade Confirmation
Manipulation Detector
State Machine
```

## 45.5 第四轮再做

```text
Strategy
LLM
Capital Flow
Tail Manager
Paper Trading
```

---

# 46. 附录：核心枚举

## 46.1 TradeState

```text
NO_TRADE
OBSERVE
SCOUT
CONFIRM
ATTACK
RIGHT_TAIL_AMPLIFY
LOCK_PROFIT
DISTRIBUTION_ALERT
FORCED_EXIT
```

## 46.2 OpportunityGrade

```text
S
A
B
C
D
```

## 46.3 ManipulationLevel

```text
M0
M1
M2
M3
```

## 46.4 TradeConfirmationLevel

```text
T0
T1
T2
T3
T4
```

## 46.5 TradingMode

```text
READ_ONLY
PAPER
MANUAL_CONFIRM
LIVE_LIMITED
LIVE_FULL
```

## 46.6 IncidentLevel

```text
P0
P1
P2
P3
```

---

# 47. 最终结论

AMA-RT V1.4 是一份生产级实施规格书。

Kiro 必须按以下原则落地：

```text
先活下来，再进攻，再放大。
先保证系统不失控，再追求右尾收益。
先完成执行、风控、回放、对账，再接策略和 LLM。
```

最终系统不是印钞机，而是：

```text
有限生命账户里的极端右尾捕获机器。
```

系统性格：

```text
平时像狙击手一样等待；
机会出现时像疯狗一样进攻；
错误发生时像杀手一样止损；
盈利扩大时像赌徒一样保留尾仓；
但绝不能像赌徒一样下注。
```

