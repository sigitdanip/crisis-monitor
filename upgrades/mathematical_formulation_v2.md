# Crisis Monitor — Mathematical Formulation v2

This document supersedes `mathematical_formulation.md` (v1). It defines the complete mathematical and logical framework of the daily pipeline: from raw indicator inputs through stale-data decay, convexity scoring, intra-category RSS aggregation, locked-denominator composite scoring, coupling-matrix pathway activation, Bayesian multi-agent synthesis, and end-state assessment.

---

## 1. Indicator Thresholds & Registry

The system tracks **30 indicators** across **8 categories**. Each indicator is evaluated against baseline ($T_{base}$), breach ($T_{breach}$), and critical ($T_{crit}$) thresholds. For numeric indicators without an explicit baseline:

$$T_{base} = T_{breach} \times 0.70$$

### Category Weights ($W_{cat}$)

The sum of all category weights is **locked at 9.9** (used in Section 3).

| Category | $W_{cat}$ | Category | $W_{cat}$ |
| :--- | :--- | :--- | :--- |
| **Energy** | 1.5 | **Supply Chain** | 1.3 |
| **Financial** | 1.4 | **Currency** | 1.2 |
| **Geopolitical** | 1.4 | **Economic** | 1.0 |
| **Food** | 1.3 | **Metals** | 0.8 |
| | | **Total** | **9.9** |

### Complete Indicator Thresholds Table

Changes from v1 are marked **[UPDATED]**.

| Category | Slug | Name | Unit | Type | $T_{base}$ | $T_{breach}$ | $T_{crit}$ | Direction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Energy** | `brent_oil` | Brent Oil Price | USD/bbl | Numeric | 75.0 | 90.0 | 110.0 | High worse |
| | `wti_oil` | WTI Oil Price | USD/bbl | Numeric | 70.0 | 85.0 | 105.0 | High worse |
| | `eu_gas_storage` | EU Gas Storage | % | Numeric | 85.0 | 70.0 | 60.0 | Inverted |
| | `natgas_henry_hub` | NatGas Henry Hub | USD/MMBtu | Numeric | 3.0 | 4.5 | 7.0 | High worse |
| **Food** | `fao_food_price_index` | FAO Food Index | Index | Numeric | **125.0** | **140.0** | **155.0** | High worse **[UPDATED]** |
| | `wheat_futures` | Wheat Futures | USD/bu | Numeric | 5.50 | 7.50 | 9.00 | High worse |
| | `corn_futures` | Corn Futures | USD/bu | Numeric | 4.00 | 5.50 | 7.00 | High worse |
| | `rice_price` | Rice Price | USD/cwt | Numeric | 14.0 | 16.0 | 20.0 | High worse |
| **Economic** | `us_ism_manufacturing` | US ISM Mfg | Index | Numeric | 50.0 | 47.0 | 45.0 | Inverted |
| | `china_caixin_pmi` | China Caixin PMI | Index | Numeric | 50.0 | 48.0 | 46.0 | Inverted |
| | `eurozone_manufacturing_pmi` | Eurozone Mfg PMI | Index | Numeric | 50.0 | 47.0 | 45.0 | Inverted |
| | `us_jobless_claims` | US Jobless Claims | Thousands | Numeric | 230.0 | 280.0 | 320.0 | High worse |
| **Financial** | `vix` | VIX Volatility | Index | Numeric | 15.0 | 25.0 | 35.0 | High worse |
| | `move_bond_volatility` | MOVE Volatility | Index | Numeric | 90.0 | 120.0 | 150.0 | High worse |
| | `ted_spread` | TED Spread | Bps | Numeric | 20.0 | 50.0 | 80.0 | High worse |
| | `credit_spread` | Credit Spread (BBB-10Y) | Bps | Numeric | 120.0 | 200.0 | 300.0 | High worse |
| **Currency** | `dxy_index` | DXY Dollar Index | Index | Numeric | 100.0 | 105.0 / 95.0 | 110.0 / 90.0 | Two-Sided |
| | `eur_usd` | EUR/USD Rate | Rate | Numeric | 1.10 | 1.15 / 1.05 | 1.20 / 1.00 | Two-Sided |
| | `usd_cny` | USD/CNY Rate | Rate | Numeric | 7.00 | 7.20 | 7.40 | High worse |
| **Metals** | `gold_price` | Gold Price | USD/oz | MA Dev | MA 200 | +15% | +25% | Deviation |
| | `copper_price` | Copper Price | USD/lb | Numeric | **6.00** | **7.50** | **9.00** | High worse **[UPDATED]** |
| | `silver_price` | Silver Price | USD/oz | Numeric | **55.0** | **65.0** | **75.0** | High worse **[UPDATED]** |
| **Supply Chain** | `baltic_dry_index` | Baltic Dry Index | Index | Numeric | **2500.0** | **3200.0** | **4000.0** | High worse **[UPDATED]** |
| | `scfi` | SCFI Container Index | Index | Numeric | 2000.0 | 3000.0 | 4000.0 | High worse |
| | `hormuz_strait` | Hormuz Strait Status | Enum | Enum | — | — | — | Enum Mapping |
| | `taiwan_strait_tension` | Taiwan Strait Tension | Enum | Enum | — | — | — | Enum Mapping |
| **Geopolitical** | `russia_ukraine_conflict` | Russia-Ukraine Level | Enum | Enum | — | — | — | Enum Mapping |
| | `middle_east_conflict` | Middle East Level | Enum | Enum | — | — | — | Enum Mapping |
| | `china_taiwan_tension` | China-Taiwan Tension | Enum | Enum | — | — | — | Enum Mapping |
| | `global_terrorism_index` | Global Terror Index | Index | Numeric | 4.5 | 6.0 | 7.5 | High worse |

