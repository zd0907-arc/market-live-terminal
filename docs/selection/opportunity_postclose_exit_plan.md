# Opportunity Discovery Post-Close Exit Plan

## Objective

Build a post-close exit model for the existing opportunity discovery selector.

The selector still produces the candidate stock after market close. For any open position, the exit model only uses information available after that day's close and can only issue an action for the next trading day's open:

- hold
- sell next open

No intraday L2 or manual watchlist execution is assumed.

## Experiment Set

1. Fixed post-close baselines
   - hold to day 22
   - fixed take-profit as a reference only
   - close-based stop loss

2. Post-close hold-value model
   - target: whether holding from today's close is still worth more than selling next open
   - features: current profit, max runup so far, drawdown from peak, recent return, daily L2 flow, market breadth, theme heat, limit-up state
   - execution: if predicted hold value is below threshold, sell next open

3. Strong-run continuation model
   - target: after a position has already reached profit, estimate whether it still has meaningful future upside
   - purpose: avoid the 15% fixed take-profit selling strong trend names too early

4. Post-close trailing policies
   - activate after profit threshold
   - use close-to-peak drawdown, not intraday low
   - sell next open after the close confirms deterioration

## Backtest Views

1. Monthly reset
   - 2026-01
   - 2026-02
   - 2026-03
   - 2026-04 partial

2. Continuous account
   - one account from 2026-01 to the latest labeled validation date
   - no monthly capital reset
   - overlapping positions and cash constraints are preserved

## Success Metrics

- total return
- max drawdown
- win rate
- average holding days
- sell-fly rate after exit
- average missed upside after exit
- number of trades and skipped signals

This model is a trading-management layer, not a replacement for the 22-day opportunity selector.
