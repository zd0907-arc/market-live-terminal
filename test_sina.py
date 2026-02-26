import akshare as ak

try:
    print("Testing Sina 30m K-lines for sz000833...")
    df = ak.stock_zh_a_minute(symbol='sz000833', period='30', adjust='qfq')
    print("Sina Success! Length:", len(df) if df is not None else 0)
    if df is not None and not df.empty:
        print(df.tail(2))
except Exception as e:
    print("Sina Failed:", e)

