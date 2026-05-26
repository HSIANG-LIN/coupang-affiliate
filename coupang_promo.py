#!/usr/bin/env python3
"""
Coupang Promo Generator — 酷澎分潤文案自動產生器

用法:
  python3 coupang_promo.py new "商品名" 價格 "分潤連結" [--style casual|deal] [--note "補充資訊"]
  python3 coupang_promo.py dilemma "商品1" 價格1 "連結1" "商品2" 價格2 "連結2" [--note "補充"]
  python3 coupang_promo.py list                    # 列出待發文案
  python3 coupang_promo.py show <id>               # 顯示指定文案
  python3 coupang_promo.py approve <id>            # 標記為已發
"""

import json
import random
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent  # 本地目錄
DATA_DIR.mkdir(parents=True, exist_ok=True)
PROMO_QUEUE = DATA_DIR / "promo_queue.json"
PRICE_HISTORY = DATA_DIR / "price_history.json"

# === 文案結構 ===
# Simon 的 Threads 文案規則：
#   1. 生活場景開頭（家庭日常、被派去買東西、小孩的事）
#   2. 自然帶到商品和價格，一句話搞定
#   3. 連結
#   4. 可選：「喔對了」補一句額外資訊（會員價、規格等）
#
# 不要：驚嘆號、火焰 emoji、行銷用語、產品成分介紹、hashtag 超過 3 個

# === 生活場景池（按分類） ===
DILEMMA_OPENINGS = [
    "每次看到{product}都會猶豫",
    "{product} 放到購物車好幾次了",
    "一直在想{product}到底要不要買",
    "對{product}又愛又恨",
]

DILEMMA_MIDDLES = [
    "但真的買了之後大概就那樣",
    "可是我又怕買了會後悔",
    "但始終沒有下手",
    "買了覺得还好 不買又一直想",
]

DILEMMA_ENDINGS = [
    "是不是該買一個\n還是只是因為我沒買才會一直覺得要買",
    "到底是要繼續猶豫 還是直接買了斷",
    "每次都在想要不要算了",
    "是不是人就是得不到的才會一直想",
]

SCENARIOS = {
    "日用品": [
        "一家三口 每次都忘了買{product}",
        "被派去買{product} 結果在酷澎看到更便宜的",
        "家裡{product}又見底了",
        "每次逛超市都在想{product}有沒有更便宜的",
        "終於找到一次買齊{product}的方法",
    ],
    "零食": [
        "追劇的時候手邊沒東西吃",
        "小孩問我可不可以買{product}",
        "辦公室抽屜又空了",
        "朋友推薦的 結果酷澎就有賣",
        "被燒到了 下單之前先分享",
    ],
    "保健": [
        "開始注意身體了",
        "同事在吃的 說不錯",
        "偶然發現的 蠻便宜",
    ],
    "美妝": [
        "朋友推薦的 結果酷澎就有賣",
        "終於補貨了",
    ],
    "泡麵": [
        "半夜肚子餓",
        "不想煮飯的日子",
        "冰箱空了 又不想出門",
    ],
}

# === 价格表达方式 ===
PRICE_STYLE = {
    "casual": [
        "{price}",
        "才{price}",
        "一箱{price}",
    ],
    "deal": [
        "{price}（原價{original}）",
        "{price} 省了{saved}",
    ],
}

# === 結尾（可選） ===
ENDINGS = [
    "",  # 乾淨結束
    "隔天就到了 免運",
    "酷澎火箭速配 真的快",
    "送到家 不用自己扛",
]


def load_queue():
    if PROMO_QUEUE.exists():
        with open(PROMO_QUEUE) as f:
            return json.load(f)
    return []


def save_queue(queue):
    with open(PROMO_QUEUE, "w") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def load_price_history():
    if PRICE_HISTORY.exists():
        with open(PRICE_HISTORY) as f:
            return json.load(f)
    return {}


