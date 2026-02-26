import asyncio
import akshare as ak
import sqlite3
import pandas as pd
import sys
import os

# Ensure we can import from backend
sys.path.append(os.getcwd())

# Force ignore system proxies that might interrupt EastMoney API
for k in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
    if k in os.environ:
        del os.environ[k]

DB_PATH = 'data/market_data.db'

async def diagnose_and_fix(symbol):
    print(f"\n{'='*20} 诊断与修复: {symbol} {'='*20}")
    pure_code = symbol
    if symbol.startswith('sz') or symbol.startswith('sh'):
        pure_code = symbol[2:]

    # 1. 检查数据库现有数据
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*), MIN(start_time), MAX(start_time) FROM history_30m WHERE symbol=?", (symbol,))
        count, start, end = c.fetchone()
        print(f"[*] 数据库现状: 总计 {count} 条记录, 时间范围: [{start}] 至 [{end}]")
        conn.close()
    except Exception as e:
        print(f"[!] 数据库查询失败: {e}")

    # 2. 尝试从 AkShare 获取 30 分钟 K 线
    print(f"[*] 正在尝试从 AkShare (东财接口) 获取 {pure_code} 的 30 分钟数据...")
    df = None
    try:
        # 尝试不带复权和带复权两种方式
        df = await asyncio.to_thread(ak.stock_zh_a_hist_min_em, symbol=pure_code, period='30', adjust='qfq')
        if df is None or df.empty:
            print("[!] AkShare 返回空数据 (qfq 模式)。尝试不复权模式...")
            df = await asyncio.to_thread(ak.stock_zh_a_hist_min_em, symbol=pure_code, period='30', adjust='')
    except Exception as e:
        print(f"[!] 东财接口调用崩溃: {e}")

    # ===== 回退机制：新浪财经接口 =====
    if df is None or df.empty:
        print(f"[*] 东财接口失效/被Ban，触发回退机制: 尝试从 [新浪财经] 获取 {symbol} 的 30 分钟数据...")
        try:
            sina_df = await asyncio.to_thread(ak.stock_zh_a_minute, symbol=symbol, period='30', adjust='qfq')
            if sina_df is not None and not sina_df.empty:
                # 新浪接口去除空行
                sina_df = sina_df.dropna(subset=['close'])
                print(f"[+] 新浪接口抓取成功! 共获取 {len(sina_df)} 条历史 K 线。")
                
                # 统一映射到目标 df 供后续写入
                df = pd.DataFrame({
                    '时间': sina_df['day'],
                    '收盘': sina_df['close'],
                    '开盘': sina_df['open'],
                    '最高': sina_df['high'],
                    '最低': sina_df['low']
                })
            else:
                print(f"[!] 新浪接口也返回了空数据。")
        except Exception as e:
            print(f"[!] 新浪接口调用崩溃: {e}")

    if df is not None and not df.empty:
        print(f"[+] 准备向数据库写入 {len(df)} 条记录...")
        
        # 3. 强制写入数据库
        data_list = []
        for _, row in df.iterrows():
            # 统一字段 (symbol, start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low)
            data_list.append((
                symbol,
                row['时间'],
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, # 流量置 0
                float(row['收盘']), float(row['开盘']), float(row['最高']), float(row['最低'])
            ))
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.executemany('''
            INSERT OR REPLACE INTO history_30m 
            (symbol, start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', data_list)
        conn.commit()
        print(f"[+] 修复成功! 已向数据库写入/更新 {len(data_list)} 条记录。")
        conn.close()
    else:
        print(f"[!] 所有数据源均无法为 {symbol} 提供数据，请检查该股票是否停牌、退市或遭遇史诗级封锁。")

async def main():
    if len(sys.argv) < 2:
        print("用法: python backend/scripts/force_fix_stock.py <symbol1> <symbol2> ...")
        return

    for sym in sys.argv[1:]:
        await diagnose_and_fix(sym)

if __name__ == "__main__":
    asyncio.run(main())