---

## 2. Indicator-Level Scoring ($S_{ind}$)

Each indicator produces a score $S_{ind} \in [0.0, 1.0]$.

### 2.1 Stale Data Decay

Before applying any threshold logic, check the data freshness status. If an indicator is **stale or unavailable**, bypass threshold math entirely and apply an hourly uncertainty penalty:

$$S_{ind}(t) = \min\!\left( S_{ind,\text{last\_known}} + \alpha_{cat} \cdot t,\ 1.0 \right)$$

where $t$ is the number of hours since last known value and $\alpha_{cat}$ is a category-specific decay rate. This drives uncertainty risk upward over time rather than holding a stale value static.

### 2.2 Convexity Exponent ($p = 2$)

All **live numeric indicators** apply a squared power function ($p=2$) to flatten normal market noise and accelerate the score as values approach breach and critical thresholds.

#### A. One-Sided (Higher is Worse)

For indicators where higher values denote higher distress (e.g. `brent_oil`, `vix`, `us_jobless_claims`):

$$S_{ind} = \begin{cases}
0.0 & x \le T_{base} \\[6pt]
0.5 \times \left(\dfrac{x - T_{base}}{T_{breach} - T_{base}}\right)^{2} & T_{base} < x \le T_{breach} \\[10pt]
0.5 + 0.5 \times \left(\dfrac{x - T_{breach}}{T_{crit} - T_{breach}}\right)^{2} & T_{breach} < x \le T_{crit} \\[10pt]
1.0 & x > T_{crit}
\end{cases}$$

#### B. One-Sided Inverted (Lower is Worse)

For indicators where lower values denote higher distress (e.g. `eu_gas_storage`, `china_caixin_pmi`):

$$S_{ind} = \begin{cases}
0.0 & x \ge T_{base} \\[6pt]
0.5 \times \left(\dfrac{T_{base} - x}{T_{base} - T_{breach}}\right)^{2} & T_{breach} \le x < T_{base} \\[10pt]
0.5 + 0.5 \times \left(\dfrac{T_{breach} - x}{T_{breach} - T_{crit}}\right)^{2} & T_{crit} \le x < T_{breach} \\[10pt]
1.0 & x < T_{crit}
\end{cases}$$