def get_price_context(product_name, current_price):
    """從價格歷史中取出上下文"""
    history = load_price_history()
    records = history.get(product_name, [])

    if not records:
        return {
            "lowest": current_price,
            "highest": current_price,
            "avg": current_price,
            "at_lowest": True,
            "drop_pct": 0,
            "record_count": 0,
        }

    prices = [r["price"] for r in records]
    avg = round(sum(prices) / len(prices))
    lowest = min(prices)

    return {
        "lowest": lowest,
        "highest": max(prices),
        "avg": avg,
        "at_lowest": current_price <= lowest,
        "drop_pct": round((avg - current_price) / avg * 100, 1) if avg > 0 else 0,
        "record_count": len(prices),
    }


def get_category(product_name):
    """根據商品名推斷分類"""
    name_lower = product_name.lower()
    if any(k in name_lower for k in ["餅乾", "零食", "泡芙", "洋芋片", "巧克力", "貝果", "杏仁"]):
        return "零食"
    if any(k in name_lower for k in ["衛生紙", "洗衣", "清潔", "尿布"]):
        return "日用品"
    if any(k in name_lower for k in ["維他命", "保健", "益生菌", "魚油"]):
        return "保健"
    if any(k in name_lower for k in ["美妝", "面膜", "化妝", "保養"]):
        return "美妝"
    if any(k in name_lower for k in ["泡麵", "拉麵", "辛拉麵"]):
        return "泡麵"
    return "零食"


def generate_dilemma_post(product1, price1, link1, product2, price2, link2, note=""):
    """產生一篇「糾結型」文案 — 兩個商品的內心戲"""

    opening = random.choice(DILEMMA_OPENINGS).format(product=product1)
    middle = random.choice(DILEMMA_MIDDLES)
    ending = random.choice(DILEMMA_ENDINGS)

    lines = [
        opening,
        f"{product1} ${price1:,}",
        link1,
        middle,
        f"但{product2}好像也不錯 ${price2:,}",
        link2,
        ending,
    ]

    if note:
        lines.append("")
        lines.append(f"喔對了 {note}")

    return "\n".join(lines)


def generate_post(product_name, price, affiliate_link, style="casual",
                   original_price=None, note=""):
    """產生一篇 Simon 風格的 Threads 文案"""

    category = get_category(product_name)
    scenarios = SCENARIOS.get(category, SCENARIOS["零食"])

    # 1. 生活場景開頭
    scenario = random.choice(scenarios).format(product=product_name)

    # 2. 商品 + 價格（一句話）
    price_str = f"${price:,}"
    if original_price and original_price > price:
        saved = original_price - price
        if style == "deal":
            price_line = f"{product_name} {price_str}（原價${original_price:,} 省${saved:,}）"
        else:
            price_line = f"{product_name} {price_str}"
    else:
        price_line = f"{product_name} {price_str}"

    # 3. 結尾（隨機選一個或不加）
    ending = random.choice(ENDINGS) if random.random() > 0.4 else ""

    # 4. 組裝
    lines = [scenario, price_line]
    if ending:
        lines.append(ending)
    lines.append(affiliate_link)

    # 5. 補充資訊（用「喔對了」開頭）
    if note:
        lines.append("")
        lines.append(f"喔對了 {note}")

    return "\n".join(lines)


def new_post(product_name, price, affiliate_link, style="casual",
             original_price=None, note="", product2=None, price2=None, link2=None):
    """新增一篇待發文案"""
    queue = load_queue()
    post_id = len(queue) + 1

    if style == "dilemma" and product2 and price2 and link2:
        content = generate_dilemma_post(
            product_name, price, affiliate_link,
            product2, price2, link2, note,
        )
    else:
        content = generate_post(
            product_name, price, affiliate_link, style,
            original_price, note,
        )

    entry = {
        "id": post_id,
        "product": product_name,
        "price": price,
        "original_price": original_price,
        "affiliate_link": affiliate_link,
        "style": style,
        "content": content,
        "note": note,
        "product2": product2,
        "price2": price2,
        "link2": link2,
        "status": "pending",  # pending / approved / posted
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "posted_at": None,
    }

    queue.append(entry)
    save_queue(queue)

    return entry


