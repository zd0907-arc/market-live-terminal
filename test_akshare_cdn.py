import urllib.request
import json
import ssl

def fetch_kline(domain, symbol):
    prefix = "0." if symbol.startswith("sz") else "1."
    code = symbol[2:]
    url = f"https://{domain}/api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&ut=7eea3edcaed734bea9cbfc24409ed989&klt=30&fqt=1&secid={prefix}{code}&beg=0&end=20500000"
    
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "http://quote.eastmoney.com/"
        })
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            html = response.read()
            data = json.loads(html)
            klines = data.get("data", {}).get("klines", [])
            print(f"✅ [{domain}] Success! KLines Count: {len(klines)}")
    except Exception as e:
        print(f"❌ [{domain}] Error: {e}")

domains = [
    "push2his.eastmoney.com",
    "6.push2his.eastmoney.com",
    "20.push2his.eastmoney.com",
    "85.push2his.eastmoney.com",
    "99.push2his.eastmoney.com",
    "1.push2his.eastmoney.com"
]

for d in domains:
    fetch_kline(d, "sz000833")
