"""Every tunable number in Coin Arena. The future fitted model replaces
scoring.py's use of these; nothing else changes."""

TOP10_SHARE_WARNING = 0.35
TOP10_SHARE_DISQUALIFIER = 0.55
SINGLE_HOLDER_WARNING = 0.15

BUNDLE_BUYERS_WARNING = 4
BUNDLE_BUYERS_DISQUALIFIER = 8
LAUNCH_WINDOW_S = 60

DEV_LAUNCHES_WARNING = 3
DEV_LAUNCHES_DISQUALIFIER = 8
DEV_HISTORY_SAMPLE = 100

CHECK_TIMEOUT_S = 8.0

VERIFY_MIN_AGE_S = 24 * 3600
DEAD_LIQUIDITY_USD = 1000.0
RUG_PRICE_RATIO = 0.10

FUNDING_MAX_SIGS = 1000  # creator wallets busier than this: funding check bails

# --- Quant Microstructure Engine ---
QME_BASE_HAZARD_PCT_PER_HOUR = 20.0   # assumed, user-adjustable — NOT estimated
QME_HAZARD_MULT_MINT_LIVE = 2.5       # mint authority still held by the dev
QME_HAZARD_MULT_CONCENTRATED = 1.8    # top-10 concentration above the warning cut
QME_HAZARD_MULT_CREATOR_SELLING = 4.0 # creator wallet observed selling
QME_FIT_WINDOW_EVENTS = 300
QME_FIT_WINDOW_SECONDS = 120.0
QME_REFIT_INTERVAL_S = 1.0
QME_TAPE_MAXLEN = 2000
