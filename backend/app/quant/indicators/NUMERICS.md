<!-- GENERATED FILE. Do not edit by hand.
     Regenerate with: python tests/quant/generate_numerics.py
     The per-indicator entries below are rendered from the IndicatorSpec
     records in this package, so the document and the engine cannot
     disagree. Edit the spec, then regenerate. -->

# Indicator numerics (WP5, Section 14)

Section 14 requires each indicator to document its formula, input price,
adjustment convention, warm-up period, missing-value behaviour, comparison
reference, and numerical tolerance. Those seven attributes are required
fields on `IndicatorSpec`, are rendered per indicator below, and are
enforced by `tests/quant/test_documentation.py`.

## Conventions that apply to every indicator

**Purity.** No indicator opens a file, a socket, or a database connection,
reads the clock, reads the environment, or draws a random number. Inputs
arrive as arrays the caller has already loaded, are copied on the way in,
and are marked read-only. `tests/quant/test_purity.py` enforces this
statically, by scanning the package for forbidden imports and attribute
names, and dynamically, by running every indicator with `open`, the socket
constructors, the process-spawning entry points, and `__import__` itself
replaced by functions that fail the test.

**Price basis.** FData OHLC is back-adjusted and expressed in thousands of
VND (Section 19.1), and every bar carries an `adjustment_status`
(Section 10.1). Nothing in this package re-adjusts, rescales, or converts a
price. Every indicator inherits whatever basis the caller supplied, which is
why each entry below restates the consequence rather than assuming it.

**Volume basis.** Volume is in shares and is NOT adjusted, while prices are.
Any statistic that multiplies a price by a volume therefore mixes an
adjusted series with an unadjusted one, and its level is comparable over
time only between corporate actions. Read the slope of the cumulative
money-flow series, not the level.

**Vietnamese price bands.** HOSE, HNX, and UPCoM all impose daily price
bands. A limit session can print `high == low == close`, which is a 0/0 form
for the classic money-flow multiplier. The convention adopted, and the
standard one, is a multiplier of zero, so the most one-sided sessions
contribute nothing to the accumulation/distribution line. The count of such
bars is reported as `zero_range_bars`, and on-balance volume, which signs a
limit-up day fully positive, is in the same block for exactly this reason.

**Missing values.** A missing bar is never imputed, interpolated, or
forward-filled. Three rules apply, and each indicator names which it
follows:

- *Windowed*: output is defined only when the whole window exists and holds
  no NaN, so one missing bar costs exactly one window of output and the
  series then recovers by itself.
- *Recursive with gap re-seed*: the input is split into maximal runs of
  consecutive defined bars and the recursion runs independently inside each
  run. A gap costs one further full warm-up period and never propagates
  beyond it.
- *Cumulative*: output is NaN at the undefined bar and the running total
  carries across unchanged, so the series resumes at its previous level.
  Used only for on-balance volume, the accumulation/distribution line, and
  volume-price trend, all three of which have an arbitrary origin.

**Warm-up.** Every indicator declares its warm-up as prose and as the
callable `IndicatorSpec.warm_up_bars`. `test_indicator_math.py` asserts that
the slowest output of each indicator first becomes defined at exactly the
declared bar, so the documented number is checked against behaviour on every
test run rather than trusted.

**Ratios.** Every division goes through `safe_divide`, which returns NaN
rather than an infinity when the denominator is zero. An undefined value
stays visibly undefined instead of becoming an infinity that survives into a
strategy comparison.

## Outstanding external verification

Section 14's acceptance criterion is that results "match an independent
reference or AmiBroker export within a documented tolerance". The
independent reference exists: `tests/quant/reference.py` reimplements every
indicator naively, in plain Python, sharing no code with the engine, and
each indicator is compared against it at its own documented tolerance,
alongside hand-computed cases whose expected values are written into the
tests as literals.

**No AmiBroker export has been supplied to this workstream, so the
AmiBroker half of that criterion is not met.** This matters beyond
belt-and-braces, because a reference implementation cannot detect a wrong
*convention*, only a wrong implementation of the chosen one. The
conventions most likely to differ from AmiBroker, and therefore most worth
checking against an export, are:

1. EMA seeding. This package seeds with an SMA of the first `period` values.
   A package seeding with the first observation produces different values
   for hundreds of bars.
2. The first bar's true range. This package leaves it undefined; some
   packages substitute `high - low`, which shifts every later ATR value.
3. The Bollinger standard deviation. This package uses the population form
   (`ddof = 0`). The sample form differs by a factor `sqrt(n / (n - 1))`,
   about 2.6 percent at `period = 20`.
4. The RSI value on a flat window. This package returns NaN where others
   conventionally return 50 or 100.

