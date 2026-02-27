import os
import sys
import pandas as pd
import sqlite3
import datetime
# Optional: test using local config thresholds

def test_etl(csv_file):
    print(f"Loading {csv_file}...")
    df = pd.read_csv(csv_file, engine='python') # Or simple C engine
    
    super_threshold = 1000000
    large_threshold = 500000
    
    # 1. 计算单笔成交真实金额
    df['amount'] = df['Price'] * df['Volume']
    
    # 2. 判断这笔成交背后的 原始委托单 是否构成主力级别
    df['buy_order_total_val'] = df['BuyOrderVolume'] * df['Price']
    df['sell_order_total_val'] = df['SaleOrderVolume'] * df['Price']
    
    super_buy = 0.0
    super_sell = 0.0
    main_buy = 0.0
    main_sell = 0.0
    
    for idx, row in df.iterrows():
        amt = row['amount']
        otype = row['Type'] # 'B' or 'S'
        
        # 资金流向我们算“主动买入”和“主动卖出”
        if otype == 'B':
            # 谁在买？看原委托单有多大
            if row['buy_order_total_val'] >= super_threshold:
                super_buy += amt
            elif row['buy_order_total_val'] >= large_threshold:
                main_buy += amt
                
        elif otype == 'S':
            if row['sell_order_total_val'] >= super_threshold:
                super_sell += amt
            elif row['sell_order_total_val'] >= large_threshold:
                main_sell += amt

    print(f"Total Super Buy: {super_buy:,.2f}")
    print(f"Total Super Sell: {super_sell:,.2f}")
    print(f"Super Net Inflow: {super_buy - super_sell:,.2f}")
    print(f"Main Net Inflow: {(super_buy + main_buy) - (super_sell + main_sell):,.2f}")

    # Generate 30-min Kline
    # Parse Time, add a fake date to use Pandas resample
    fake_date = "2023-10-10 "
    df['datetime'] = pd.to_datetime(fake_date + df['Time'])
    df.set_index('datetime', inplace=True)
    
    # Resample
    ohlc = df['Price'].resample('30min', label='right', closed='right').ohlc()
    vol = df['Volume'].resample('30min', label='right', closed='right').sum()
    ohlc['volume'] = vol
    ohlc.dropna(inplace=True)
    
    print("\n30-Minute K-Lines:")
    print(ohlc)


if __name__ == "__main__":
    test_etl('603639.csv')
