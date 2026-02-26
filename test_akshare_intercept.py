import akshare as ak
import requests
import urllib.parse

original_get = requests.get

def mock_get(url, **kwargs):
    print("----- Intercepted requests.get -----")
    print("URL:", url)
    print("kwargs:", kwargs)
    print("Constructed URL:", url + "?" + urllib.parse.urlencode(kwargs.get("params", {})))
    print("------------------------------------")
    return original_get(url, **kwargs)

requests.get = mock_get

try:
    print("Calling akshare...")
    df = ak.stock_zh_a_hist_min_em(symbol="000833", period='30', adjust='qfq')
    print("Success! Length:", len(df))
except Exception as e:
    print("Failed:", e)