Each per-indicator tolerance below states the reference it applies to. Where
a looser tolerance is proposed for an eventual AmiBroker comparison, the
reason is FData's float32 storage (Section 19.1), not a weaker claim about
the mathematics.

Suggested next step for whoever holds the AmiBroker licence: export the
Section 14 indicators for a handful of tickers at the default parameters,
drop the CSV into `tests/quant/golden/amibroker/`, and add a comparison
test. Until that exists, treat the four conventions above as unverified
against the reference platform the user already trusts.

## Blocked and partially blocked indicators

**Relative strength versus VN-Index and versus sector.** The mathematics is
implemented and tested against a synthetic benchmark. Choosing the actual
benchmark is blocked: Section 10.2 requires an index code-to-name mapping
from an external source before these calculations are enabled, the 207 files
under `EOD/index` are named with numeric codes, and no security-master entry
with `security_type: "index"` and a populated `index_code` exists yet. The
resolver raises `BenchmarkMappingUnavailable` rather than guessing a code,
and the end-to-end tests skip themselves with that reason. This is a
dependency on the data stream (WP2), not on this workstream.

**Close versus VWAP.** Section 14 admits this to the money-flow block once
`Aux1` is confirmed as unadjusted VWAP, and `docs/data_dictionary.md` now
records that confirmation, dated 30 July 2026. Three things still stand
between the confirmation and the block, and none of them belong to this
workstream: the canonical `PriceBar` contract carries no VWAP or
unadjusted-close field, so the inputs cannot be delivered; the data
dictionary's own safeguard keeps `Aux1` out of every calculation pending an
explicit downstream design decision; and the verification covers five liquid
HOSE equities on one session, with corporate-action dates untested. There is
also a substantive trap: `Aux1` is unadjusted while OHLC is back-adjusted,
so dividing the stored close by the stored `Aux1` is correct only for bars
after the most recent corporate action and silently wrong before it. The
formula is implemented and tested as
`money_flow.close_versus_vwap(unadjusted_close, vwap)`, which takes the
unadjusted close explicitly so the mistake cannot be made by accident, and
`build_money_flow_block` accepts a finished value from a caller that can
legitimately produce one. It is never derived from the bars.

## Per-indicator record

## Block: levels
### `pivot_levels` — Classic floor-trader pivot levels

- **Block:** levels
- **Series outputs:** `pivot`, `r1`, `r2`, `r3`, `s1`, `s2`, `s3`
- **Scalar outputs:** none
- **Parameters (defaults):** none
- **Formula:** Using the previous bar's high H, low L, and close C: pivot = (H + L + C) / 3; r1 = 2 * pivot - L; s1 = 2 * pivot - H; r2 = pivot + (H - L); s2 = pivot - (H - L); r3 = H + 2 * (pivot - L); s3 = L - 2 * (H - pivot).
- **Input price:** The previous bar's high, low, and close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package. Pivot levels are price levels, so a back-adjusted series produces back-adjusted levels. Comparing a pivot level computed on adjusted data with a quote from an unadjusted screen is a category error; the caller must keep both on the same basis.
- **Warm-up:** 1 bar. The levels published for bar i are computed from bar i - 1, so they are known before bar i trades and contain no look-ahead.
- **Missing values:** All seven outputs are NaN when any of the previous bar's high, low, or close is missing. Nothing is carried forward from an older bar, because a stale pivot level presented as current would be misleading.
- **Comparison reference:** Closed-form arithmetic; hand-computed cases in the golden fixture. The period is whatever the caller supplies: pass daily bars for daily pivots, or a weekly or monthly resampling for weekly or monthly pivots. Resampling is deliberately outside this function so that the timeframe conversion has one owner rather than being reimplemented per indicator.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against hand-computed arithmetic. Note this is the classic pivot formula; Woodie, Camarilla, DeMark, and Fibonacci variants give different numbers and are not implemented.
## Block: momentum
### `rsi` — Relative strength index (Wilder)

