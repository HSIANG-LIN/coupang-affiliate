#!/usr/bin/env python3
"""
酷澎價格監控 + 低點偵測 + Threads 文案產生器
核心系統
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# === 設定 ===
DATA_DIR = Path(__file__).parent  # 本地目錄
DATA_DIR.mkdir(parents=True, exist_ok=True)
PRICE_DB = DATA_DIR / "price_history.json"
PRODUCT_LIST = DATA_DIR / "products.json"
AFFILIATE_ID = "AF1508181"

# === 初始化商品清單 ===
DEFAULT_PRODUCTS = {
    "倍潔雅衛生紙": {
        "url": "https://www.tw.coupang.com/np/products/brand-shop?brandName=%E5%80%8D%E6%BD%94%E9%9B%85",
        "keywords": ["倍潔雅", "抽取式衛生紙", "150抽"],
        "category": "衛生紙",
        "last_price": None,
        "lowest_price": None,
        "highest_price": None,
    },
    "Ariel洗衣膠囊": {
        "url": "https://www.tw.coupang.com/np/products/brand-shop?brandName=ARIEL",
        "keywords": ["ARIEL", "4D抗菌洗衣膠囊", "洗衣球"],
        "category": "洗衣用品",
        "last_price": None,
        "lowest_price": None,
        "highest_price": None,
    },
    "愛康涼感衛生棉": {
        "url": None,
        "keywords": ["愛康", "涼感衛生棉", "icon"],
        "category": "衛生棉",
        "last_price": None,
        "lowest_price": None,
        "highest_price": None,
    },
    "韓國零食組合": {
        "url": None,
        "keywords": ["韓國零食", "酷澎", "熱銷"],
        "category": "零食",
        "last_price": None,
        "lowest_price": None,
        "highest_price": None,
    },
    "DHC維他命": {
        "url": "https://www.tw.coupang.com/products/DHC-%E5%8F%B0%E7%81%A3%E5%85%AC%E5%8F%B8%E8%B2%A8-%E6%B4%BB%E5%8A%9B%E7%B6%9C%E5%90%88%E7%B6%AD%E4%BB%96%E5%91%BD-201474885779465",
        "keywords": ["DHC", "維他命", "綜合維他命"],
        "category": "保健食品",
        "last_price": None,
        "lowest_price": None,
        "highest_price": None,
    },
}

def load_products():
    """載入商品清單"""
    if PRODUCT_LIST.exists():
        with open(PRODUCT_LIST) as f:
            return json.load(f)
    # 首次建立
    with open(PRODUCT_LIST, "w") as f:
        json.dump(DEFAULT_PRODUCTS, f, ensure_ascii=False, indent=2)
    return DEFAULT_PRODUCTS

def load_price_history():
    """載入價格歷史"""
    if PRICE_DB.exists():
        with open(PRICE_DB) as f:
            return json.load(f)
    return {}

def save_price_history(history):
    with open(PRICE_DB, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def fetch_coupang_price(product_name, product_info):
    """
    用 curl 抓酷澎商品頁，嘗試抽取價格
    回傳 (price_int, raw_text) 或 (None, error_msg)
    """
    url = product_info.get("url")
    if not url:
        return None, "無商品連結"

    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "10",
             "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
             "-H", "Accept-Language: zh-TW,zh;q=0.9",
             url],
            capture_output=True, text=True, timeout=15
        )
        html = result.stdout

        # 嘗試多種價格模式
        patterns = [
            r'(\d{1,3}(?:,\d{3})*)\s*元',
            r'NT\$\s*(\d{1,3}(?:,\d{3})*)',
            r'price["\']?\s*[:=]\s*["\']?(\d+)',
            r'折扣後價格[^\d]*(\d+)',
            r'(\d+)\s*元',
        ]
        
        prices = []
        for p in patterns:
            matches = re.findall(p, html)
            for m in matches:
                clean = m.replace(",", "")
                if clean.isdigit() and 10 < int(clean) < 10000:
                    prices.append(int(clean))
        
        if prices:
            # 取最低價（通常是折扣價）
            return min(prices), html[:500]
        
        return None, "找不到價格資訊（可能被擋）"
    
    except Exception as e:
        return None, str(e)

def check_price_drop(product_name, history, new_price):
    """檢查是否到達低點"""
    records = history.get(product_name, [])
    if len(records) < 2:
        return False, None
    
    prices = [r["price"] for r in records]
    avg_price = sum(prices) / len(prices)
    lowest = min(prices)
    
    if new_price < lowest:
        drop_pct = round((lowest - new_price) / lowest * 100, 1)
        return True, {
            "current": new_price,
            "lowest": lowest,
            "avg": round(avg_price),
            "drop_pct": drop_pct
        }
    
    return False, None

def generate_threads_post(product_name, price, deal_info=None):
    """產生 Threads 推薦文案"""
    emoji_map = {
        "倍潔雅衛生紙": "🧻",
        "Ariel洗衣膠囊": "🧴",
        "愛康涼感衛生棉": "🌸",
        "韓國零食組合": "🇰🇷",
        "DHC維他命": "💊",
    }
    emoji = emoji_map.get(product_name, "🛒")
    
    lines = [
        f"{emoji} 酷澎好物分享｜{product_name}",
        "",
    ]
    
    if deal_info:
        lines.append(f"🔥 價格來到低點了！比均價便宜 {deal_info['drop_pct']}%")
        lines.append(f"💵 現在只要 ${deal_info['current']} 元")
    else:
        lines.append(f"💵 目前價格 ${price} 元")
    
    lines += [
        "",
        "酷澎火箭速配隔天就到，不用扛回家🚀",
        "👇 連結下單，價格不變",
        f"https://coupa.ng/???  ← 分潤連結",
        "",
        f"#酷澎 #Coupang #{product_name.replace(' ','')} #省錢 #消耗品",
    ]
    
    return "\n".join(lines)

def record_price(product_name, price):
    """記錄一筆價格"""
    history = load_price_history()
    if product_name not in history:
        history[product_name] = []
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    history[product_name].append({
        "price": price,
        "time": now
    })
    
    # 只保留最近 90 筆
    if len(history[product_name]) > 90:
        history[product_name] = history[product_name][-90:]
    
    save_price_history(history)
    return history

def scan_all_products():
    """掃描所有商品的價格"""
    products = load_products()
    history = load_price_history()
    results = []
    
    for name, info in products.items():
        price, msg = fetch_coupang_price(name, info)
        
        if price:
            history = record_price(name, price)
            is_drop, deal_info = check_price_drop(name, history, price)
            
            results.append({
                "name": name,
                "price": price,
                "msg": f"✅ ${price}",
                "is_drop": is_drop,
                "deal_info": deal_info
            })
        else:
            results.append({
                "name": name,
                "price": None,
                "msg": f"❌ {msg}",
                "is_drop": False,
                "deal_info": None
            })
    
    return results

def get_price_summary(product_name):
    """取得某商品價格摘要"""
    history = load_price_history()
    records = history.get(product_name, [])
    if not records:
        return "尚無價格記錄"
    
    prices = [r["price"] for r in records]
    latest = prices[-1]
    lowest = min(prices)
    highest = max(prices)
    avg = round(sum(prices) / len(prices))
    
    return {
        "latest": latest,
        "lowest": lowest,
        "highest": highest,
        "avg": avg,
        "records": len(records),
        "days": len(set(r["time"][:10] for r in records))
    }

def add_product(name, url=None, keywords=None, category=None):
    """手動新增商品"""
    products = load_products()
    products[name] = {
        "url": url,
        "keywords": keywords or [],
        "category": category or "未分類",
        "last_price": None,
        "lowest_price": None,
        "highest_price": None,
    }
    with open(PRODUCT_LIST, "w") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    return f"✅ 已新增商品：{name}"

# === CLI 介面 ===
def report_price(product_name, price, note=""):
    """手動回報價格（你用 Telegram 或 CLI 呼叫）"""
    history = load_price_history()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if product_name not in history:
        history[product_name] = []
    
    history[product_name].append({
        "price": price,
        "time": now,
        "note": note
    })
    
    # 只保留最近 90 筆
    if len(history[product_name]) > 90:
        history[product_name] = history[product_name][-90:]
    
    save_price_history(history)
    
    # 檢查是否低點
    records = history[product_name]
    prices = [r["price"] for r in records]
    lowest = min(prices)
    avg = round(sum(prices) / len(prices))
    
    lines = [
        f"✅ 已記錄：{product_name} = ${price}",
        f"📊 歷史最低：${lowest} | 均價：${avg} | 記錄數：{len(records)}",
    ]
    
    if price <= lowest:
        drop_pct = round((avg - price) / avg * 100, 1)
        lines.append(f"🔥 這是歷史低點！比均價便宜 {drop_pct}%")
        lines.append("")
        lines.append(generate_threads_post(product_name, price, {
            "current": price,
            "lowest": lowest,
            "avg": avg,
            "drop_pct": drop_pct
        }))
    
    return "\n".join(lines)

def list_products():
    """列出所有商品及摘要"""
    products = load_products()
    history = load_price_history()
    lines = ["📋 追蹤商品清單："]
    for name in products:
        records = history.get(name, [])
        if records:
            prices = [r["price"] for r in records]
            lines.append(f"  • {name}: 最新${prices[-1]} 最低${min(prices)} 均價${round(sum(prices)/len(prices))}")
        else:
            lines.append(f"  • {name}: 尚無價格記錄")
    return "\n".join(lines)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 coupang_tracker.py report NAME PRICE [備註]  # 回報價格")
        print("  python3 coupang_tracker.py summary                 # 顯示價格摘要")
        print("  python3 coupang_tracker.py list                    # 列出追蹤商品")
        print("  python3 coupang_tracker.py post NAME               # 產生 Threads 文案")
        print("  python3 coupang_tracker.py add NAME [URL]          # 新增商品")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "report":
        if len(sys.argv) < 4:
            print("用法: python3 coupang_tracker.py report NAME PRICE")
            sys.exit(1)
        name = sys.argv[2]
        price = int(sys.argv[3].replace(",", "").replace("$", ""))
        note = sys.argv[4] if len(sys.argv) > 4 else ""
        print(report_price(name, price, note))
    
    elif cmd == "summary":
        products = load_products()
        for name in products:
            s = get_price_summary(name)
            if isinstance(s, dict):
                print(f"\n📊 {name} 價格摘要：")
                print(f"  最新：${s['latest']}")
                print(f"  最低：${s['lowest']}")
                print(f"  最高：${s['highest']}")
                print(f"  均價：${s['avg']}")
                print(f"  記錄數：{s['records']} 筆 / {s['days']} 天")
            else:
                print(f"\n{name}: {s}")
    
    elif cmd == "list":
        print(list_products())
    
    elif cmd == "add":
        if len(sys.argv) < 3:
            print("請指定商品名稱")
            sys.exit(1)
        name = sys.argv[2]
        url = sys.argv[3] if len(sys.argv) > 3 else None
        print(add_product(name, url))
    
    elif cmd == "post":
        if len(sys.argv) < 3:
            print("請指定商品名稱")
            sys.exit(1)
        name = sys.argv[2]
        summary = get_price_summary(name)
        if isinstance(summary, str):
            print(summary)
        else:
            deal_info = None
            records = load_price_history().get(name, [])
            if records:
                prices = [r["price"] for r in records]
                avg = round(sum(prices) / len(prices))
                if summary["latest"] <= summary["lowest"]:
                    drop_pct = round((avg - summary["latest"]) / avg * 100, 1)
                    deal_info = {
                        "current": summary["latest"],
                        "lowest": summary["lowest"],
                        "avg": avg,
                        "drop_pct": drop_pct
                    }
            print(generate_threads_post(name, summary["latest"], deal_info))
    
    else:
        print(f"未知指令：{cmd}")