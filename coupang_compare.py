#!/usr/bin/env python3
"""
跨平台比價引擎
搜尋同一商品在 momo / 蝦皮 / PChome / 酷澎 的價格，找出真正最低價

平台策略:
  - 酷澎: Partners API (最快最準)
  - momo: curl + JSON-LD 結構化資料 (穩定)
  - 蝦皮: Playwright 瀏覽器 (反爬嚴格)
  - PChome: Playwright 瀏覽器 (Next.js JS 渲染)
"""

import json
import os
import re
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

COMPARE_DB = DATA_DIR / "price_compare.json"
COMPARE_LOG = DATA_DIR / "price_compare.log"

sys.path.insert(0, str(SCRIPT_DIR))
from coupang_api import search_products

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(COMPARE_LOG), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("price_compare")


# ═══════════════════════════════════════════════════
# 平台 1: 酷澎 (API)
# ═══════════════════════════════════════════════════

def search_coupang(keyword, size=5):
    """用 Coupang API 搜尋"""
    try:
        resp = search_products(keyword, size=size)
        items = resp.get("data", {}).get("productData", [])
        results = []
        for p in items:
            price = p.get("productPrice", 0)
            if price and price > 0:
                first_price = p.get("firstPurchasePrice", 0)
                results.append({
                    "platform": "coupang",
                    "name": p.get("productName", ""),
                    "price": price,
                    "first_price": first_price if first_price and first_price < price else None,
                    "url": p.get("productUrl", ""),
                    "image": p.get("productImage", ""),
                    "is_rocket": p.get("isRocket", False),
                })
        return results
    except Exception as e:
        log.error(f"Coupang 搜尋失敗: {e}")
        return []


# ═══════════════════════════════════════════════════
# 平台 2: momo (curl + JSON-LD)
# ═══════════════════════════════════════════════════

def search_momo(keyword, size=5):
    """用 curl 抓 momo 搜尋頁，解析 JSON-LD"""
    import subprocess
    try:
        url = f"https://www.momoshop.com.tw/search/searchShop.jsp?keyword={quote(keyword)}"
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", "10",
             "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
             url],
            capture_output=True, text=True, timeout=15
        )
        html = result.stdout

        # 解析 JSON-LD
        matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            html, re.DOTALL
        )

        results = []
        for m in matches:
            try:
                data = json.loads(m)
                if isinstance(data, dict) and "@graph" in data:
                    for item in data["@graph"]:
                        if item.get("@type") == "ItemList":
                            for prod in item.get("itemListElement", [])[:size]:
                                offers = prod.get("offers", {})
                                price = offers.get("price", 0)
                                if price and price > 0:
                                    results.append({
                                        "platform": "momo",
                                        "name": prod.get("name", ""),
                                        "price": price,
                                        "url": prod.get("url", ""),
                                        "image": prod.get("image", ""),
                                        "rating": prod.get("aggregateRating", {}).get("ratingValue"),
                                    })
            except json.JSONDecodeError:
                continue

        return results[:size]
    except Exception as e:
        log.error(f"momo 搜尋失敗: {e}")
        return []


# ═══════════════════════════════════════════════════
# 平台 3 & 4: 蝦皮 / PChome (Playwright)
# ═══════════════════════════════════════════════════

