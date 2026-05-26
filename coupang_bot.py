#!/usr/bin/env python3
"""
酷澎價格追蹤 Telegram Bot
讓你可以直接用手機回報價格、查摘要、產生文案
"""

import json
import os
import re
import sys
from pathlib import Path

# 載入追蹤器核心
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
from coupang_tracker import (
    report_price, list_products, get_price_summary, 
    generate_threads_post, load_price_history,
    load_products, PRICE_DB, PRODUCT_LIST
)

def handle_message(text: str, chat_id: str = "origin") -> str:
    """
    處理 Telegram 訊息，回傳要發送的文字
    
    /start - 顯示幫助
    /list - 列出追蹤商品
    /summary [商品名] - 價格摘要
    /post [商品名] - 產生 Threads 文案
    report [商品名] [價格] - 回報價格
    add [商品名] [網址] - 新增商品
    """
    text = text.strip()
    
    # 幫助
    if text in ["/start", "help", "幫助", "指令"]:
        return """🤖 酷澎價格追蹤 Bot

指令：
  report [商品名] [價格]  → 回報價格
  範例：report 倍潔雅衛生紙 999

  /list  → 列出追蹤商品
  /summary [商品名]  → 價格摘要
  /post [商品名]  → 產生 Threads 文案

  add [商品名] [網址]  → 新增商品

分潤連結：https://coupa.ng/???  ← 要換成你的
         """
    
    # /list
    if text == "/list" or text == "list":
        return list_products()
    
    # /summary
    if text.startswith("/summary ") or text.startswith("summary "):
        name = text.split(" ", 1)[1].strip()
        s = get_price_summary(name)
        if isinstance(s, str):
            return f"❌ {s}"
        records = load_price_history().get(name, [])
        msg = f"📊 {name} 價格摘要\n"
        msg += f"  最新：${s['latest']}\n"
        msg += f"  最低：${s['lowest']}\n"
        msg += f"  最高：${s['highest']}\n"
        msg += f"  均價：${s['avg']}\n"
        msg += f"  記錄數：{s['records']} 筆 / {s['days']} 天"
        return msg
    
    # /post
    if text.startswith("/post ") or text.startswith("post "):
        name = text.split(" ", 1)[1].strip()
        s = get_price_summary(name)
        if isinstance(s, str):
            return f"❌ {s}"
        
        records = load_price_history().get(name, [])
        deal_info = None
        if records:
            prices = [r["price"] for r in records]
            avg = round(sum(prices) / len(prices))
            if s["latest"] <= s["lowest"]:
                drop_pct = round((avg - s["latest"]) / avg * 100, 1)
                deal_info = {
                    "current": s["latest"],
                    "lowest": s["lowest"],
                    "avg": avg,
                    "drop_pct": drop_pct
                }
        
        return generate_threads_post(name, s["latest"], deal_info)
    
    # add [商品名] [網址]
    if text.startswith("add ") or text.startswith("/add "):
        parts = text.split(" ", 2)
        if len(parts) < 2:
            return "用法: add 商品名 [網址]"
        name = parts[1]
        url = parts[2] if len(parts) > 2 else None
        
        from coupang_tracker import add_product
        return add_product(name, url)
    
    # report [商品名] [價格] [備註]
    report_match = re.match(r"^report\s+(.+?)\s+(\d[\d,]*)\s*(.*)$", text, re.IGNORECASE)
    if report_match:
        name = report_match.group(1).strip()
        price = int(report_match.group(2).replace(",", ""))
        note = report_match.group(3).strip()
        return report_price(name, price, note)
    
    # 預設：當作 report 處理（如果只傳數字和名稱）
    default_match = re.match(r"^(.+?)\s+(\d[\d,]*)", text)
    if default_match:
        name = default_match.group(1).strip()
        price = int(default_match.group(2).replace(",", ""))
        return report_price(name, price, "")
    
    return f"❌ 看不懂。輸入「幫助」或「/start」看指令"

# === 如果直接執行，測試用 ===
if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(handle_message(" ".join(sys.argv[1:])))
    else:
        # 測試模式
        print("=== 測試 Bot 處理 ===")
        print("\n--- 測試 /list ---")
        print(handle_message("/list"))
        print("\n--- 測試 report ---")
        print(handle_message("report 倍潔雅衛生紙 888"))
        print("\n--- 測試 /post ---")
        print(handle_message("/post 倍潔雅衛生紙"))