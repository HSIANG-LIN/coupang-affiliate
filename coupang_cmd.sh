#!/usr/bin/env python3
"""
酷澎價格追蹤 — Hermes slash 指令
用法：
  /coupang list            → 列出追蹤商品
  /coupang summary 商品名   → 價格摘要
  /coupang post 商品名     → 產生 Threads 文案
  /coupang report 商品名 價格 [備註] → 回報價格
  /coupang add 商品名 [網址] → 新增商品
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))  # 本地目錄
from coupang_bot import handle_message

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: coupang_cmd <指令> [參數...]")
        sys.exit(1)
    
    cmd = " ".join(sys.argv[1:])
    result = handle_message(cmd)
    print(result)