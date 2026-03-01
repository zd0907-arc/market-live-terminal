#!/usr/bin/expect -f
# ETL 进度查询 - 通过局域网快速查看 Windows ETL 进度
# 用法: ./check_etl.sh

set timeout 15

spawn ssh laqiyuan@192.168.3.108 {python -c "import sqlite3,os;db='D:/market-live-terminal/market_data_history.db';c=sqlite3.connect(db);done=c.execute('SELECT count(*) FROM etl_manifest WHERE status=\"DONE\"').fetchone()[0];fail=c.execute('SELECT count(*) FROM etl_manifest WHERE status=\"FAILED\"').fetchone()[0];total=278;pct=done*100//total;print(f'========== ETL Progress ==========');print(f'Done:   {done}/{total} ({pct}%)');fail and print(f'Failed: {fail}');print(f'DB Size: {os.path.getsize(db)//1024//1024}MB');rows=c.execute('SELECT trade_date,rows_local_history,rows_h30m,duration_ms FROM etl_manifest WHERE status=\"DONE\" ORDER BY last_updated DESC LIMIT 5').fetchall();print();print('Recent completions:');[print(f'  {d} | daily:{rl} | 30m:{r3} | {t//1000}s') for d,rl,r3,t in rows];print('==================================')"}
expect {
    "password:" {
        send "zhangdong\r"
        exp_continue
    }
    eof
}
