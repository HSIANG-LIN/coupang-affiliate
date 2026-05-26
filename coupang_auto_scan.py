#!/usr/bin/env python3
"""
酷澎自動價格掃描 + 低點警示
用途: cron 定期執行，掃描金盒子 + 追蹤商品，記錄價格，低點自動推播

輸出:
  - 更新 price_history.json
  - 價格跌到歷史低點時輸出警示文案（供 cron deliver 推播）
  - 無異常時靜默（不推播）
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

# === 路徑 ===
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR
PRICE_DB = DATA_DIR / "price_history.json"
PRODUCTS_FILE = DATA_DIR / "products.json"
GOLDBOX_CACHE = DATA_DIR / "data" / "goldbox_latest.json"
SCAN_LOG = DATA_DIR / "data" / "auto_scan.log"

# 確保 data 目錄存在
(DATA_DIR / "data").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(SCRIPT_DIR))
from coupang_api import search_products, get_goldbox, generate_deeplink
from coupang_compare import search_momo, search_shopee, search_pchome
from coupang_tracker import generate_threads_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(SCAN_LOG), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("auto_scan")

AFFILIATE_ID = "AF1508181"


# ═══════════════════════════════════════════════════
# 資料讀寫
# ═══════════════════════════════════════════════════

def load_json(path, default=None):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_products():
    return load_json(PRODUCTS_FILE, {})


def load_price_history():
    return load_json(PRICE_DB, {})


def save_price_history(history):
    save_json(PRICE_DB, history)


# ═══════════════════════════════════════════════════
# 價格記錄 + 低點偵測
# ═══════════════════════════════════════════════════

def record_price(history, product_name, price, source="api"):
    """記錄一筆價格，回傳 (is_new_low, stats_dict)"""
    if product_name not in history:
        history[product_name] = []

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    history[product_name].append({
        "price": price,
        "time": now,
        "source": source,
    })

    # 只保留最近 180 筆
    if len(history[product_name]) > 180:
        history[product_name] = history[product_name][-180:]

    records = history[product_name]
    prices = [r["price"] for r in records]
    current_lowest = min(prices)
    avg = round(sum(prices) / len(prices))

    # 判斷是否新低（排除第一筆）
    is_new_low = False
    if len(prices) >= 2:
        prev_prices = prices[:-1]
        prev_lowest = min(prev_prices)
        if price < prev_lowest:
            is_new_low = True

    stats = {
        "current": price,
        "lowest": current_lowest,
        "avg": avg,
        "records": len(records),
        "drop_pct": round((avg - price) / avg * 100, 1) if avg > 0 and price < avg else 0,
    }

    return is_new_low, stats


# ═══════════════════════════════════════════════════
# 掃描金盒子
# ═══════════════════════════════════════════════════

def scan_goldbox(history):
    """掃描每日金盒子，記錄價格，回傳新低商品"""
    log.info("掃描金盒子...")
    alerts = []

    try:
        resp = get_goldbox()
        products = resp.get("data", [])
        if not products:
            log.info("  金盒子無商品")
            return alerts

        log.info(f"  金盒子 {len(products)} 檔商品")

        # 快取金盒子資料
        save_json(GOLDBOX_CACHE, {
            "scan_time": datetime.now().isoformat(),
            "products": products,
        })

        for p in products:
            name = p.get("productName", "unknown")
            price = p.get("productPrice", 0)
            pid = p.get("productId", "")

            if not price or price <= 0:
                continue

            # 用 productId 作為唯一識別
            key = f"goldbox_{pid}"
            is_new_low, stats = record_price(history, key, price, source="goldbox")

            if is_new_low:
                alerts.append({
                    "name": name,
                    "price": price,
                    "stats": stats,
                    "url": p.get("productUrl", ""),
                    "source": "goldbox",
                })

        # 篩選值得推廣的（火箭、價格 < 500 的日用品）
        good_deals = []
        for p in products:
            if p.get("isRocket") and p.get("productPrice", 9999) < 500:
                good_deals.append({
                    "name": p["productName"],
                    "price": p["productPrice"],
                    "url": p.get("productUrl", ""),
                    "image": p.get("productImage", ""),
                })

        if good_deals:
            log.info(f"  🔥 低價火箭商品: {len(good_deals)} 檔")

    except Exception as e:
        log.error(f"  金盒子掃描失敗: {e}")

    return alerts


# ═══════════════════════════════════════════════════
# 掃描追蹤商品
# ═══════════════════════════════════════════════════

# ═══════════════════════════════════════════════════
# 跨平台比價
# ═══════════════════════════════════════════════════

COMPARE_DB = DATA_DIR / "data" / "price_compare_latest.json"


def cross_platform_compare(keyword, coupang_price=None):
    """
    搜尋同一關鍵字在各平台的價格
    回傳 {platform: cheapest_item} + overall_cheapest
    """
    platforms = {}

    # 酷澎（已有價格就不用再查）
    if coupang_price:
        platforms["coupang"] = {"price": coupang_price, "platform": "coupang"}

    # momo
    try:
        momo_results = search_momo(keyword, size=3)
        if momo_results:
            cheapest = min(momo_results, key=lambda x: x["price"])
            platforms["momo"] = cheapest
    except Exception as e:
        log.warning(f"  momo 比價失敗: {e}")

    # 蝦皮 (Playwright, 較慢，只比有追蹤的商品)
    try:
        shopee_results = search_shopee(keyword, size=3)
        if shopee_results:
            cheapest = min(shopee_results, key=lambda x: x["price"])
            platforms["shopee"] = cheapest
    except Exception as e:
        log.warning(f"  蝦皮 比價失敗: {e}")

    # PChome (Playwright)
    try:
        pchome_results = search_pchome(keyword, size=3)
        if pchome_results:
            cheapest = min(pchome_results, key=lambda x: x["price"])
            platforms["pchome"] = cheapest
    except Exception as e:
        log.warning(f"  PChome 比價失敗: {e}")

    # 找整體最低
    overall = None
    if platforms:
        overall = min(platforms.values(), key=lambda x: x.get("price", 999999))

    return {
        "keyword": keyword,
        "platforms": platforms,
        "overall_cheapest": overall,
    }


def scan_tracked_products(history, do_compare=False):
    """用 API 搜尋追蹤商品，記錄價格，回傳新低商品"""
    log.info("掃描追蹤商品...")
    products = load_products()
    alerts = []
    compare_results = []

    for name, info in products.items():
        keywords = info.get("keywords", [])
        if not keywords:
            continue

        try:
            # 用第一個關鍵字搜尋
            resp = search_products(keywords[0], size=5)
            product_data = resp.get("data", {}).get("productData", [])

            if not product_data:
                log.info(f"  {name}: 搜尋無結果")
                continue

            # 找最符合的商品
            best_match = None
            for pd in product_data:
                pname = pd.get("productName", "")
                # 簡單匹配：關鍵字出現在商品名中
                match_count = sum(1 for kw in keywords if kw in pname)
                if match_count >= 2 or (match_count >= 1 and not best_match):
                    best_match = pd
                    if match_count >= 2:
                        break

            if not best_match:
                best_match = product_data[0]  # 退而求其次

            price = best_match.get("productPrice", 0)
            if not price or price <= 0:
                continue

            is_new_low, stats = record_price(history, name, price, source="search")

            log.info(f"  {name}: ${price} (最低${stats['lowest']} 均價${stats['avg']})")

            if is_new_low:
                alerts.append({
                    "name": name,
                    "price": price,
                    "stats": stats,
                    "url": best_match.get("productUrl", ""),
                    "source": "search",
                })

            # 更新 products.json 的 last_price
            info["last_price"] = price
            info["lowest_price"] = stats["lowest"]
            info["highest_price"] = max([r["price"] for r in history.get(name, [])] or [price])

            # 跨平台比價（只比有追蹤的商品）
            if do_compare:
                try:
                    cmp = cross_platform_compare(keywords[0], coupang_price=price)
                    cmp["product_name"] = name
                    compare_results.append(cmp)
                    time.sleep(2)
                except Exception as e:
                    log.warning(f"  {name} 比價失敗: {e}")

            time.sleep(1)  # API 限速

        except Exception as e:
            log.error(f"  {name} 掃描失敗: {e}")

    # 回寫 products.json
    save_json(PRODUCTS_FILE, products)

    # 儲存比價結果
    if compare_results:
        save_json(COMPARE_DB, {
            "last_compare": datetime.now().isoformat(),
            "results": compare_results,
        })

    return alerts, compare_results


# ═══════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true", help="啟用跨平台比價")
    args = parser.parse_args()

    log.info("=" * 50)
    log.info("開始自動掃描")

    history = load_price_history()
    all_alerts = []

    # 1. 掃描金盒子
    goldbox_alerts = scan_goldbox(history)
    all_alerts.extend(goldbox_alerts)

    # 2. 掃描追蹤商品 + 比價
    tracked_alerts, compare_results = scan_tracked_products(history, do_compare=args.compare)
    all_alerts.extend(tracked_alerts)

    # 3. 儲存
    save_price_history(history)
    log.info(f"價格資料已更新 ({sum(len(v) for v in history.values())} 筆)")

    # 4. 輸出警示（供 cron 推播）+ 自動生成 Threads 文案
    output_lines = []

    if all_alerts:
        output_lines.append("🔥 酷澎價格警示 + Threads 文案")
        output_lines.append("")
        for a in all_alerts:
            s = a["stats"]
            output_lines.append(f"📉 {a['name']}")
            output_lines.append(f"   現在 ${a['price']} (歷史低！均價 ${s['avg']}，便宜 {s['drop_pct']}%)")
            if a.get("url"):
                output_lines.append(f"   {a['url']}")
            output_lines.append("")

            # 自動生成 Threads 文案
            deal_info = {
                "current": a["price"],
                "lowest": s["lowest"],
                "avg": s["avg"],
                "drop_pct": s["drop_pct"],
            }
            post = generate_threads_post(a["name"], a["price"], deal_info)
            output_lines.append("📝 可直接複製的 Threads 文案：")
            output_lines.append("---")
            output_lines.append(post)
            output_lines.append("---")
            output_lines.append("")

        output_lines.append("⚠️ 我可能會從合作夥伴的活動中收取佣金")

    # 5. 輸出比價結果
    if compare_results:
        output_lines.append("")
        output_lines.append("📊 跨平台比價結果")
        output_lines.append("")
        for cmp in compare_results:
            pname = cmp.get("product_name", cmp.get("keyword", ""))
            platforms = cmp.get("platforms", {})
            overall = cmp.get("overall_cheapest")

            if not platforms:
                continue

            output_lines.append(f"🔍 {pname}")
            for plat, item in sorted(platforms.items(), key=lambda x: x[1].get("price", 999999)):
                price = item.get("price", "?")
                marker = "👑" if overall and price == overall.get("price") else "  "
                output_lines.append(f"  {marker} {plat}: ${price}")
            if overall:
                output_lines.append(f"  🏆 最低: {overall.get('platform', '?')} ${overall.get('price', '?')}")
            output_lines.append("")

    if output_lines:
        print("\n".join(output_lines))
    else:
        log.info("無低點警示，靜默處理")

    log.info("掃描完成")
    return len(all_alerts)


if __name__ == "__main__":
    alerts = main()
    sys.exit(0)