#### C. Two-Sided (Both Extremes are Worse)

For indices where both significant expansion and contraction denote distress (e.g. `dxy_index`, `eur_usd`):

$$T_{base\_center} = \frac{T_{breach\_lower} + T_{breach\_upper}}{2}$$

$$S_{ind} = \max\!\left( S_{upper}(x),\ S_{lower}(x) \right)$$

where $S_{upper}$ applies one-sided higher-is-worse logic with baseline $T_{base\_center}$, and $S_{lower}$ applies one-sided inverted logic with baseline $T_{base\_center}$. The convexity exponent ($p=2$) applies to both sub-scores.

#### D. Gold 200-Day Moving Average Deviation

$$D = \frac{P - MA_{200}}{MA_{200}}$$

| Zone | Condition | Formula |
| :--- | :--- | :--- |
| Normal | $D \le 0.05$ | $S_{gold} = 0.0$ |
| Approaching Breach | $0.05 < D \le 0.15$ | $S_{gold} = 0.5 \times \left(\dfrac{D - 0.05}{0.10}\right)^{2}$ |
| Approaching Critical | $0.15 < D \le 0.25$ | $S_{gold} = 0.5 + 0.5 \times \left(\dfrac{D - 0.15}{0.10}\right)^{2}$ |
| Critical | $D > 0.25$ | $S_{gold} = 1.0$ |

#### E. Non-Numeric Enum Mappings

Enum indicators map qualitative labels directly to $S_{ind}$. The convexity exponent does **not** apply.

| Indicator | Label → Score | Label → Score | Label → Score | Label → Score |
| :--- | :--- | :--- | :--- | :--- |
| `hormuz_strait` | normal → 0.0 | elevated → 0.3 | threatened → 0.7 | closure → 1.0 |
| `taiwan_strait_tension` | normal → 0.0 | monitored → 0.2 | elevated → 0.6 | high → 1.0 |
| `russia_ukraine_conflict` | normal → 0.0 | ongoing → 0.3 | escalation → 0.7 | major → 1.0 |
| `middle_east_conflict` | normal → 0.0 | localized → 0.3 | regional → 0.7 | widespread → 1.0 |
| `china_taiwan_tension` | normal → 0.0 | elevated → 0.6 | critical → 1.0 | — |

---

## 3. Composite Score Aggregation ($C$)

Aggregation now uses a **two-layer** approach to prevent double-counting correlated indicators within the same category.

### Layer 1: Intra-Category Aggregation (Normalized RSS)

For each category $k$ with $n_k$ available indicators, compute a single category score using Normalized Root-Sum-Square:

$$S_{cat,k} = \sqrt{\frac{\sum_{i=1}^{n_k} S_{ind,i}^{2}}{n_k}}$$

This suppresses artificial score inflation when correlated indicators (e.g. Brent and WTI) respond to the same shock simultaneously.

### Layer 2: Final Composite Calculation (Locked Denominator)

The total weight denominator is **locked at 9.9**, ensuring $C$ scales perfectly to the 30-point range regardless of how many categories have available data:

$$C = \text{round}\!\left( \frac{\displaystyle\sum_{k \in \mathcal{A}} S_{cat,k} \times W_{cat,k}}{9.9} \times 30.0,\ 1 \right)$$

where $\mathcal{A}$ is the set of categories that are **not** fully offline (at least one indicator with live or stale-decayed data).

### Data Blackout & Circuit Breaker Logic

Stale indicators apply the decay formula from Section 2.1 and contribute their decayed $S_{ind}$ into Layer 1 normally.

However, if the combined weight of **completely offline** categories exceeds **4.0** (~40.4% of total system weight):

1. Set dashboard state to **INDETERMINATE**
2. Freeze the composite score calculation
3. Trigger a **System Telemetry Alarm**
4. **Bypass automated pathway execution**

### Zone Interpretations