- **Block:** momentum
- **Series outputs:** `value`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=14`
- **Formula:** change[i] = close[i] - close[i - 1]; gain = max(change, 0); loss = max(-change, 0); avg_gain and avg_loss are Wilder-smoothed over `period` (seed = simple mean of the first `period` values, then s[i] = s[i-1] + (x[i] - s[i-1]) / period); RSI = 100 * avg_gain / (avg_gain + avg_loss). That last expression is algebraically identical to the published 100 - 100 / (1 + avg_gain / avg_loss) whenever avg_loss > 0, and it avoids a division by zero: a window with no down days returns exactly 100, and a completely flat window (no up and no down movement) returns NaN because the index is genuinely undefined there rather than conventionally 50 or 100.
- **Input price:** Close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period bars. `period` price changes are needed, which requires period + 1 closes, so the first defined value sits at index `period`.
- **Missing values:** A missing close makes two changes undefined (the one into it and the one out of it). The Wilder recursion then applies the gap re-seed rule, so a gap costs a further full `period` of warm-up and never propagates past that.
- **Comparison reference:** Naive reference implementation of Wilder's recursion in tests/quant/reference.py, plus a hand-computed case with a known closed-form answer (a strictly rising series must give exactly 100, a strictly falling series exactly 0). AmiBroker RSI() cross-check pending an export.
- **Tolerance:** absolute 1e-08, relative 1e-08. Against the naive reference implementation. RSI is bounded on [0, 100], so the absolute arm dominates. A 1e-3 absolute allowance is proposed for the pending AmiBroker cross-check.
## Block: money_flow
### `accumulation_distribution` — Accumulation/distribution line

- **Block:** money_flow
- **Series outputs:** `value`, `money_flow_multiplier`, `money_flow_volume`
- **Scalar outputs:** `zero_range_bars`
- **Parameters (defaults):** none
- **Formula:** money_flow_multiplier[i] = ((close - low) - (high - close)) / (high - low), which simplifies to (2 * close - high - low) / (high - low) and lies in [-1, +1]; money_flow_volume[i] = multiplier * volume; value[i] = value[i-1] + money_flow_volume[i].
- **Input price:** High, low, and close of the same bar; volume in shares.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected.
- **Warm-up:** None. The multiplier uses only the current bar, so the first bar already has a value.
- **Missing values:** NaN wherever high, low, close, or volume is missing, with the running total unchanged across the gap (cumulative rule). ZERO-RANGE CONVENTION: when high == low the multiplier is 0/0 and is set to 0, the standard convention. In Vietnam this is not a rare degenerate case: a limit-up or limit-down session prints high == low, so the most one-sided sessions contribute nothing to this line. The count of affected bars is returned as the `zero_range_bars` scalar, and on-balance volume, which has no such blind spot, should be read alongside it.
- **Comparison reference:** Naive reference implementation plus a hand-computed three-bar case covering one ordinary bar, one close-at-high bar (multiplier exactly +1), and one zero-range bar (multiplier 0 by convention). The origin of the cumulative series is arbitrary and starts at the first defined bar's money flow volume, so any external comparison must be on differences, not levels.
- **Tolerance:** absolute 1e-06, relative 1e-09. Against the naive reference implementation, on differences of the series. The absolute arm is loose because the running total reaches 1e8 and above on liquid names.
### `on_balance_volume` — On-balance volume

- **Block:** money_flow
- **Series outputs:** `value`, `signed_volume`
- **Scalar outputs:** none
- **Parameters (defaults):** none
- **Formula:** signed_volume[i] = +volume[i] if close[i] > close[i-1], -volume[i] if close[i] < close[i-1], 0 if unchanged; value[i] = value[i-1] + signed_volume[i].
- **Input price:** Close, for direction only; volume in shares for magnitude.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected. Direction is taken from the adjusted close, so a price change that is purely a corporate-action artifact can sign a day's volume. Days on which the security master records a corporate action should be treated as unreliable for this indicator.
- **Warm-up:** 1 bar; the first bar has no previous close to compare against.
- **Missing values:** NaN wherever the close, the previous close, or the volume is missing, with the running total unchanged across the gap (cumulative rule). Unlike the accumulation/distribution line, on-balance volume has no zero-range blind spot: a limit-up session is signed fully positive.
- **Comparison reference:** Naive reference implementation plus a hand-computed four-bar case covering an up day, a down day, and an unchanged day. Origin is arbitrary; compare differences, not levels.
- **Tolerance:** absolute 1e-06, relative 1e-09. Against the naive reference implementation, on differences.
### `unusual_volume` — Unusual-volume flags

- **Block:** money_flow
- **Series outputs:** `flag`, `ratio`, `baseline`
- **Scalar outputs:** none
- **Parameters (defaults):** `window=20`, `multiple=2.0`
- **Formula:** baseline[i] = median(volume[i - window .. i - 1]), the trailing median excluding the current bar; ratio[i] = volume[i] / baseline[i]; flag[i] = 1.0 when ratio[i] >= multiple, else 0.0.
- **Input price:** Volume in shares; no price input.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected.
- **Warm-up:** window bars, because the baseline excludes the current bar and needs `window` prior bars.
- **Missing values:** All three outputs are NaN when the current volume is missing or the trailing window is incomplete or contains a missing volume. ratio and flag are NaN when the baseline median is zero, which happens for a security that has not traded for most of the window; Section 19.2 treats such runs as an inactivity signal, and flagging the first trade after a dormant month as an infinite volume spike would be noise.
- **Comparison reference:** Naive reference implementation plus hand-computed cases. The median baseline is chosen over a mean because a single prior spike would otherwise raise the bar enough to hide the next one; the current bar is excluded so that a large bar cannot inflate its own baseline. The default multiple of 2.0 is a convention with no external authority: Section 14 requires unusual-volume flags but sets no threshold, so the threshold is a parameter and the screener should tune it per liquidity band rather than treat 2.0 as meaningful.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation. `flag` is exact, being 0.0 or 1.0; note that a ratio exactly equal to `multiple` flags, the comparison being >=.
### `up_down_volume_ratio` — Up-day versus down-day volume ratio

- **Block:** money_flow
- **Series outputs:** `value`, `up_volume_share`, `up_volume`, `down_volume`
- **Scalar outputs:** none
- **Parameters (defaults):** `window=20`
- **Formula:** Over the trailing `window` bars: up_volume = sum of volume on bars where close > previous close; down_volume = sum of volume on bars where close < previous close; unchanged bars are counted in neither. value = up_volume / down_volume; up_volume_share = up_volume / (up_volume + down_volume).
- **Input price:** Close for direction, volume in shares for magnitude.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected.
- **Warm-up:** window bars. The direction of the first bar is undefined, so `window` signed bars require window + 1 closes and the first defined value sits at index `window`.
- **Missing values:** Windowed rule on the two sums: NaN if any bar in the window has a missing close or volume. `value` is additionally NaN when down_volume is zero, which is a real Vietnamese case during a limit-up streak rather than a defect; `up_volume_share` stays defined there and equals 1.0, which is why both are exposed. safe_divide returns NaN rather than an infinity so the undefined case cannot survive unnoticed into a strategy comparison.
- **Comparison reference:** Naive reference implementation plus a hand-computed case with a known answer (three up days of 100 shares against two down days of 50 gives exactly 3.0 and a share of 0.75). No standard external reference exists; this is a defined statistic rather than a published indicator, so its definition here is the reference.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation.
### `volume_at_price` — Volume-at-price concentration

- **Block:** money_flow
- **Series outputs:** `typical_price`
- **Scalar outputs:** `bin_edges`, `bin_volume`, `bin_volume_share`, `point_of_control_price`, `point_of_control_share`, `top_three_bin_share`, `herfindahl`, `normalized_herfindahl`, `value_area_low`, `value_area_high`, `included_bars`, `excluded_bars`
- **Parameters (defaults):** `lookback=120`, `bins=20`, `value_area_share=0.7`
- **Formula:** typical_price[i] = (high + low + close) / 3. Over the last `lookback` bars, the price span [min(low), max(high)] is divided into `bins` equal width bins and each bar's entire volume is assigned to the bin containing its typical price. From that histogram: point_of_control is the bin holding the most volume; herfindahl is the sum of squared bin shares (1 / bins under a perfectly flat distribution, 1.0 when all volume sits in one bin); normalized_herfindahl rescales that onto [0, 1]; the value area is the smallest set of bins, taken in descending volume order with ties broken by the lower bin, whose combined share reaches `value_area_share`.
- **Input price:** High, low, and close, combined into the typical price; volume in shares.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected. The histogram is built on back-adjusted prices, so its bin prices are adjusted prices and will not line up with an unadjusted chart if a corporate action falls inside the lookback window.
- **Warm-up:** The histogram needs at least one bar with a defined typical price and volume inside the lookback; the `typical_price` series itself has no warm-up.
- **Missing values:** Bars with a missing typical price or volume are excluded from the histogram, and the count of excluded bars is reported as `excluded_bars` so a thin histogram is visible rather than implied. If no bar survives, or if every surviving bar shares one price so the span is zero, the scalars are returned as None rather than as a degenerate single-bin histogram.
- **Comparison reference:** Naive reference implementation plus a hand-computed case with a constructed histogram. This is a defined statistic rather than a published indicator. Two modelling choices are conventions, not measurements, and a different tool will disagree without either being wrong: assigning a bar's whole volume to the typical-price bin, rather than spreading it across the high-low range, and choosing the value area greedily rather than by the classic market-profile expansion from the point of control. Spreading volume across the range is the more faithful model and is recorded as a follow-up.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation, for the histogram and every derived share. Bin assignment at an exact bin boundary is resolved to the lower bin, and the top edge to the last bin, so boundary cases are deterministic rather than tolerance-dependent.
## Block: relative_strength
### `relative_strength_sector` — Relative strength versus sector index

- **Block:** relative_strength
- **Series outputs:** `ratio`, `roc`, `excess_return_pct`, `mansfield`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=63`, `mansfield_period=200`, `benchmark=None`
- **Formula:** ratio[i] = 100 * close[i] / benchmark_close[i], where benchmark_close is the benchmark aligned onto the security's trading dates; roc[i] = 100 * (ratio[i] / ratio[i - period] - 1); excess_return_pct[i] = ROC(close, period) - ROC(benchmark_close, period); mansfield[i] = 100 * (ratio[i] / SMA(ratio, mansfield_period) - 1), the Mansfield relative-strength form used in Weinstein stage analysis.
- **Input price:** Close of the security and close of the benchmark index. The ratio's LEVEL is arbitrary, being a price in thousands of VND divided by an index level, so it must never be compared across securities. It is deliberately not re-based to 100 at the start of the loaded window, because that would make every value depend on how much history the caller happened to request. Compare securities using roc, excess_return_pct, or mansfield, all three of which are invariant to the ratio's scale.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package. The same basis requirement as relative strength versus VN-Index applies, and additionally the sector index must be the one the security master assigns to this security's sector, not a sector chosen by resemblance.
- **Warm-up:** ratio: none beyond the first date both series cover. roc and excess_return_pct: `period` bars. mansfield: mansfield_period - 1 bars.
- **Missing values:** NaN on any date the benchmark does not cover, on any date the security's close is missing, and wherever the benchmark close is zero. Alignment is by trading date and nothing is forward-filled, so a benchmark holiday shows as a gap rather than as a flat day. mansfield additionally follows the windowed rule over mansfield_period. A sector index typically has a shorter history than a long-listed security, so the overlap window, not the security's own history, sets the first usable date.
- **Comparison reference:** Naive reference implementation on a synthetic benchmark. BLOCKED for any real comparison on the same Section 10.2 mapping dependency, and additionally on the sector taxonomy: the security master's `sector` field must use the same vocabulary as whatever the sector indices are built from, which is not yet established.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation, on a synthetic benchmark. No external cross-check is possible until the index mapping and real index bars exist; the AmiBroker comparison for this family is blocked on the same dependency, not merely on an export.
### `relative_strength_vnindex` — Relative strength versus VN-Index

