#!/usr/bin/env python3
"""
酷澎分潤連結自動產生器
使用 Coupang Partners Open API (HMAC SHA256 簽章)
自動把任何酷澎商品網址 → 分潤連結 + coupa.ng 短網址
"""

import hashlib
import hmac
import json
import os
import re
import time
import urllib.parse
import requests
from pathlib import Path
from datetime import datetime, timezone

# === 設定 ===
# 去 partners.tw.coupang.com → OpenAPI 管理 申請
ACCESS_KEY = os.environ.get("COUPANG_ACCESS_KEY", "")
SECRET_KEY = os.environ.get("COUPANG_SECRET_KEY", "")
AFFILIATE_ID = "AF1508181"  # 你的分潤 ID

DOMAIN = "https://partners.coupang.com"
DEEPLINK_PATH = "/api/v2/deeplink"

def generate_signature(method: str, path: str, secret_key: str) -> tuple[str, str]:
    """產生 HMAC SHA256 簽章，回傳 (authorization, datetime)"""
    now = datetime.now(timezone.utc)
    dt = now.strftime("%y%m%d")
    # Coupang 的 signature 格式: CEAP xx:yy
    message = f"{method}\n{path}\n{dt}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest().upper()
    
    authorization = f"CEA {ACCESS_KEY}:{signature}"
    return authorization, dt

def generate_deeplink(coupang_url: str) -> dict:
    """
    把酷澎商品網址轉成分潤連結
    
    參數:
        coupang_url: 酷澎商品網址 (例如 https://www.tw.coupang.com/products/...)
    
    回傳:
        { "original_url": str, "deeplink_url": str, "shorten_url": str or None, "error": str or None }
    """
    if not ACCESS_KEY or not SECRET_KEY:
        return {
            "error": "請先設定 COUPANG_ACCESS_KEY 和 COUPANG_SECRET_KEY 環境變數",
            "hint": "前往 partners.tw.coupang.com → OpenAPI 管理 申請"
        }
    
    # 準備請求
    path = DEEPLINK_PATH
    authorization, dt = generate_signature("POST", path, SECRET_KEY)
    
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json;charset=UTF-8",
    }
    
    payload = {
        "coupangUrls": [coupang_url]
    }
    
    url = f"{DOMAIN}{path}"
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Coupang 回傳格式通常像:
            # { "data": [ { "coupangUrl": "...", "deeplink": "...", "shortenUrl": "..." } ] }
            
            results = data.get("data", [])
            if results and len(results) > 0:
                result = results[0]
                return {
                    "original_url": result.get("coupangUrl", coupang_url),
                    "deeplink_url": result.get("deeplink", ""),
                    "shorten_url": result.get("shortenUrl", ""),
                }
            else:
                return {"error": f"API 回傳空的 data: {data}"}
        
        elif resp.status_code == 401:
            return {"error": "API 驗證失敗，請確認 AccessKey / SecretKey 是否正確"}
        elif resp.status_code == 403:
            return {"error": "API 權限不足，可能需要等待審核 (審核時間約 24 小時)"}
        else:
            return {"error": f"API 錯誤 ({resp.status_code}): {resp.text[:200]}"}
    
    except requests.exceptions.Timeout:
        return {"error": "API 請求超時"}
    except Exception as e:
        return {"error": str(e)}

def batch_generate_deeplink(urls: list[str]) -> list[dict]:
    """批次產生多個分潤連結 (Coupang API 支援一次多個)"""
    results = []
    
    # API 限制一次最多 50 個，分批處理
    batch_size = 50
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i+batch_size]
        
        for url in batch:
            result = generate_deeplink(url)
            results.append(result)
    
    return results

def extract_product_id_from_url(url: str) -> str | None:
    """從酷澎商品 URL 提取商品 ID"""
    # 格式: https://www.tw.coupang.com/products/xxxxxxxxxxxx
    match = re.search(r'/products/(\d+)', url)
    if match:
        return match.group(1)
    return None

def add_affiliate_id_to_url(url: str) -> str:
    """手動附加分潤 ID (備用方案，當 API 不能用時)"""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    
    # 常見的酷澎分潤參數
    params["vendorItemId"] = [AFFILIATE_ID]  # 可能不是這個參數
    
    new_query = urllib.parse.urlencode(params, doseq=True)
    new_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
    return new_url


# === 測試 & CLI ===
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("酷澎分潤連結產生器")
        print()
        print("用法:")
        print("  python3 deeplink.py <酷澎商品網址>")
        print("  python3 deeplink.py --batch <網址1> <網址2> ...")
        print()
        print("範例:")
        print("  python3 deeplink.py https://www.tw.coupang.com/products/xxxx")
        print()
        print("環境變數:")
        print("  COUPANG_ACCESS_KEY    - API Access Key")
        print("  COUPANG_SECRET_KEY    - API Secret Key")
        print()
        print("先去 partners.tw.coupang.com → OpenAPI 管理 申請")
        sys.exit(1)
    
    if sys.argv[1] == "--batch":
        urls = sys.argv[2:]
        results = batch_generate_deeplink(urls)
    else:
        url = sys.argv[1]
        result = generate_deeplink(url)
        results = [result]
    
    for r in results:
        if "error" in r:
            print(f"❌ {r['error']}")
        else:
            print(f"✅ 原始網址: {r['original_url']}")
            print(f"🔗 分潤連結: {r['deeplink_url']}")
            print(f"📎 短網址:   {r['shorten_url'] or '無'}")