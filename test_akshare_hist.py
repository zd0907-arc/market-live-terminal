import akshare as ak
import pandas as pd
from datetime import datetime

def test_symbol(symbol):
    print(f"\n--- Testing {symbol} ---")
    pure_code = symbol
    if symbol.startswith('sz') or symbol.startswith('sh'):
        pure_code = symbol[2:]
    
    try:
        print(f"Calling ak.stock_zh_a_hist_min_em for {pure_code}...")
        df = ak.stock_zh_a_hist_min_em(symbol=pure_code, period='30', adjust='qfq')
        if df is not None and not df.empty:
            print(f"Success! Found {len(df)} rows.")
            print(df.tail(3))
        else:
            print("Failed: Empty dataframe returned.")
    except Exception as e:
        print(f"Error: {e}")

test_symbol("sz000833") # 粤桂股份
test_symbol("sz000759") # 中百集团