- **Block:** relative_strength
- **Series outputs:** `ratio`, `roc`, `excess_return_pct`, `mansfield`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=63`, `mansfield_period=200`, `benchmark=None`
- **Formula:** ratio[i] = 100 * close[i] / benchmark_close[i], where benchmark_close is the benchmark aligned onto the security's trading dates; roc[i] = 100 * (ratio[i] / ratio[i - period] - 1); excess_return_pct[i] = ROC(close, period) - ROC(benchmark_close, period); mansfield[i] = 100 * (ratio[i] / SMA(ratio, mansfield_period) - 1), the Mansfield relative-strength form used in Weinstein stage analysis.
- **Input price:** Close of the security and close of the benchmark index. The ratio's LEVEL is arbitrary, being a price in thousands of VND divided by an index level, so it must never be compared across securities. It is deliberately not re-based to 100 at the start of the loaded window, because that would make every value depend on how much history the caller happened to request. Compare securities using roc, excess_return_pct, or mansfield, all three of which are invariant to the ratio's scale.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package. Both legs must be on the same adjustment basis. A back-adjusted security close divided by a price index that is not back-adjusted produces a ratio that drifts at every corporate action; confirming that the index series in EOD/index is on a comparable basis is part of the outstanding data-stream dependency.
- **Warm-up:** ratio: none beyond the first date both series cover. roc and excess_return_pct: `period` bars. mansfield: mansfield_period - 1 bars, so the default of 200 needs roughly ten months of overlapping history.
- **Missing values:** NaN on any date the benchmark does not cover, on any date the security's close is missing, and wherever the benchmark close is zero. Alignment is by trading date and nothing is forward-filled, so a benchmark holiday shows as a gap rather than as a flat day. mansfield additionally follows the windowed rule over mansfield_period.
- **Comparison reference:** Naive reference implementation on a synthetic benchmark. BLOCKED for any real comparison: the benchmark cannot be identified until the data stream supplies the Section 10.2 index code-to-name mapping. The default period of 63 bars is a quarter of trading sessions and the Mansfield period of 200 follows Weinstein's published convention; neither is prescribed by Section 14.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation, on a synthetic benchmark. No external cross-check is possible until the index mapping and real index bars exist; the AmiBroker comparison for this family is blocked on the same dependency, not merely on an export.
## Block: trend
### `ema` — Exponential moving average

- **Block:** trend
- **Series outputs:** `value`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=20`
- **Formula:** alpha = 2 / (period + 1); seed = mean(close[first .. first + period - 1]) placed at index first + period - 1; thereafter EMA[i] = alpha * close[i] + (1 - alpha) * EMA[i - 1].
- **Input price:** Close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period - 1 bars, because the recursion is seeded with a simple mean of the first `period` closes rather than with close[0].
- **Missing values:** Gap re-seed rule: the close series is split into maximal runs of consecutive non-NaN bars and the recursion runs independently inside each run, so one missing bar costs one further warm-up period and never contaminates the rest of the series. Runs shorter than `period` produce no output at all.
- **Comparison reference:** Naive reference implementation applying the same seeding rule, plus a hand-computed three-step recursion. AmiBroker EMA() cross-check pending an export; note AmiBroker's seeding convention must be confirmed before that comparison is meaningful.
- **Tolerance:** absolute 1e-08, relative 1e-08. Against the independent naive reference implementation in tests/quant/reference.py. Looser than the windowed indicators because the recursion accumulates rounding over the full series. A 1e-4 relative allowance is proposed for the pending AmiBroker cross-check, which also depends on AmiBroker using the same SMA seeding convention.
### `macd` — Moving average convergence divergence

