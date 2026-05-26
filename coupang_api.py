#!/usr/bin/env python3
"""
Coupang Partners Open API Client
HMAC-SHA256 簽章 + 商品搜尋/每日特價/分潤連結
"""

import hashlib
import hmac
import json
import os
import requests
from time import gmtime, strftime
from pathlib import Path
from urllib.parse import urlencode

# === 載入 .env ===
_ENV_PATH = Path(__file__).parent / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ACCESS_KEY = os.environ.get("COUPANG_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("COUPANG_SECRET_KEY", "")

DOMAIN = "https://api-gateway.tw.coupang.com"
API_PREFIX = "/v2/providers/affiliate_open_api/apis/openapi/v1"


# === HMAC 簽章 (完全依照官方 Python 範例) ===
def _generate_hmac(method, url_path):
    """產生 Coupang API HMAC-SHA256 Authorization header"""
    path, *query = url_path.split("?")
    datetimeGMT = strftime('%y%m%d', gmtime()) + 'T' + strftime('%H%M%S', gmtime()) + 'Z'
    message = datetimeGMT + method + path + (query[0] if query else "")
    signature = hmac.new(
        bytes(SECRET_KEY, "utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "CEA algorithm=HmacSHA256, access-key={}, signed-date={}, signature={}".format(
        ACCESS_KEY, datetimeGMT, signature
    )


def _request(method, endpoint, params=None, payload=None):
    """通用 API 請求"""
    url_path = API_PREFIX + endpoint
    if params and method == "GET":
        query = urlencode(params)
        url_path += "?" + query

    url = f"{DOMAIN}{url_path}"
    authorization = _generate_hmac(method, url_path)
    headers = {"Authorization": authorization, "Content-Type": "application/json"}

    if method == "GET":
        resp = requests.get(url, headers=headers, timeout=15)
    else:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
    return resp.json()


# === Products API ===
def search_products(keyword, page=1, size=20):
    """關鍵字搜尋商品 (每分鐘最多 50 次)"""
    return _request("GET", "/products/search", {"keyword": keyword, "page": page, "size": size})


def get_goldbox():
    """取得每日特價商品 (每天 07:30 更新)"""
    return _request("GET", "/products/goldbox")


def get_best_categories(category_id):
    """取得各類別最佳商品"""
    return _request("GET", f"/products/bestcategories/{category_id}")


def get_coupang_pl():
    """取得 Coupang PL 商品"""
    return _request("GET", "/products/coupangPL")


# === Links API ===
def generate_deeplink(urls):
    """將酷澎網址轉為分潤追蹤短網址"""
    return _request("POST", "/deeplink", payload={"coupangUrls": urls})


# === Reports API ===
def get_commission_report(start_date, end_date):
    """查詢分潤報表 (YYYYMMDD 格式)"""
    return _request("GET", "/reports/commission", {"startDate": start_date, "endDate": end_date})


def get_orders_report(start_date, end_date):
    """查詢訂單報表"""
    return _request("GET", "/reports/orders", {"startDate": start_date, "endDate": end_date})


# === CLI ===
if __name__ == "__main__":
    import sys
    if not ACCESS_KEY or not SECRET_KEY:
        print("❌ 請先設定 COUPANG_ACCESS_KEY 和 COUPANG_SECRET_KEY (coupang/.env)")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "goldbox"
    if cmd == "goldbox":
        print(json.dumps(get_goldbox(), indent=2, ensure_ascii=False))
    elif cmd == "search":
        kw = sys.argv[2] if len(sys.argv) > 2 else "衛生紙"
        print(json.dumps(search_products(kw), indent=2, ensure_ascii=False))
    elif cmd == "deeplink":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://www.tw.coupang.com"
        print(json.dumps(generate_deeplink([url]), indent=2, ensure_ascii=False))
    elif cmd == "pl":
        print(json.dumps(get_coupang_pl(), indent=2, ensure_ascii=False))
    elif cmd == "commission":
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y%m%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
        print(json.dumps(get_commission_report(week_ago, today), indent=2, ensure_ascii=False))
    else:
        print("用法: python3 coupang_api.py [goldbox|search <kw>|deeplink <url>|pl|commission]")