| Zone | Range |
| :--- | :--- |
| Normal | $C \in [0, 6)$ |
| Monitor | $C \in [6, 12)$ |
| Elevated | $C \in [12, 20)$ |
| Alert | $C \in [20, 25)$ |
| Critical | $C \in [25, 30]$ |

---

## 4. Alerts Engine Logic

### Status Classifications

$$Flag = \begin{cases}
\text{NORMAL} & S_{ind} = 0.0 \\
\text{BREACHED} & 0.0 < S_{ind} < 1.0 \\
\text{CRITICAL} & S_{ind} = 1.0
\end{cases}$$

### Cooldown De-duplication Rule

An alert is only written to the database if no entry with the same composite key exists within the previous 24 hours:

$$\text{Key} = \text{Category} + \text{Indicator} + \text{Flag}$$

---

## 5. Dynamic Pathway Activation (Agent 6)

### 5.1 Pathway Definitions

| Pathway | Name | Causal Chain | Primary Dots |
| :--- | :--- | :--- | :--- |
| **A** | Monetary Cascade | Credit tightening → liquidity crisis → sovereign stress → recession | 4, 5 |
| **B** | Energy Price Shock | Energy disruption → price spikes → food surge → social unrest → government crisis | 1, 2, 3 |
| **C** | Geopolitical Fracture | Alliance breakdown → trade fragmentation → capital flight → regional crisis → spillover | 6, 4 |
| **D** | Systemic Collapse | Pathways A + B + C activating simultaneously | All |

### 5.2 The Coupling Matrix ($M$)

To capture cross-sector cascade effects, a **Coupling Matrix** primes dependent category scores based on distress in linked influencer categories, without creating false alarms.

The activation metric $A_k$ for pathway $k$ is:

$$A_k = \sum_{i \in \mathcal{P}_k} S_{cat,i} + \sum_{j \notin \mathcal{P}_k} \left( M_{i,j} \times S_{cat,j} \right)$$

where:
- $S_{cat,i}$: base category score for pathway-member category $i$
- $M_{i,j}$: coupling coefficient from influencer $j$ to dependent $i$ (cap: **0.15**)

**Design constraints:**

- **Unidirectional DAG**: The matrix follows a strict Directed Acyclic Graph structure to prevent feedback loops ("hall of mirrors" effect).
- **Cap**: Maximum external influence per category is capped at **0.15**.
- **Traceability**: Logs must explicitly record: `Triggered: Base (S_i) + Coupling (M_{i,j} * S_j)`.

### 5.3 Pathway D Activation Rule

Pathway D can only be marked active if **at least two** of Pathways A, B, or C are active.

### 5.4 Fallback Heuristics (LLM Failure)

If the LLM synthesis fails or times out, the system falls back to deterministic rules based on $C$:

| Condition | Pathway Activated |
| :--- | :--- |
| $C \ge 20$ | Pathway D |
| $C \ge 12$ or Pathway D active | Pathways A, B, C |

---

## 6. Multi-Agent Response Orchestration

### 6.1 Hierarchical Architecture

| Role | Function | Output |
| :--- | :--- | :--- |
| **Specialist Agents** (Dot Analyzers 1–5) | Category-constrained workers | `Risk_Assessment_Object` {Evidence, Certainty_Score, Confidence_Level} |
| **Orchestrator / CIO** (Agent 6 — Pathway Synthesizer) | Synthesizes specialist reports into a Systemic Verdict | $V$ |
| **Meta-Agent** | Resolves internal agent conflicts autonomously | Revised $V$ |

### 6.2 Bayesian Synthesis

The Orchestrator computes a weighted consensus verdict to avoid harsh tie-breaking:

$$V = \frac{\displaystyle\sum_{k} \left( Report_k \times W_k \times C_k \right)}{\displaystyle\sum_{k} \left( W_k \times C_k \right)}$$

where $W_k$ is the authority weight of specialist agent $k$ and $C_k$ is its reported confidence score.

### 6.3 Divergence Resolution (Zero-Human Loop)

