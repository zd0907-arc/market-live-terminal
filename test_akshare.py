import akshare as ak
import sys

if __name__ == "__main__":
    symbol = "sz000833"
    print(f"Testing AkShare for {symbol}...")
    try:
        df = ak.stock_zh_a_tick_tx_js(symbol)
        if df is not None and not df.empty:
            print(f"Success! Rows: {len(df)}")
            print("Columns:", df.columns.tolist())
            print("First row:", df.iloc[0].to_dict())
        else:
            print("Failed: Empty DataFrame")
    except Exception as e:
        print(f"Error: {e}")