- **Block:** trend
- **Series outputs:** `macd`, `signal`, `histogram`
- **Scalar outputs:** none
- **Parameters (defaults):** `fast_period=12`, `slow_period=26`, `signal_period=9`
- **Formula:** MACD = EMA(close, fast_period) - EMA(close, slow_period); signal = EMA(MACD, signal_period); histogram = MACD - signal. Every EMA uses the SMA-seeded convention documented for the `ema` indicator, and the signal line is seeded from the first `signal_period` defined MACD values.
- **Input price:** Close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** MACD line: slow_period - 1 bars. Signal and histogram: slow_period + signal_period - 2 bars, since the signal EMA is seeded from the first signal_period defined MACD values.
- **Missing values:** Inherits the EMA gap re-seed rule on both legs. A NaN close makes both EMAs undefined at that bar, so MACD, signal, and histogram are all NaN there; the signal line then re-seeds from the resumed MACD run.
- **Comparison reference:** Naive reference implementation composed from the reference EMA. AmiBroker MACD()/Signal() cross-check pending an export.
- **Tolerance:** absolute 1e-08, relative 1e-08. Against the independent naive reference implementation in tests/quant/reference.py. Looser than the windowed indicators because the recursion accumulates rounding over the full series. A 1e-4 relative allowance is proposed for the pending AmiBroker cross-check, which also depends on AmiBroker using the same SMA seeding convention.
### `rate_of_change` — Rate of change

