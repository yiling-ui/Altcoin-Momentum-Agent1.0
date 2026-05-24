[AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM_deduped.md](https://github.com/user-attachments/files/28188951/AMA_RT_ADAPTIVE_MARKET_OPERATING_SYSTEM_deduped.md)
# AMA-RT Adaptive Market Operating System Governance
# 自适应市场操作系统架构治理文档

> **Status:** Guidance-only architecture governance document.
> **Authority:** Long-term architectural principles + AI safety
> rails. **NOT** a phase implementation, **NOT** a runtime
> behavior change, **NOT** a phase-gate transition.
> **Scope of this PR:** docs-only.
>
> This document does **NOT** authorise any runtime behavior,
> any new phase, any new code path, any new event, any new
> configuration flag, any new exchange call, any new LLM
> call, any new Telegram outbound message, any new exchange
> private endpoint, or any change to the Phase 1 safety lock.
> It records architectural intent for future planning and
> review. It is binding as governance, not as implementation.

---

## 0. Document Purpose

This document records the AMOS core goal, anti-corruption governance, AI authority boundary, and long-term architecture rails for AMA-RT. It is guidance-only and does not change any phase gate or runtime behavior.

## 1. Final System Positioning

AMA-RT is not an auto-trading bot.

AMA-RT is an Adaptive Market Operating System.

AMA-RT 的最终目标不是预测价格，也不是追求低波动稳定收益，而是：

* 长期稳定运行；
* 持续理解市场结构变化；
* 动态识别不同市场状态；
* 限制系统性风险；
* 在不同 Regime 下切换 paper-only 风险表达方式；
* 在山寨市场真实流动性扩张阶段，尽可能早发现并捕捉真正的右尾机会。

“短期行情达到 5x+”是系统的进攻目标，不是收益承诺。
所有策略、评分、标签、AI 解释、cluster action、validation result 都必须服务于这个目标，但不能绕过 Phase Gate、Risk Engine、Execution FSM、Replay / Verification 和 Go / No-Go。

---

## 2. Core Operating Philosophy

### 2.1 The market is a dynamic adversarial system

市场不存在永久有效策略。

市场中的参与者结构、资金结构、流动性结构、叙事结构会持续变化。因此，固定策略最终一定会失效。

AMA-RT 不追求永恒 Alpha，而追求持续适应市场结构变化。系统真正要持续校准的是：

* 当前市场由谁推动；
* 资金是否真实进入；
* 承接是否持续；
* 流动性是否允许扩张；
* 右尾行情是否仍处在可参与阶段；
* 当前状态是否已经进入 late / blowoff / distribution / liquidity collapse。

### 2.2 Price can lie, liquidity is harder to fake

K 线、普通价格行为、短期拉盘、插针、洗盘、做市行为都可能被诱导或操纵。

AMA-RT 的核心研究对象不是“价格是否上涨”，而是：

* 是否有真实成交；
* 是否有真实承接；
* depth 是否支持继续扩张；
* spread 是否异常扩大；
* OI / Funding 是否健康；
* spot / perp 是否出现背离；
* CVD 是否支持趋势；
* 流动性是否正在向少数候选集中；
* 注意力是否正在转化为流动性。

系统必须优先研究真实市场结构，而不是单纯研究价格形态。

### 2.3 The system does not aim for stable small profits

AMA-RT 不以低波动稳定收益为核心目标。

AMA-RT 的研究目标是非稳定性右尾机会，包括：

* 山寨币暴力扩张阶段；
* 流动性快速聚集阶段；
* 高波动资金迁移阶段；
* Meme / narrative / beta 集中爆发阶段；
* 少数候选在短周期中形成极端 MFE 的阶段。

系统的目标是在可控风险下捕捉少量高质量右尾，而不是频繁交易、平均盈利或追求日常稳定小收益。

---

## 3. AI Authority Boundary

AI / LLM 永远不进入执行链。

AI 永远禁止：

* 下单；
* 平仓；
* 修改杠杆；
* 修改仓位；
* 修改止损；
* 修改目标价；
* 修改风险预算；
* 绕过 Risk Engine；
* 绕过 Execution FSM；
* 绕过 Phase Gate；
* 控制真实执行；
* 把自己的文本输出当成训练事实。

AI 只允许做：

* Market Intelligence；
* Narrative Interpretation；
* Regime Explanation；
* Structural Anomaly Explanation；
* Replay / Reflection summarisation；
* Evidence compression。

AI 不负责：

* Trade Execution；
* Position Sizing；
* Leverage Control；
* Stop Control；
* Final Trade Decision。

AI 的作用是帮助系统理解市场，不是替系统交易。

---

## 4. Stateless AI Cognition

LLM 不是长期稳定记忆体。

AI 推理必须无状态化。每次 AI 推理都必须基于结构化真实数据重新构建认知，而不是依赖聊天上下文、历史回答或自己的旧分析文本。

禁止：

* 把聊天上下文当成事实源；
* 把 previous assistant response 当成事实；
* 把 AI 自己过去的分析作为训练标签；
* 把未验证 narrative 当成 Truth；
* 把 Telegram 文案或 KOL 文案当成事实。

事实源优先级：

1. Exchange public market data；
2. EventRepository；
3. Replay / Export；
4. Structured reports；
5. Human-approved phase docs；
6. AI analysis text only as commentary, never truth。

---

## 5. Truth Layer

Truth Layer 是事实层。

核心原则：

事实数据不可修改。没有 Truth Layer 证据，不允许声称策略有效。

Truth Layer 必须记录：

Market facts:

* price；
* volume；
* OI；
* funding；
* spread；
* depth；
* liquidation；
* spot / perp divergence；
* stablecoin flow；
* candidate first_seen；
* MFE / MAE；
* tail_label。

System behavior:

* why candidate was promoted；
* why risk rejected；
* why system paused；
* why system degraded；
* strategy_mode；
* cluster context；
* risk rejection reason；
* report_id；
* opportunity_id；
* scan_batch_id。

Final outcome:

* trend continuation；
* fake breakout；
* dumped；
* missed tail；
* late chase failure；
* strong_tail / moderate_tail / weak_tail。

所有 AI 判断必须引用 Truth Layer 中的事实字段。
没有 Truth Layer 证据，不允许声称“某策略有效”“某 Regime 有优势”“某分数可以放大风险”。

---

## 6. Reality Check Layer

AI 不是事实来源。Strategy Selector 也不是事实来源。

所有 AI 输出和 Strategy Selector 结论都必须经过 Reality Check Layer 的硬规则验证。

如果 AI 判断“趋势健康”，但系统发现：

* spot volume 下降；
* funding 过热；
* spread 扩大；
* depth collapse；
* late_chase_risk 高；
* data stale / degraded；
* Risk Engine reject；

则 AI 结论必须降权、拒绝或进入 observe。

Reality Check 优先级高于 AI explanation。
Reality Check 优先级高于 Strategy Selector。
Reality Check 只能 downweight / reject / observe，不能触发真实交易。

---

## 7. Anti-Overfitting Governance

禁止：

* 根据少量样本自动放宽规则；
* 用单次妖币案例修改全局策略；
* 因历史样本拟合而提高杠杆或仓位；
* 根据 AI 文本标签优化交易参数；
* 让 validation result 自动改变 runtime strategy；
* 让 cluster action 自动改变真实仓位；
* 黑箱自动参数优化；
* 强化学习实盘探索。

所有策略调整必须经过：

* dataset sample count gate；
* validation quality gate；
* replay；
* paper-only shadow validation；
* human review；
* phase gate approval。

系统可以学习真实市场结果，但不能因为少量样本、单次暴涨或 AI 解释而自动改变交易行为。

---

## 8. Feedback Isolation

AI 不能学习自己的输出。

AI 只能学习真实市场结果。

允许学习的对象：

* MFE / MAE；
* tail_label；
* fake_breakout；
* missed_tail；
* late_chase_failure；
* risk rejection outcome；
* replay verified result。

禁止学习的对象：

* AI 自己的 narrative；
* AI 自己的 confidence；
* AI 过去的推测文本；
* Telegram 文案；
* KOL 主观观点；
* 未经验证的人工主观评价。

目的：防止 AI 自我强化、递归污染、上下文漂移和长期认知腐化。

---

## 9. Limited Complexity Governance

AMA-RT 的长期目标不是越来越复杂，而是越来越稳定、可解释、可验证、可恢复。

### 9.1 Prevent Layer Explosion

系统后期容易不断新增更多层、更多评分、更多过滤、更多 AI 推理，导致推理链过长，难以调试、归因、维护和验证。

新增任何层之前必须回答：

* 这一层是否真正增加市场理解？
* 这一层是否真正改善风险控制？
* 这一层是否改善 Replay / Decision Trace？
* 这一层是否只是增加复杂度？

如果无法回答，禁止新增。

### 9.2 Prevent Regime Explosion

系统后期容易无限新增更多 Regime、更多市场阶段、更多例外条件，导致 FSM 与 Regime 复杂度膨胀。

Regime 必须保持少量高抽象状态。

新增 Regime 必须满足：

* 存在明显不同的流动性结构；
* 存在明显不同的风险结构；
* 存在明显不同的策略适配；
* 能被 Truth Layer 和 Replay 验证。

AMA-RT 研究的是状态迁移，不是状态枚举。

### 9.3 Prevent Narrative Pollution

AI Narrative 容易逐渐文学化、情绪化、故事化，最终让系统变成市场评论系统。

AI 只允许输出可验证结构解释，例如：

* OI acceleration；
* depth weakening；
* spread expansion；
* spot / perp divergence；
* funding overheating；
* liquidity concentration；
* attention velocity increasing。

禁止输出不可验证叙事作为系统依据，例如：

* 市场疯狂；
* 资金信仰增强；
* 情绪崩溃；
* 主力意图明确；
* 社区共识强烈。

Narrative 不是交易信号。Narrative 只能作为市场流动性变化的辅助观察维度。

### 9.4 Prevent Research Loop

系统不能无限研究、无限扩展、无限抽象，最终永远停留在理论系统。

所有新增模块必须回答：

* 是否真正改变市场理解？
* 是否真正改善风险控制？
* 是否真正提高执行稳定性？
* 是否真正提高 Replay 质量？
* 是否真正帮助发现或验证右尾机会？

AMA-RT 允许删除模块。
系统长期目标是持续压缩复杂度。

### 9.5 Prevent AI Cognitive Corruption

AI 后期可能依赖自身输出、强化自身叙事、形成递归幻觉，最终偏离真实市场。

强制原则：

* AI 永远不学习自身文本输出；
* AI 只能学习真实市场结果；
* AI 不是系统真理来源；
* AI 只是市场理解辅助层；
* Truth Layer 和 Reality Check 永远优先于 AI 文本。

---

## 10. Attention & Narrative Flow

山寨市场中的右尾行情往往不仅来自资金流动，还来自注意力迁移。

交易所原生社交平台、热点标签、KOL 扩散、Meme 聚集、Launchpool 周期、AI 币热潮、链上热点迁移，都可能导致流动性快速聚焦。

AMA-RT 不研究“情绪”，而研究注意力如何影响流动性结构。

未来可以观察：

* Narrative Velocity：叙事传播速度、热点传播斜率、标签增长速度；
* Attention Concentration：市场注意力是否集中到少数币种；
* Narrative Saturation：是否进入过热传播、刷屏、KOL 一致化；
* Attention Decay：热点传播是否开始衰减。

强制限制：

* 禁止基于情绪文本直接交易；
* 禁止基于 KOL 观点直接交易；
* 禁止基于 AI 情绪总结直接交易；
* 禁止把 narrative score 作为真实下单依据。

正确用途：

* 辅助解释为什么注意力开始聚集；
* 辅助解释为什么流动性开始扩张；
* 辅助解释为什么 Meme Beta 开始提升；
* 辅助 Reality Check，而不是取代 Truth Layer。

未来接入 Binance Square、X / Twitter、Telegram、Discord、KOL feed 时，必须永远研究“传播结构”，而不是研究“观点内容”。

推动山寨右尾的不是“别人说了什么”，而是：

* 传播速度；
* 传播密度；
* 注意力集中度；
* 注意力向流动性的转换效率。

---

## 11. Long-Term Evolution Principle

AMA-RT 的真正进化不是：

* 增加更多 AI；
* 增加更多指标；
* 增加更多 Regime；
* 增加更多策略；
* 增加更多黑箱评分。

AMA-RT 的真正进化是：

* 提升市场结构理解质量；
* 提升状态识别能力；
* 提升风险适配能力；
* 提升系统可解释性；
* 提升真实市场锚定能力；
* 提升 Replay / Decision Trace 质量；
* 删除无效模块；
* 压缩复杂度；
* 保持长期稳定运行。

最终守则：

AMA-RT 必须长期保持：

* 稳定骨架；
* 动态智能；
* 有限复杂度；
* 强可解释性；
* 真实市场锚定；
* AI 只读；
* Risk Engine 最高裁决；
* Execution FSM 状态一致；
* Replay 可验证；
* Phase Gate 不可绕过。

---

## 12. Final Definition

AMA-RT 的最终目标不是预测市场。

AMA-RT 的最终目标是：

持续理解市场结构变化，动态适配市场状态，限制系统性风险，在不同 Regime 下切换风险表达，并在真实流动性扩张阶段捕捉山寨市场中的右尾机会。

短期 5x+ 是进攻目标，不是收益承诺。

任何系统升级、策略修正、AI 接入、数据扩展、风险调节、cluster 控制、validation gate，都必须服务于：

* 长期稳定运行；
* 捕捉山寨最肥右尾；
* 防止 AI 幻觉造成资金损害；
* 防止复杂度失控；
* 防止过拟合；
* 防止黑箱决策；
* 防止绕过安全边界。

---

## 13. Architecture Layers and Trade Authority

The conceptual layering of AMA-RT is recorded below. This
section is **descriptive of intent**, not prescriptive of
new code. Each layer is annotated with current state.

### Layer index (top-down)

| # | Layer                          | Trade authority |
|---|--------------------------------|-----------------|
| 1 | Observation Layer              | NONE            |
| 2 | Market Intelligence Layer      | NONE            |
| 3 | Regime Engine                  | NONE            |
| 4 | Strategy Orchestrator          | NONE (paper)    |
| 5 | Risk Allocation Engine         | **GATE**        |
| 6 | Execution FSM                  | **GATE**        |
| 7 | Replay / Verification Layer    | NONE            |
| 8 | Truth Layer                    | NONE (substrate)|
| 9 | Reality Check Layer            | DOWNWEIGHT      |

Only layers 5 and 6 are trade-decision gates. **No other
layer may directly authorise a trade.** No AI / LLM may
authorise a trade at any layer.

### Layer state today

  - **Observation Layer.** Partially implemented:
    Binance public REST + public WS via `app/exchanges/`,
    `MarketDataBuffer`, the Phase 11C.1A rate-limit
    governor, the Phase 11C.1B WS-first all-market radar,
    the `SymbolUniverse` / exchangeInfo-as-truth contract.
    Trade authority: **NONE**.
  - **Market Intelligence Layer.** Partially implemented:
    `app/adaptive/cluster.py`, `app/adaptive/context.py`,
    candidate scoring, the Phase 11C.1C-B runtime
    calibration block (15 fields), early-tail discovery.
    Narrative / liquidity / cross-exchange / lead-lag /
    bot-amplification / iceberg-spoof intelligence are
    **NOT** implemented (see §14). Trade authority:
    **NONE**.
  - **Regime Engine.** Partially implemented:
    `app/adaptive/regime.py`,
    `app/adaptive/strategy_validation.py` cohort
    aggregation. Regime *transition prediction* is **NOT**
    implemented (see §14). Trade authority: **NONE**.
  - **Strategy Orchestrator.** Partially implemented:
    `app/adaptive/selector.py`,
    `app/adaptive/scoring.py`, `app/adaptive/stage.py`,
    Phase 11C.1C-A strategy selector contracts. Output is
    paper / virtual `strategy_mode` only. Trade authority:
    **NONE (paper)**.
  - **Risk Allocation Engine.** Implemented as the existing
    Risk Engine + no-trade gate (Phase 7). The Risk Engine
    is the *single* trade-decision gate. Trade authority:
    **GATE**.
  - **Execution FSM.** Implemented (Phase 9 — paper
    today). The FSM is the second gate; orders never reach
    the exchange except via this FSM, and today it is
    paper-only. Trade authority: **GATE**.
  - **Replay / Verification Layer.** Partially implemented:
    Phase 10A replay engine substrate, Phase 10B reflection
    + replay (read-only), Phase 8.5 export, Phase
    11C.1C-C-B-B-A dataset replay. Trade authority:
    **NONE**.
  - **Truth Layer.** Implemented as `EventRepository` /
    events.db / Phase 8.5 learning-ready payload. Trade
    authority: **NONE (substrate)**.
  - **Reality Check Layer.** Partially implemented as the
    Risk Engine veto reasons, manipulation detector,
    `late_chase_risk`, `ws_stale_count`, HTTP 429 / 418
    handling. A first-class *AI Reality Check Scoring*
    layer is **NOT** implemented (see §14). Trade
    authority: **DOWNWEIGHT** (and it never *grants*
    authority; it can only *withhold* it).

This document does **not** create any of the above. It
records the layering and the trade-authority annotation.

---

## 14. Future Backlog / Not Implemented Yet

The following capabilities are **not implemented**, are
**not authorised**, and **must not be claimed as shipped**
in any current phase doc, PR description, daily report,
Telegram message, or AI narrative.

| # | Capability                                | status         | trade_authority |
|---|-------------------------------------------|----------------|-----------------|
|  1 | Regime Transition Prediction             | NOT_STARTED    | NONE            |
|  2 | Liquidity Intelligence                   | NOT_STARTED    | NONE            |
|  3 | Market Structure Memory                  | NOT_STARTED    | NONE            |
|  4 | Narrative Acceleration                   | FUTURE_RESEARCH| NONE            |
|  5 | Social Saturation                        | FUTURE_RESEARCH| NONE            |
|  6 | Bot Amplification (detection)            | FUTURE_RESEARCH| NONE            |
|  7 | Cross-exchange Flow                      | NOT_STARTED    | NONE            |
|  8 | Lead-lag Relationships                   | NOT_STARTED    | NONE            |
|  9 | Spot / perp Divergence                   | NOT_STARTED    | NONE            |
| 10 | Stablecoin Inflow                        | NOT_STARTED    | NONE            |
| 11 | Iceberg / Spoof Detection                | FUTURE_RESEARCH| NONE            |
| 12 | Narrative-aware Cluster Taxonomy         | FUTURE_RESEARCH| NONE            |
| 13 | AI Market Intelligence Layer             | FUTURE_RESEARCH| NONE            |
| 14 | AI Interpretation Sandbox                | FUTURE_RESEARCH| NONE            |
| 15 | AI Reality Check Scoring                 | FUTURE_RESEARCH| NONE            |

Rules for this backlog:

  - **No item above may be claimed as shipped.** Any PR /
    report / Telegram message / AI narrative that says
    "AMA-RT does X" where X is in this table is **wrong**
    and must be corrected before merge.
  - **No item above grants trade authority.** When (and
    only when) an item is later promoted to a phase, the
    promotion must follow §7 (Anti-Overfitting Governance)
    and §17 (Phase / Status / Changelog discipline).
  - **No item above bypasses the Risk Engine or Execution
    FSM.** Items 13 / 14 / 15 (the AI-flavoured ones) are
    explicitly subject to §3 (AI Authority Boundary).

---

## 15. Explicit Rejections

The following are **permanently** rejected by this
governance document. Any future PR proposing them must be
rejected at review unless this document is first updated
with explicit human approval.

  - **AI autonomous trading.** AI never holds trade
    authority.
  - **AI direct price prediction.** The system's job is
    structural understanding, not next-bar guessing; AI
    output framed as "price will go to X" is rejected.
  - **Reinforcement learning in live trading.** RL on a
    live order book is rejected.
  - **Black-box parameter optimisation.** Optimisers that
    mutate runtime knobs without §7's six-gate process are
    rejected.
  - **Infinite auto-optimisation.** No background loop may
    self-tune without human approval and phase-gate
    acceptance.
  - **AI bypassing the Risk Engine.** Any path where AI
    output reaches an order without going through the Risk
    Engine is rejected.
  - **AI modifying leverage / size / stop-loss / target.**
    See §3.
  - **Direct jump to Phase 12.** Phase 12 is reachable only
    via Spec §41 Go/No-Go and only via the standard
    phase-gate progression.

---

## 16. Link to Current Phase

This document is published while the repository is in the
**Phase 11C paper-only second half**. Specifically:

  - The repository has accepted Phase 11C.1A, Phase 11C.1B,
    Phase 11C.1C-A, Phase 11C.1C-B, Phase 11C.1C-C-A, and
    Phase 11C.1C-C-B-A.
  - Phase 11C.1C-C-B-B-A is currently `IN_REVIEW` (PR #44).
  - Current work focus is **validation / dataset / quality
    gate / replay verification**, not new runtime
    capability.
  - **Phase 12 (real money / live trading) remains
    FORBIDDEN.**

This governance document:

  - Does **not** change any phase gate.
  - Does **not** authorise any runtime behavior.
  - Does **not** flip any safety flag.
  - Does **not** advance Phase 11C.1C-C-B-B-A to ACCEPTED.
  - Does **not** kick off Phase 11C.1C-C-B-B-B.
  - Does **not** authorise live trading, API keys, signed
    endpoints, private WebSockets, `listenKey`, DeepSeek
    trade decisions, real Telegram outbound, or Phase 12.

It is **guidance-only**, binding as architectural intent.

For the authoritative phase ledger see `docs/PHASE_GATE.md`
and `docs/PROJECT_STATUS.md`.

---

## 17. Update PROJECT_STATUS / PHASE_GATE / CHANGELOG

The companion edits to `docs/PROJECT_STATUS.md`,
`docs/PHASE_GATE.md`, and `docs/CHANGELOG.md` shipped in
this PR record only the following:

  - A new **architecture governance document** has been
    added (this file).
  - The new document is **guidance-only**.
  - The new document **does not change the current phase**.
  - The new document **does not change any safety flag**.
  - The new document **does not authorise Phase 12**.

No phase entry is flipped, no acceptance evidence is added,
no new event is plumbed, no new code path is created, no
new test is added.

---

## 18. Safety Boundary

The Phase 1 safety lock and every Phase 11C.1B / 11C.1C-A /
11C.1C-B / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A
forbidden item carry over **unchanged** under this
document. Specifically, the following must hold and are
**not** modified by this PR:

```
mode                            = paper
live_trading                    = False
exchange_live_orders            = False
right_tail                      = False
llm                             = False
telegram_outbound_enabled       = False
binance_private_api_enabled     = False
```

In addition:

  - **No Binance API key.**
  - **No Binance API secret.**
  - **No signed endpoint** call.
  - **No account / order / position / leverage / margin
    endpoint** call.
  - **No private WebSocket** subscription.
  - **No `listenKey`** / user data stream.
  - **No DeepSeek trade decision.**
  - **No real Telegram outbound.**
  - **Phase 12 remains FORBIDDEN.**

If any future PR — including future PRs that *cite this
document* — appears to weaken any of the above, that PR is
out of scope for this document and must be rejected at
review unless this document and the Phase 1 safety lock are
both first amended via human-approved phase-gate work.

---

## Appendix A. Document classification

  - **Type:** Architecture governance.
  - **Authority:** Long-term, binding.
  - **Scope of this PR:** docs-only.
  - **Runtime effect:** none.
  - **Phase effect:** none.
  - **Safety flag effect:** none.
  - **Trade authority granted:** none.
  - **Phase 12 status:** FORBIDDEN (unchanged).

## Appendix B. Reading order for new contributors

  1. `docs/PROJECT_STATUS.md` — what phase we're in.
  2. `docs/PHASE_GATE.md` — the authoritative phase ledger.
  3. `docs/AMA_RT_V1_4_Production_Spec_Kiro.md` — the
     production spec (incl. §41 Go/No-Go).
  4. **This document** — the architectural rails.
  5. The relevant `docs/PHASE_*.md` for the current open
     phase.

If a contributor's PR appears to conflict with this
document, the PR is wrong by default and must either be
revised or this document must be amended *first* via a
separate, human-approved governance PR.
