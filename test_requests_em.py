import requests
import os

url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?fields1=f1%2Cf2%2Cf3%2Cf4%2Cf5%2Cf6&fields2=f51%2Cf52%2Cf53%2Cf54%2Cf55%2Cf56%2Cf57%2Cf58%2Cf59%2Cf60%2Cf61&ut=7eea3edcaed734bea9cbfc24409ed989&klt=30&fqt=1&secid=0.000833&beg=0&end=20500000"

print("3. Testing by explicitly disabling requests proxy...")
try:
    # Disable requests from reading OS proxies by passing empty dicts
    session = requests.Session()
    session.trust_env = False
    r3 = session.get(url, timeout=5, proxies={"http": None, "https": None})
    print(f"Status 3: {r3.status_code}")
    print(f"Response length: {len(r3.text)}")
except Exception as e:
    print(f"Error 3: {e}")
