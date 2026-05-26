#!/usr/bin/env python3
"""
Coupang Dreaming — 每週自我進化引擎
自動分析價格歷史 → 產出下週推薦策略
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent  # 本地目錄
PRICE_DB = DATA_DIR / "price_history.json"
STRATEGY_FILE = DATA_DIR / "weekly_strategy.json"

def load_price_history():
    if PRICE_DB.exists():
        with open(PRICE_DB) as f:
            return json.load(f)
    return {}

def analyze_volatility(prices):
    """分析價格波動率 — 標準差/均價"""
    if len(prices) < 2:
        return 0
    avg = sum(prices) / len(prices)
    variance = sum((p - avg) ** 2 for p in prices) / len(prices)
    return (variance ** 0.5) / avg * 100  # 波動率百分比

def calculate_drop_potential(prices, current_price):
    """計算目前價格與歷史均價的差距"""
    if len(prices) < 2:
        return 0
    avg = sum(prices) / len(prices)
    if avg == 0:
        return 0
    return round((avg - current_price) / avg * 100, 1)

def dream():
    """執行 dreaming 分析，產出下週策略"""
    history = load_price_history()
    now = datetime.now()
    
    insights = []
    rankings = []
    
    for product_name, records in history.items():
        if len(records) < 2:
            insights.append({
                "product": product_name,
                "status": "資料不足",
                "records": len(records)
            })
            continue
        
        prices = [r["price"] for r in records]
        current_price = prices[-1]
        lowest = min(prices)
        highest = max(prices)
        avg = round(sum(prices) / len(prices))
        volatility = analyze_volatility(prices)
        drop_pct = calculate_drop_potential(prices, current_price)
        
        # 計算最近 7 天的價格趨勢
        recent_prices = [r["price"] for r in records if 
                        "time" in r and 
                        (now - datetime.strptime(r["time"], "%Y-%m-%d %H:%M")).days <= 7]
        
        recent_trend = "持平"
        if recent_prices:
            if recent_prices[-1] < recent_prices[0] * 0.95:
                recent_trend = "📉 下跌中"
            elif recent_prices[-1] > recent_prices[0] * 1.05:
                recent_trend = "📈 上漲中"
        
        analysis = {
            "product": product_name,
            "records": len(records),
            "current_price": current_price,
            "lowest": lowest,
            "highest": highest,
            "avg": avg,
            "volatility": round(volatility, 1),
            "drop_pct": drop_pct,
            "recent_trend": recent_trend,
            "recommendation": ""
        }
        
        # 推薦邏輯
        if drop_pct >= 10:
            analysis["recommendation"] = "🔥🔥🔥 強烈推薦 — 比均價便宜 10% 以上，立刻發文！"
            analysis["priority"] = 1
        elif drop_pct >= 5:
            analysis["recommendation"] = "✅ 推薦 — 價格不錯，可以考慮發文"
            analysis["priority"] = 2
        elif volatility > 10:
            analysis["recommendation"] = "👀 波動大 — 價格變化劇烈，建議每天盯"
            analysis["priority"] = 3
        else:
            analysis["recommendation"] = "⏸️ 觀望 — 價格穩定，等低點再出手"
            analysis["priority"] = 4
        
        insights.append(analysis)
        rankings.append(analysis)
    
    # 排序：priority 越高越前面
    rankings.sort(key=lambda x: x.get("priority", 99))
    
    # 產出策略
    strategy = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "total_products": len(history),
            "hot_products": sum(1 for r in rankings if r.get("priority") == 1),
            "watch_products": sum(1 for r in rankings if r.get("priority") == 3),
        },
        "top_picks": [r for r in rankings if r.get("priority") == 1],
        "recommended": [r for r in rankings if r.get("priority") == 2],
        "watchlist": [r for r in rankings if r.get("priority") == 3],
        "hold": [r for r in rankings if r.get("priority") == 4],
        "all_insights": rankings
    }
    
    # 儲存策略
    with open(STRATEGY_FILE, "w") as f:
        json.dump(strategy, f, ensure_ascii=False, indent=2)
    
    return strategy

def format_report(strategy):
    """產出人類可讀的報告"""
    lines = [
        f"🧠 Coupang Dreaming — {strategy['summary']['total_products']} 商品分析完成",
        f"📅 {strategy['generated_at']}",
        "",
    ]
    
    if strategy["top_picks"]:
        lines.append("🔥 本週強烈推薦（立刻發文！）")
        lines.append("─" * 30)
        for p in strategy["top_picks"]:
            lines.append(f"  {p['product']}：目前 ${p['current_price']}")
            lines.append(f"    比均價便宜 {p['drop_pct']}% | 波動率 {p['volatility']}%")
            lines.append(f"    趨勢：{p['recent_trend']}")
            lines.append("")
    
    if strategy["recommended"]:
        lines.append("✅ 可考慮發文")
        lines.append("─" * 30)
        for p in strategy["recommended"]:
            lines.append(f"  {p['product']}：${p['current_price']}（便宜 {p['drop_pct']}%）")
        lines.append("")
    
    if strategy["watchlist"]:
        lines.append("👀 波動大，建議每天盯")
        lines.append("─" * 30)
        for p in strategy["watchlist"]:
            lines.append(f"  {p['product']}：波動率 {p['volatility']}%")
        lines.append("")
    
    if strategy["hold"]:
        lines.append("⏸️ 先觀望")
        lines.append("─" * 30)
        for p in strategy["hold"]:
            lines.append(f"  {p['product']}：價格穩定，等低點")
        lines.append("")
    
    lines.append("📌 策略已儲存至 weekly_strategy.json")
    return "\n".join(lines)

# === CLI ===
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--report":
        strategy = dream()
        print(format_report(strategy))
    else:
        strategy = dream()
        print(f"✅ Dreaming 完成！分析 {strategy['summary']['total_products']} 商品")
        print(f"🔥 熱點商品：{strategy['summary']['hot_products']}")
        print(f"👀 需關注：{strategy['summary']['watch_products']}")
        print(f"📁 策略已儲存：{STRATEGY_FILE}")