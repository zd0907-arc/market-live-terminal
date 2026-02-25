import akshare as ak
try:
    df = ak.stock_zh_a_hist_min_em(symbol="603629", period='30', adjust='qfq')
    print("Code length:", len(df) if df is not None else 0)
    if df is not None and not df.empty:
        print(df.tail(2))
except Exception as e:
    print(f"Error fetching 603629: {e}")

try:
    df2 = ak.stock_zh_a_tick_tx_js("sh603629")
    print("Ticks length:", len(df2) if df2 is not None else 0)
except Exception as e:
    print(f"Error fetching ticks 603629: {e}")
