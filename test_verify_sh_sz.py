import urllib.request
import ssl
import json

def test_fetch(symbol, market):
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&ut=7eea3edcaed734bea9cbfc24409ed989&klt=30&fqt=1&secid={market}.{symbol}&beg=0&end=20500000"
    print(f"URL: {url}")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        })
        r = urllib.request.urlopen(req, context=ctx, timeout=10).read()
        klines = json.loads(r).get("data", {}).get("klines", [])
        print('SUCCESS! KLines length:', len(klines))
    except Exception as e:
        print('FAILED:', str(e))

print("--- Testing sh603629 ---")
test_fetch("603629", "1")

print("--- Testing sz000833 ---")
test_fetch("000833", "0")
