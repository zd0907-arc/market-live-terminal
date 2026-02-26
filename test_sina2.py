import akshare as ak

try:
    df = ak.stock_zh_a_minute(symbol='sz000833', period='30', adjust='qfq')
    if df is not None:
        df = df.dropna()
        print(df.tail(3))
except Exception as e:
    print("Sina Failed:", e)