- **Block:** trend
- **Series outputs:** `value`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=12`
- **Formula:** ROC[i] = 100 * (close[i] / close[i - period] - 1), in percent.
- **Input price:** Close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period bars; the first defined value sits at index `period`.
- **Missing values:** NaN when either endpoint is missing. A zero or negative close at the lagged endpoint yields NaN rather than an infinity, via safe_divide.
- **Comparison reference:** Closed-form arithmetic; hand-computed cases in the golden fixture. AmiBroker ROC() cross-check pending an export.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the independent naive reference implementation in tests/quant/reference.py and the hand-computed cases in the golden fixture. Float64 arithmetic only, so agreement is near machine precision. A looser 1e-4 relative allowance is proposed for the pending AmiBroker cross-check because FData stores prices as float32 (Section 19.1).
### `rolling_high` — Rolling high

- **Block:** trend
- **Series outputs:** `value`, `distance_pct`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=52`
- **Formula:** value[i] = max(high[i - period + 1 .. i]); distance_pct[i] = 100 * (close[i] / value[i] - 1), negative when the close sits below the rolling high.
- **Input price:** High for the extreme itself, close for the distance measure. Using the high rather than the close means the level matches what a chart shows.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period - 1 bars.
- **Missing values:** Windowed rule: NaN whenever the window is incomplete or contains a NaN high. distance_pct is additionally NaN when the close is missing.
- **Comparison reference:** Naive reference implementation plus hand-computed cases. AmiBroker HHV() cross-check pending an export.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the independent naive reference implementation in tests/quant/reference.py and the hand-computed cases in the golden fixture. Float64 arithmetic only, so agreement is near machine precision. A looser 1e-4 relative allowance is proposed for the pending AmiBroker cross-check because FData stores prices as float32 (Section 19.1).
### `rolling_low` — Rolling low