def list_queue(status="pending"):
    """列出指定狀態的文案"""
    queue = load_queue()
    filtered = [q for q in queue if q["status"] == status]
    if not filtered:
        return f"沒有 {status} 的文案"

    lines = [f"📝 {status} 文案列表："]
    for q in filtered:
        lines.append(f"  [{q['id']}] {q['product']} — ${q['price']:,} ({q['style']})")
    return "\n".join(lines)


def show_post(post_id):
    """顯示指定文案"""
    queue = load_queue()
    for q in queue:
        if q["id"] == post_id:
            return q["content"]
    return f"找不到 ID {post_id} 的文案"


def approve_post(post_id):
    """標記文案為已發"""
    queue = load_queue()
    for q in queue:
        if q["id"] == post_id:
            q["status"] = "posted"
            q["posted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_queue(queue)
            return f"✅ 已標記 [{q['id']}] {q['product']} 為已發"
    return f"找不到 ID {post_id} 的文案"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "new":
        if len(sys.argv) < 5:
            print("用法: python3 coupang_promo.py new '商品名' 價格 '分潤連結' [--style casual|deal] [--note '補充']")
            sys.exit(1)

        name = sys.argv[2]
        price = int(sys.argv[3].replace(",", "").replace("$", ""))
        link = sys.argv[4]

        style = "casual"
        note = ""
        orig_price = None
        i = 5
        while i < len(sys.argv):
            if sys.argv[i] == "--style" and i + 1 < len(sys.argv):
                style = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--note" and i + 1 < len(sys.argv):
                note = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--orig" and i + 1 < len(sys.argv):
                orig_price = int(sys.argv[i + 1].replace(",", "").replace("$", ""))
                i += 2
            else:
                i += 1

        entry = new_post(name, price, link, style, orig_price, note)
        print(f"✅ 已產生文案 #{entry['id']}")
        print(f"📦 {entry['product']} — ${entry['price']:,}")
        print(f"🎨 風格: {entry['style']}")
        print()
        print(entry["content"])

    elif cmd == "dilemma":
        if len(sys.argv) < 8:
            print("用法: python3 coupang_promo.py dilemma '商品1' 價格1 '連結1' '商品2' 價格2 '連結2' [--note '補充']")
            sys.exit(1)

        name1 = sys.argv[2]
        price1 = int(sys.argv[3].replace(",", "").replace("$", ""))
        link1 = sys.argv[4]
        name2 = sys.argv[5]
        price2 = int(sys.argv[6].replace(",", "").replace("$", ""))
        link2 = sys.argv[7]

        note = ""
        i = 8
        while i < len(sys.argv):
            if sys.argv[i] == "--note" and i + 1 < len(sys.argv):
                note = sys.argv[i + 1]
                i += 2
            else:
                i += 1

        entry = new_post(name1, price1, link1, "dilemma", None, note, name2, price2, link2)
        print(f"✅ 已產生文案 #{entry['id']}")
        print(f"📦 {entry['product']} vs {entry['product2']}")
        print(f"🎨 風格: dilemma")
        print()
        print(entry["content"])

    elif cmd == "list":
        status = sys.argv[2] if len(sys.argv) > 2 else "pending"
        print(list_queue(status))

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("用法: python3 coupang_promo.py show <id>")
            sys.exit(1)
        print(show_post(int(sys.argv[2])))

    elif cmd == "approve":
        if len(sys.argv) < 3:
            print("用法: python3 coupang_promo.py approve <id>")
            sys.exit(1)
        print(approve_post(int(sys.argv[2])))

    else:
        print(f"未知指令：{cmd}")
        print(__doc__)
