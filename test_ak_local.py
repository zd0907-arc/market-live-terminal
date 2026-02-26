import akshare as ak
try:
    df = ak.stock_zh_a_hist_min_em(symbol="000833", period='30', adjust='qfq')
    print("000833 qfq length:", len(df) if df is not None else 0)
except Exception as e:
    print("000833 qfq Error:", e)

try:
    df = ak.stock_zh_a_hist_min_em(symbol="000833", period='30', adjust='')
    print("000833 no-adjust length:", len(df) if df is not None else 0)
except Exception as e:
    print("000833 no-adjust Error:", e)