- **Block:** trend
- **Series outputs:** `value`, `distance_pct`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=52`
- **Formula:** value[i] = min(low[i - period + 1 .. i]); distance_pct[i] = 100 * (close[i] / value[i] - 1), positive when the close sits above the rolling low.
- **Input price:** Low for the extreme itself, close for the distance measure.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period - 1 bars.
- **Missing values:** Windowed rule: NaN whenever the window is incomplete or contains a NaN low. distance_pct is additionally NaN when the close is missing, and when the rolling low is zero.
- **Comparison reference:** Naive reference implementation plus hand-computed cases. AmiBroker LLV() cross-check pending an export.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the independent naive reference implementation in tests/quant/reference.py and the hand-computed cases in the golden fixture. Float64 arithmetic only, so agreement is near machine precision. A looser 1e-4 relative allowance is proposed for the pending AmiBroker cross-check because FData stores prices as float32 (Section 19.1).
### `sma` — Simple moving average

- **Block:** trend
- **Series outputs:** `value`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=20`
- **Formula:** SMA[i] = mean(close[i - period + 1 .. i])
- **Input price:** Close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period - 1 bars. The first defined value sits at index period - 1, the first bar with a complete window.
- **Missing values:** Windowed rule: NaN whenever the window is incomplete or contains a NaN close. A single missing bar costs exactly `period` outputs and the series then recovers on its own. No imputation or forward fill.
- **Comparison reference:** Naive O(n*period) reference implementation plus hand-computed values on a five-bar series. AmiBroker MA() cross-check pending an export.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the independent naive reference implementation in tests/quant/reference.py and the hand-computed cases in the golden fixture. Float64 arithmetic only, so agreement is near machine precision. A looser 1e-4 relative allowance is proposed for the pending AmiBroker cross-check because FData stores prices as float32 (Section 19.1).
## Block: volatility
### `atr` — Average true range (Wilder)

- **Block:** volatility
- **Series outputs:** `value`, `percent_of_close`, `true_range`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=14`
- **Formula:** TR[i] = max(high[i] - low[i], |high[i] - close[i-1]|, |low[i] - close[i-1]|); ATR = Wilder smoothing of TR over `period`; percent_of_close = 100 * ATR / close.
- **Input price:** High, low, and the previous close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period bars. TR is undefined on the first bar, and the Wilder seed consumes the next `period` TR values, so the first ATR sits at index `period`.
- **Missing values:** TR is NaN wherever the bar or the previous close is missing. ATR then applies the gap re-seed rule, costing a further full `period`. percent_of_close is additionally NaN when the close is zero or missing.
- **Comparison reference:** Naive reference implementation of TR and of Wilder's recursion, plus a hand-computed three-bar case. AmiBroker ATR() cross-check pending an export.
- **Tolerance:** absolute 1e-08, relative 1e-08. Against the naive reference implementation. A 1e-4 relative allowance is proposed for the pending AmiBroker cross-check, which also requires confirming AmiBroker's first-bar TR convention.
### `bollinger_bands` — Bollinger Bands

- **Block:** volatility
- **Series outputs:** `middle`, `upper`, `lower`, `bandwidth`, `percent_b`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=20`, `num_std=2.0`
- **Formula:** middle = SMA(close, period); sigma = population standard deviation of close over the same window (ddof = 0); upper = middle + num_std * sigma; lower = middle - num_std * sigma; bandwidth = 100 * (upper - lower) / middle; percent_b = (close - lower) / (upper - lower).
- **Input price:** Close.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package.
- **Warm-up:** period - 1 bars, the same as the underlying SMA.
- **Missing values:** Windowed rule on both the mean and the standard deviation: NaN whenever the window is incomplete or contains a NaN close. bandwidth is NaN when the middle band is zero, and percent_b is NaN on a zero-width band (a window of identical closes), both via safe_divide rather than returning an infinity.
- **Comparison reference:** Naive reference implementation using the population standard deviation, plus a hand-computed case. The ddof = 0 choice matches the original publication and AmiBroker's StDev; a package using the sample standard deviation will differ by a factor sqrt(period / (period - 1)), which is about 2.6 percent at period = 20. AmiBroker BBandTop()/BBandBot() cross-check pending an export.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation. Does not cover the ddof convention difference described above, which is a definitional difference rather than a numerical one.
### `drawdown` — Drawdown from running peak

- **Block:** volatility
- **Series outputs:** `value`, `peak`
- **Scalar outputs:** `max_drawdown_pct`, `max_drawdown_index`
- **Parameters (defaults):** none
- **Formula:** peak[i] = max(close[0 .. i]) over defined closes; value[i] = 100 * (close[i] / peak[i] - 1), which is zero at a new high and negative below it.
- **Input price:** Close. Computed on the closing price, not on intraday lows, so it measures close-to-close drawdown rather than peak-to-trough.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package. Drawdown is scale-invariant, so it is unaffected by the price unit, but it is sensitive to the adjustment method: an unadjusted series shows an artificial drawdown on every ex-dividend and split date.
- **Warm-up:** None. The first defined close is its own peak, so value[first] = 0.
- **Missing values:** NaN at a missing close. The running peak carries across the gap unchanged (it is a maximum over defined closes only), so the series resumes correctly rather than restarting.
- **Comparison reference:** Naive reference implementation plus hand-computed cases; the definition is closed-form.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation.
### `rolling_volatility` — Rolling realized volatility