When specialist reports diverge beyond an acceptable threshold:

1. No human halt is triggered.
2. The **Meta-Agent** is initialized to perform root-cause analysis on the conflict.
3. The Meta-Agent outputs a revised Systemic Verdict $V'$ that reconciles the divergent data.

### 6.4 Tiered Dissemination

| Tier | Name | Trigger Condition | Action |
| :--- | :--- | :--- | :--- |
| 1 | Status | Always | Passive dashboard update |
| 2 | Digest | Pathway activation metric $A_k > 0.6$ | Contextual summary |
| 3 | Intervention | $C > 20.0$ or Circuit Breaker fired | Direct actionable recommendation |

---

## 7. End State Assessment (Agent 7)

### 7.1 Boundary Conditions

The model must respect strict mathematical boundary conditions in the following priority order:

$$\text{EndState} = \begin{cases}
\text{systemic\_collapse} & C \ge 25 \quad \text{or} \quad \left( C \ge 20 \land \text{Pathway D active} \right) \\[6pt]
\text{fragmented\_stability} & 12 \le C < 25 \quad \land \quad \text{any Pathway active} \\[6pt]
\text{containment} & C < 6 \quad \text{or} \quad \text{all Pathways inactive}
\end{cases}$$

### 7.2 Confidence Constraints

$$P(\text{confidence}) \in [0.85,\ 0.95]$$

### 7.3 Global Recession Probability $P(\text{recession})$

The 6-month recession probability is bounded strictly by the composite score:

| $C$ Range | $P(\text{recession})$ |
| :--- | :--- |
| $C < 6$ | $< 0.15$ |
| $6 \le C < 12$ | $[0.15,\ 0.35]$ |
| $12 \le C < 20$ | $[0.35,\ 0.60]$ |
| $C \ge 20$ | $> 0.60$ |

---

## 8. Historical Backtesting & Validation

### 8.1 Sliding Window (Walk-Forward) Methodology

To prevent overfitting, all parameter validation uses a rolling 12-month window:

1. Run backtest on a 12-month slice (e.g. 2020–2021).
2. Slide window forward by 1 month.
3. Validate weights and coupling coefficients against out-of-sample data.

### 8.2 Success Metrics

| Metric | Definition | Target |
| :--- | :--- | :--- |
| Lead Time ($T_{lead}$) | $T_{trigger} - T_{crash}$ | $> 0$ |
| False Positive Rate (FPR) | Fraction of alerts without subsequent crisis | $< 10\%$ |
| Sensitivity Drift | Rate of weight adjustment needed to maintain accuracy | Minimize |

### 8.3 Autonomous Feedback Loop (Zero-Human Loop)

Every quarter, the system runs an **Auto-Backtest**:

1. If $T_{lead} \le 0$, the Meta-Agent initiates weight recalibration.
2. Recalibrated $W_{cat}$ and $M_{i,j}$ values are tested against the previous 3 months of data.
3. If results improve (higher $T_{lead}$, lower FPR), parameters update automatically.

---

## Appendix: Key Formula Reference

| Formula | Description |
| :--- | :--- |
| $S_{ind}(t) = \min(S_{last} + \alpha_{cat} \cdot t,\ 1.0)$ | Stale data decay |
| $S_{ind} = 0.5 \times \left(\frac{x - T_{base}}{T_{breach} - T_{base}}\right)^2$ | Convex scoring, pre-breach zone |
| $S_{cat} = \sqrt{\frac{\sum S_{ind,i}^2}{n}}$ | Intra-category normalized RSS |
| $C = \text{round}\!\left(\frac{\sum S_{cat} \times W_{cat}}{9.9} \times 30,\ 1\right)$ | Composite score (locked denominator) |
| $A_k = \sum_{i \in \mathcal{P}_k} S_i + \sum_{j} M_{i,j} \times S_j$ | Pathway activation metric with coupling |
| $V = \frac{\sum Report_k \times W_k \times C_k}{\sum W_k \times C_k}$ | Bayesian systemic verdict |