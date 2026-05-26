#!/usr/bin/env python3
"""
酷澎高佣商品挖掘器
用途: cron 每天跑一次，掃描各分類找出高分潤率商品，推播值得推廣的品項

策略:
  1. 用搜尋 API 掃描高頻消耗品關鍵字（衛生紙、洗衣、清潔、零食...）
  2. 記錄每個商品的價格 + 分類 + 價格帶
  3. 篩選條件: 火箭商品 + 價格帶 $100-$2000（適合帶貨）
  4. 排除已追蹤商品，只推新發現的好貨
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DISCOVER_DB = DATA_DIR / "discovered_products.json"
DISCOVER_LOG = DATA_DIR / "discover.log"
PRODUCTS_FILE = SCRIPT_DIR / "products.json"

sys.path.insert(0, str(SCRIPT_DIR))
from coupang_api import search_products, generate_deeplink

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(DISCOVER_LOG), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("discover")

# ═══════════════════════════════════════════════════
# 掃描關鍵字（高頻消耗品 + 家庭用品）
# ═══════════════════════════════════════════════════

SCAN_KEYWORDS = [
    # 衛生紙/清潔
    "衛生紙", "濕紙巾", "廚房紙巾", "垃圾袋", "保鮮膜",
    # 洗衣/清潔
    "洗衣精", "洗衣膠囊", "洗碗精", "清潔劑", "漂白水",
    # 個人清潔
    "洗髮精", "沐浴乳", "牙膏", "刮鬍刀",
    # 食品
    "韓國零食", "泡麵", "咖啡", "茶葉", "牛奶",
    # 保健
    "維他命", "益生菌", "魚油",
    # 寢具/生活
    "毛巾", "枕頭", "拖鞋", "收納",
    # 寵物
    "貓砂", "寵物飼料",
]


def load_discovered():
    if DISCOVER_DB.exists():
        with open(DISCOVER_DB) as f:
            return json.load(f)
    return {"products": [], "last_scan": None}


def save_discovered(data):
    data["last_scan"] = datetime.now().isoformat()
    with open(DISCOVER_DB, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_tracked_names():
    """載入已追蹤商品名稱（排除用）"""
    if PRODUCTS_FILE.exists():
        with open(PRODUCTS_FILE) as f:
            products = json.load(f)
        # 建立名稱 + 關鍵字的集合
        names = set(products.keys())
        for info in products.values():
            names.update(info.get("keywords", []))
        return names
    return set()


def discover_products():
    """掃描各關鍵字，挖掘值得推廣的商品"""
    log.info("=" * 50)
    log.info("開始高佣商品挖掘")

    discovered = load_discovered()
    tracked_names = load_tracked_names()
    existing_ids = {str(p.get("productId")) for p in discovered.get("products", [])}

    new_products = []
    seen_ids = set()

    for kw in SCAN_KEYWORDS:
        try:
            log.info(f"  掃描: {kw}")
            resp = search_products(kw, size=10)
            product_data = resp.get("data", {}).get("productData", [])

            if not product_data:
                continue

            for p in product_data:
                pid = str(p.get("productId", ""))
                name = p.get("productName", "")
                price = p.get("productPrice", 0)
                is_rocket = p.get("isRocket", False)
                category = p.get("categoryName", "")
                first_price = p.get("firstPurchasePrice", 0)

                # 基本篩選
                if not price or price <= 0:
                    continue
                if pid in seen_ids or pid in existing_ids:
                    continue
                if not is_rocket:
                    continue  # 只要火箭商品
                if price < 50 or price > 3000:
                    continue  # 價格帶篩選

                # 排除已追蹤的
                name_lower = name.lower()
                if any(t.lower() in name_lower for t in tracked_names):
                    continue

                # 計算分數（簡單 heuristic）
                score = 0
                # 價格帶加分: $100-$800 最佳（消耗品甜蜜點）
                if 100 <= price <= 800:
                    score += 3
                elif 800 < price <= 2000:
                    score += 1
                # 首購價有折扣加分
                if first_price and first_price < price:
                    discount = round((price - first_price) / price * 100)
                    score += min(discount // 5, 3)
                # 消耗品關鍵字加分
                consumable_kw = ["衛生紙", "洗衣", "洗碗", "清潔", "濕紙巾", "垃圾袋", "貓砂", "飼料", "咖啡", "泡麵"]
                if any(ck in name for ck in consumable_kw):
                    score += 2

                if score < 2:
                    continue

                product_entry = {
                    "productId": pid,
                    "name": name,
                    "price": price,
                    "firstPurchasePrice": first_price,
                    "category": category,
                    "isRocket": is_rocket,
                    "url": p.get("productUrl", ""),
                    "image": p.get("productImage", ""),
                    "score": score,
                    "discovered": datetime.now().strftime("%Y-%m-%d"),
                    "searchKeyword": kw,
                }

                new_products.append(product_entry)
                seen_ids.add(pid)

            time.sleep(1)  # API 限速

        except Exception as e:
            log.error(f"  {kw} 掃描失敗: {e}")
            time.sleep(2)

    # 排序: 分數高的在前
    new_products.sort(key=lambda x: x["score"], reverse=True)

    # 加入資料庫（最多保留 200 筆）
    discovered["products"].extend(new_products)
    discovered["products"] = discovered["products"][-200:]

    save_discovered(discovered)
    log.info(f"挖掘完成: 新增 {len(new_products)} 檔商品")

    # 自動加入追蹤清單（分數 >= 7 的高分商品）
    auto_tracked = auto_add_to_tracking(new_products)

    return new_products, auto_tracked


def auto_add_to_tracking(new_products):
    """分數 >= 7 的商品自動加入追蹤清單"""
    TRACKING_FILE = SCRIPT_DIR / "products.json"
    AUTO_TRACK_SCORE = 7  # 只追蹤高分商品

    # 載入現有追蹤清單
    existing = {}
    if TRACKING_FILE.exists():
        with open(TRACKING_FILE) as f:
            existing = json.load(f)

    added = []
    for p in new_products:
        if p.get("score", 0) < AUTO_TRACK_SCORE:
            continue

        name = p["name"][:30]  # 截短名稱
        if name in existing:
            continue

        # 從商品名提取關鍵字
        keywords = [p.get("searchKeyword", "")]
        # 加入品牌名（第一個詞）
        brand = name.split()[0] if name.split() else ""
        if brand and brand not in keywords:
            keywords.append(brand)

        existing[name] = {
            "url": p.get("url", ""),
            "keywords": keywords,
            "category": p.get("category", "未分類"),
            "last_price": p.get("price"),
            "lowest_price": p.get("price"),
            "highest_price": p.get("price"),
            "auto_added": datetime.now().strftime("%Y-%m-%d"),
        }
        added.append(name)
        log.info(f"  自動追蹤: {name} (${p['price']})")

    if added:
        with open(TRACKING_FILE, "w") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        log.info(f"自動加入追蹤: {len(added)} 檔")

    return added


def format_alert(new_products):
    """格式化推播訊息（只推 top 10）"""
    if not new_products:
        return ""

    top = new_products[:10]

    lines = ["🔍 酷澎新好貨挖掘", ""]
    lines.append(f"本次掃描新增 {len(new_products)} 檔高分商品")
    lines.append("")

    for i, p in enumerate(top, 1):
        fp = p.get("firstPurchasePrice", 0)
        price_line = f"${p['price']}"
        if fp and fp < p["price"]:
            price_line += f" (首購 ${fp})"

        lines.append(f"{i}. {p['name']}")
        lines.append(f"   💰 {price_line} | ⭐ 分數 {p['score']}")
        lines.append(f"   📁 {p['category']} | 🔍 {p['searchKeyword']}")
        if p.get("url"):
            lines.append(f"   🔗 {p['url']}")
        lines.append("")

    lines.append("⚠️ 我可能會從合作夥伴的活動中收取佣金")
    return "\n".join(lines)


def main():
    new_products, auto_tracked = discover_products()

    if new_products:
        alert = format_alert(new_products)
        print(alert)

        if auto_tracked:
            print(f"\n📌 自動加入追蹤: {len(auto_tracked)} 檔")
            for name in auto_tracked:
                print(f"  • {name}")
    else:
        log.info("無新高佣商品")

    return len(new_products)


if __name__ == "__main__":
    count = main()
    sys.exit(0)