- **Block:** volatility
- **Series outputs:** `value`, `daily_std`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=20`, `trading_days_per_year=252`
- **Formula:** r[i] = ln(close[i] / close[i - 1]); daily_std = sample standard deviation of r over `period` (ddof = 1); value = 100 * daily_std * sqrt(trading_days_per_year), in annualized percent.
- **Input price:** Close, as log returns.
- **Adjustment convention:** Inherits the caller's price adjustment verbatim. FData bars are back-adjusted and expressed in thousands of VND (Section 19.1) with adjustment_status carried on every bar (Section 10.1). No re-adjustment, rescaling, or currency conversion happens inside this package. Log returns require a positive close; a zero or negative adjusted close yields NaN rather than a complex or infinite return.
- **Warm-up:** period bars. `period` returns are needed, which requires period + 1 closes, so the first defined value sits at index `period`.
- **Missing values:** A missing close makes two returns undefined, and the windowed rule then makes `period` volatility values undefined. ddof = 1 means a window must hold at least two returns, which `period >= 2` guarantees.
- **Comparison reference:** Naive reference implementation. The annualization factor is a convention, not a measurement: 252 is the common international default and is used here, but Ho Chi Minh City and Hanoi trade roughly 247 to 250 sessions a year, so a VN-specific caller should pass the realized session count. Changing it rescales `value` by a known constant and leaves `daily_std` untouched.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation, at a fixed trading_days_per_year. Comparisons across packages must first reconcile the annualization factor and the ddof choice.
## Block: volume
### `volume_price_trend` — Volume-price trend

- **Block:** volume
- **Series outputs:** `value`, `contribution`
- **Scalar outputs:** none
- **Parameters (defaults):** none
- **Formula:** contribution[i] = volume[i] * (close[i] - close[i-1]) / close[i-1]; value[i] = value[i-1] + contribution[i], a running total starting from zero at the first defined contribution.
- **Input price:** Close for the return, volume in shares for the weight.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected.
- **Warm-up:** 1 bar; the first bar has no previous close.
- **Missing values:** Cumulative rule: NaN at a bar whose contribution is undefined, with the running total unchanged across the gap. The level of a cumulative volume series has no absolute meaning, so resuming at the same level is safe; the direction and slope, which are what the indicator is read for, stay intact.
- **Comparison reference:** Naive reference implementation plus a hand-computed three-bar case. No AmiBroker built-in is assumed; if a comparison is wanted the AFL must state its own starting value, since the origin is arbitrary. Compare differences of the series, not levels.
- **Tolerance:** absolute 1e-06, relative 1e-09. Against the naive reference implementation. The absolute arm is loose because the running total reaches 1e8 and above on liquid names, where one unit in the last place is already about 1e-8 relative.
### `volume_sma` — Volume simple moving average

- **Block:** volume
- **Series outputs:** `value`, `relative_volume`
- **Scalar outputs:** none
- **Parameters (defaults):** `period=20`
- **Formula:** value[i] = mean(volume[i - period + 1 .. i]); relative_volume[i] = volume[i] / value[i], so 1.0 is an average day and 3.0 is three times the recent average.
- **Input price:** Volume in shares; no price input.
- **Adjustment convention:** Volume is in shares (Section 19.1) and is NOT back-adjusted, while prices are. Any indicator that multiplies a price by a volume therefore mixes an adjusted series with an unadjusted one, and its level is comparable over time only up to the next corporate action. Ratios of volume to its own moving average, which is how the screener should use these, are unaffected.
- **Warm-up:** period - 1 bars.
- **Missing values:** Windowed rule: NaN whenever the window is incomplete or contains a NaN volume. A genuine zero-volume session is a valid observation, not a missing one, and is averaged in as zero; relative_volume is then NaN only if the average itself is zero (an entire window of no trading), which Section 19.2 treats as an inactivity signal rather than an error.
- **Comparison reference:** Naive reference implementation plus hand-computed cases. AmiBroker MA(Volume, n) cross-check pending an export.
- **Tolerance:** absolute 1e-09, relative 1e-09. Against the naive reference implementation. Volumes reach 1e7 and above, so the relative arm dominates.