def _search_with_playwright(keyword, platform, size=5):
    """用 Playwright 瀏覽器搜尋蝦皮或 PChome"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Playwright 未安裝")
        return []

    if platform == "shopee":
        search_url = f"https://shopee.tw/search?keyword={quote(keyword)}&sortBy=price&order=asc"
    elif platform == "pchome":
        search_url = f"https://24h.pchome.com.tw/search/?q={quote(keyword)}"
    else:
        return []

    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)  # 等 JS 渲染

            if platform == "shopee":
                # 蝦皮: 解析搜尋結果
                items = page.query_selector_all('[data-sqe="item"]')
                if not items:
                    items = page.query_selector_all('.shopee-search-item-result__item')

                for item in items[:size]:
                    try:
                        name_el = item.query_selector('.line-clamp-2, .ie3A\\+n, .shopee-search-item-result__item-name')
                        price_el = item.query_selector('.price, .ooOxS, .shopee-search-item-result__item-price')
                        link_el = item.query_selector('a')

                        name = name_el.inner_text() if name_el else ""
                        price_text = price_el.inner_text() if price_el else "0"
                        price = int(re.sub(r'[^\d]', '', price_text.split('$')[-1]) or 0)
                        url = link_el.get_attribute("href") if link_el else ""
                        if url and not url.startswith("http"):
                            url = "https://shopee.tw" + url

                        if price > 0 and name:
                            results.append({
                                "platform": "shopee",
                                "name": name.strip()[:80],
                                "price": price,
                                "url": url,
                            })
                    except Exception:
                        continue

            elif platform == "pchome":
                # PChome: 解析搜尋結果
                items = page.query_selector_all('.product, .prod_item, [class*="Product"]')
                if not items:
                    # 嘗試 Next.js RSC 資料
                    content = page.content()
                    # 找價格模式
                    price_matches = re.findall(r'"price":(\d+)', content)
                    name_matches = re.findall(r'"prdname":"([^"]+)"', content)
                    if not name_matches:
                        name_matches = re.findall(r'"name":"([^"]{5,50})"', content)

                    for i in range(min(len(price_matches), len(name_matches), size)):
                        price = int(price_matches[i])
                        if price > 0:
                            results.append({
                                "platform": "pchome",
                                "name": name_matches[i],
                                "price": price,
                                "url": f"https://24h.pchome.com.tw/search/?q={quote(keyword)}",
                            })
                else:
                    for item in items[:size]:
                        try:
                            name_el = item.query_selector('.prod_name a, .prd-name a, h3, .name')
                            price_el = item.query_selector('.price, .prod_price, .money, [class*="price"]')
                            link_el = item.query_selector('a')

                            name = name_el.inner_text() if name_el else ""
                            price_text = price_el.inner_text() if price_el else "0"
                            price = int(re.sub(r'[^\d]', '', price_text) or 0)
                            url = link_el.get_attribute("href") if link_el else ""
                            if url and not url.startswith("http"):
                                url = "https://24h.pchome.com.tw" + url

                            if price > 0 and name:
                                results.append({
                                    "platform": "pchome",
                                    "name": name.strip()[:80],
                                    "price": price,
                                    "url": url,
                                })
                        except Exception:
                            continue

            browser.close()

    except Exception as e:
        log.error(f"Playwright {platform} 搜尋失敗: {e}")

    return results


def search_shopee(keyword, size=5):
    return _search_with_playwright(keyword, "shopee", size)


def search_pchome(keyword, size=5):
    return _search_with_playwright(keyword, "pchome", size)


# ═══════════════════════════════════════════════════
# 綜合比價
# ═══════════════════════════════════════════════════

def compare_prices(keyword, platforms=None):
    """
    搜尋同一關鍵字在所有平台的價格
    回傳 {platform: [results]} + 最低價摘要
    """
    if platforms is None:
        platforms = ["coupang", "momo", "shopee", "pchome"]

    all_results = {}

    for plat in platforms:
        log.info(f"  搜尋 {plat}...")
        if plat == "coupang":
            results = search_coupang(keyword)
        elif plat == "momo":
            results = search_momo(keyword)
        elif plat == "shopee":
            results = search_shopee(keyword)
        elif plat == "pchome":
            results = search_pchome(keyword)
        else:
            results = []

        all_results[plat] = results
        time.sleep(1)  # 平台間間隔

    # 找各平台最低價
    platform_cheapest = {}
    for plat, results in all_results.items():
        if results:
            cheapest = min(results, key=lambda x: x["price"])
            platform_cheapest[plat] = cheapest

    # 找整體最低價
    overall_cheapest = None
    if platform_cheapest:
        overall_cheapest = min(platform_cheapest.values(), key=lambda x: x["price"])

    return {
        "keyword": keyword,
        "timestamp": datetime.now().isoformat(),
        "platforms": all_results,
        "cheapest_per_platform": platform_cheapest,
        "overall_cheapest": overall_cheapest,
    }


def format_compare_result(result):
    """格式化比價結果"""
    keyword = result["keyword"]
    cheapest_per = result["cheapest_per_platform"]
    overall = result["overall_cheapest"]

    lines = [f"🔍 比價結果: {keyword}", ""]

    if not cheapest_per:
        lines.append("❌ 所有平台都找不到商品")
        return "\n".join(lines)

    # 各平台最低價
    for plat, item in sorted(cheapest_per.items(), key=lambda x: x[1]["price"]):
        marker = "👑" if overall and item["price"] == overall["price"] else "  "
        first = f" (首購 ${item['first_price']})" if item.get("first_price") else ""
        rocket = " 🚀" if item.get("is_rocket") else ""
        lines.append(f"{marker} {plat}: ${item['price']}{first}{rocket}")
        lines.append(f"    {item['name'][:50]}")
        if item.get("url"):
            lines.append(f"    {item['url']}")
        lines.append("")

    # 最低價摘要
    if overall:
        lines.append(f"🏆 最低價: {overall['platform']} ${overall['price']}")
        lines.append(f"   {overall['name'][:60]}")

    # 價格差異
    prices = [item["price"] for item in cheapest_per.values()]
    if len(prices) >= 2:
        diff = max(prices) - min(prices)
        diff_pct = round(diff / max(prices) * 100, 1)
        lines.append(f"   最高 vs 最低差 ${diff} ({diff_pct}%)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════
# 追蹤商品自動比價
# ═══════════════════════════════════════════════════

def auto_compare_tracked():
    """自動比價所有追蹤商品"""
    products_file = SCRIPT_DIR / "products.json"
    if not products_file.exists():
        return []

    with open(products_file) as f:
        products = json.load(f)

    all_results = []
    for name, info in products.items():
        keywords = info.get("keywords", [])
        if not keywords:
            continue

        keyword = keywords[0]  # 用第一個關鍵字
        log.info(f"比價: {name} ({keyword})")

        result = compare_prices(keyword)
        result["product_name"] = name
        all_results.append(result)

        time.sleep(2)

    # 儲存
    with open(COMPARE_DB, "w") as f:
        json.dump({
            "last_compare": datetime.now().isoformat(),
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    return all_results


# ═══════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 coupang_compare.py search 關鍵字     # 比價單一商品")
        print("  python3 coupang_compare.py auto              # 自動比價所有追蹤商品")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search" and len(sys.argv) >= 3:
        keyword = sys.argv[2]
        result = compare_prices(keyword)
        print(format_compare_result(result))

    elif cmd == "auto":
        results = auto_compare_tracked()
        for r in results:
            print(format_compare_result(r))
            print("")

    else:
        print("未知指令")
