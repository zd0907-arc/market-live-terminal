import os
import sys
import asyncio
import akshare as ak

async def fetch_and_generate_sql(symbols, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("BEGIN TRANSACTION;\n")
        
        for symbol in symbols:
            pure_code = symbol
            if symbol.startswith('sz') or symbol.startswith('sh'):
                pure_code = symbol[2:]
                
            print(f"[*] 正在从本地宽带抓取 AkShare (东财) 30 分钟 K 线 -> {symbol} ...")
            try:
                # 强制删除可能残留的代理环境变量
                for k in ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']:
                    if k in os.environ:
                        del os.environ[k]

                df = await asyncio.to_thread(ak.stock_zh_a_hist_min_em, symbol=pure_code, period='30', adjust='qfq')
                if df is not None and not df.empty:
                    print(f"    -> 成功！获取到 {len(df)} 条记录。正在生成 SQL 语句包...")
                    for _, row in df.iterrows():
                        time_str = row['时间']
                        close = float(row['收盘'])
                        open_p = float(row['开盘'])
                        high = float(row['最高'])
                        low = float(row['最低'])
                        
                        f.write(f"INSERT OR REPLACE INTO history_30m (symbol, start_time, net_inflow, main_buy, main_sell, super_net, super_buy, super_sell, close, open, high, low) VALUES ('{symbol}', '{time_str}', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {close}, {open_p}, {high}, {low});\n")
                else:
                    print(f"    -> 警告：{symbol} 无有效数据返回。")
            except Exception as e:
                print(f"    -> 错误：抓取 {symbol} 时发生异常：{e}")
        
        f.write("COMMIT;\n")
    print(f"\n[+] 离线 SQL 数据融合包已生成: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 fetch_local_data.py <output.sql> <sym1> [sym2...]")
        sys.exit(1)
    
    out_file = sys.argv[1]
    targets = sys.argv[2:]
    asyncio.run(fetch_and_generate_sql(targets, out_file))
