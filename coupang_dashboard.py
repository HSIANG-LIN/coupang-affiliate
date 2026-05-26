#!/usr/bin/env python3
"""
酷澎特價商品 Dashboard
- 每日金盒子特價 (自動抓取)
- 商品搜尋 + 分潤連結
- 價格追蹤
- 分潤報表
"""

import streamlit as st
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# === 路徑設定 ===
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(SCRIPT_DIR))
from coupang_api import (
    get_goldbox,
    search_products,
    generate_deeplink,
    get_commission_report,
)
from coupang_compare import search_momo, search_shopee, search_pchome
from coupang_tracker import load_products as load_tracked_products, load_price_history

AFFILIATE_ID = "AF1508181"

# === 文案產生 ===
SCENARIOS = {
    "日用品": [
        "一家三口 每次都忘了買{product}",
        "被派去買{product} 結果在酷澎看到更便宜的",
        "家裡{product}又見底了",
        "每次逛超市都在想{product}有沒有更便宜的",
    ],
    "零食": [
        "追劇的時候手邊沒東西吃",
        "小孩問我可不可以買{product}",
        "辦公室抽屜又空了",
    ],
    "保健": [
        "開始注意身體了",
        "偶然發現的 蠻便宜",
    ],
    "美妝": [
        "朋友推薦的 結果酷澎就有賣",
        "終於補貨了",
    ],
    "泡麵": [
        "半夜肚子餓",
        "不想煮飯的日子",
    ],
}

ENDINGS = [
    "",
    "隔天就到了 免運",
    "酷澎火箭速配 真的快",
    "送到家 不用自己扛",
]

import random

def generate_post(product_name, price, affiliate_url, style="casual"):
    """產生 Simon 風格的 Threads 文案"""
    # 判斷分類
    category = "日用品"
    for cat in ["零食", "保健", "美妝", "泡麵"]:
        if cat in product_name:
            category = cat
            break

    # 開頭場景
    scenarios = SCENARIOS.get(category, SCENARIOS["日用品"])
    opening = random.choice(scenarios).format(product=product_name)

    # 價格
    if style == "deal":
        price_line = f"目前特價 {price}"
    else:
        price_line = f"才{price}" if price < 500 else f"{price}"

    # 結尾
    ending = random.choice(ENDINGS)

    lines = [
        opening,
        f"酷澎上看了一下 {product_name} {price_line}",
        "",
    ]
    if ending:
        lines.append(ending)
    lines += [
        "連結在下面 價格不變",
        affiliate_url,
        f"#{product_name.replace(' ','')} #酷澎 #省錢",
    ]

    return "\n".join(lines)

# === 快取 ===
PRICE_HISTORY_FILE = SCRIPT_DIR / "price_history.json"


def load_price_history():
    if PRICE_HISTORY_FILE.exists():
        return json.loads(PRICE_HISTORY_FILE.read_text())
    return {}


def save_price_history(history):
    PRICE_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def format_price(p):
    return f"NT${p:,}"


# === 頁面設定 ===
st.set_page_config(
    page_title="酷澎特價情報",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔥 酷澎特價情報 Dashboard")
st.caption("Coupang Partners API — 自動抓取每日特價・搜尋商品・追蹤價格")

# === 側邊欄 ===
with st.sidebar:
    st.header("📋 功能選單")
    page = st.radio(
        "選擇頁面",
        ["🏠 每日金盒子", "🔍 商品搜尋", "📝 產生文案", "📊 價格追蹤", "⚖️ 跨平台比價", "📈 價格歷史", "💰 分潤報表"],
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("---")
    st.caption("⚠️ 寫文章時需聲明：")
    st.caption("「我可能會從合作夥伴的活動中收取佣金」")


# ========================================
# 🏠 每日金盒子
# ========================================
if page == "🏠 每日金盒子":
    st.header("🎯 每日金盒子特價")
    st.info("📅 每天 07:30 更新。點選商品可產生分潤追蹤連結。")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🔄 重新載入金盒子", width="stretch"):
            with st.spinner("正在抓取..."):
                st.session_state["goldbox"] = get_goldbox()
    with col2:
        if "goldbox" not in st.session_state:
            with st.spinner("首次載入中..."):
                st.session_state["goldbox"] = get_goldbox()

    data = st.session_state.get("goldbox", {})
    items = data.get("data", [])

    if not items:
        st.warning("目前沒有金盒子特價商品，或 API 尚未回傳資料。")
    else:
        st.success(f"共 {len(items)} 檔特價商品")

        # 分類篩選
        categories = list(set(p.get("categoryName", "其他") for p in items))
        selected_cat = st.selectbox("篩選類別", ["全部"] + sorted(categories))

        filtered = items if selected_cat == "全部" else [p for p in items if p.get("categoryName") == selected_cat]

        # 顯示商品
        for i in range(0, len(filtered), 3):
            cols = st.columns(3)
            for j, col in enumerate(cols):
                idx = i + j
                if idx >= len(filtered):
                    break
                p = filtered[idx]
                with col:
                    with st.container(border=True):
                        st.image(p.get("productImage", ""))
                        st.markdown(f"**{p.get('productName', 'Unknown')}**")
                        st.markdown(f"### {format_price(p.get('productPrice', 0))}")

                        tags = []
                        if p.get("isRocket"):
                            tags.append("🚀 火箭配送")
                        if p.get("isFreeShipping"):
                            tags.append("🚚 免運")
                        if tags:
                            st.caption(" ".join(tags))

                        st.caption(f"#{p.get('rank', '?')} | {p.get('categoryName', '')}")

                        # 產生分潤連結
                        product_url = p.get("productUrl", "")
                        if product_url:
                            st.link_button("🛒 前往購買", product_url, width="stretch")


# ========================================
# 🔍 商品搜尋
# ========================================
elif page == "🔍 商品搜尋":
    st.header("🔍 商品搜尋")
    st.info("關鍵字搜尋酷澎商品，自動產生分潤追蹤連結。")

    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入搜尋關鍵字", placeholder="例: 衛生紙, 洗衣膠囊, 零食")
    with col2:
        page_num = st.number_input("頁數", min_value=1, max_value=50, value=1)

    if keyword:
        with st.spinner(f"搜尋「{keyword}」中..."):
            results = search_products(keyword, page=page_num)

        data = results.get("data", {})
        items = data.get("productData", []) if isinstance(data, dict) else data
        if not items:
            st.warning("找不到相關商品，或 API 回傳空結果。")
        else:
            st.success(f"找到 {len(items)} 個商品")

            for i in range(0, len(items), 3):
                cols = st.columns(3)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx >= len(items):
                        break
                    p = items[idx]
                    with col:
                        with st.container(border=True):
                            img = p.get("productImage", "")
                            if img:
                                st.image(img)
                            st.markdown(f"**{p.get('productName', 'Unknown')[:60]}**")
                            st.markdown(f"### {format_price(p.get('productPrice', 0))}")

                            tags = []
                            if p.get("isRocket"):
                                tags.append("🚀 火箭")
                            if p.get("isFreeShipping"):
                                tags.append("🚚 免運")
                            if tags:
                                st.caption(" ".join(tags))

                            # 連結
                            url = p.get("productUrl", "")
                            if url:
                                st.link_button("🛒 購買", url, width="stretch")


# ========================================
# 📝 產生文案
# ========================================
elif page == "📝 產生文案":
    st.header("📝 產生 Threads 文案")
    st.info("貼上酷澎商品資訊，自動產生 Simon 風格的推薦文案。")

    # 手動輸入
    st.subheader("✏️ 手動輸入商品資訊")
    c1, c2 = st.columns(2)
    with c1:
        manual_name = st.text_input("商品名稱", placeholder="例: 倍潔雅衛生紙 150抽")
        manual_price = st.number_input("價格", min_value=0, value=0)
    with c2:
        manual_url = st.text_area("分潤連結", placeholder="貼上酷澎商品網址或分潤連結", height=68)
        style = st.selectbox("文案風格", ["casual", "deal"], format_func=lambda x: "📝 日常分享" if x == "casual" else "🔥 特價推薦")

    if manual_name and manual_price and manual_url:
        if st.button("✨ 產生文案", use_container_width=True):
            post = generate_post(manual_name, manual_price, manual_url, style)
            st.session_state["generated_post"] = post

    # 從金盒子/搜尋帶入
    st.subheader("📦 從商品資料帶入")
    st.caption("在「每日金盒子」或「商品搜尋」頁面，找到想推廣的商品後複製連結貼到上方即可")

    # 顯示 & 編輯文案
    if "generated_post" in st.session_state:
        st.divider()
        st.subheader("📋 文案預覽")

        edited = st.text_area("編輯文案", st.session_state["generated_post"], height=200, key="post_edit")

        c1, c2 = st.columns(2)
        with c1:
            st.code(edited, language=None)
        with c2:
            if st.button("📋 複製到剪貼簿", use_container_width=True):
                st.session_state["copied_post"] = edited
                st.toast("已複製到剪貼簿！", icon="✅")
            st.link_button(
                "🚀 開啟 Threads",
                "https://www.threads.net/",
                use_container_width=True,
            )

        st.caption("複製文案後，貼到 Threads 貼文區即可。")

# ========================================
# 📊 價格追蹤
# ========================================
elif page == "📊 價格追蹤":
    st.header("📊 價格追蹤")
    st.info("追蹤特定商品的價格變化。搜尋商品後加入追蹤清單。")

    history = load_price_history()

    # 新增追蹤
    st.subheader("➕ 新增追蹤商品")
    track_keyword = st.text_input("搜尋要追蹤的商品", placeholder="關鍵字", key="track_kw")

    if track_keyword:
        with st.spinner("搜尋中..."):
            results = search_products(track_keyword)

        data = results.get("data", {})
        items = data.get("productData", []) if isinstance(data, dict) else data
        if items:
            options = {p["productName"][:50]: p for p in items[:10]}
            selected = st.selectbox("選擇商品", list(options.keys()))

            if selected and st.button("📌 加入追蹤"):
                p = options[selected]
                pid = str(p["productId"])
                if pid not in history:
                    history[pid] = {
                        "name": p["productName"],
                        "image": p.get("productImage", ""),
                        "prices": [],
                    }
                today = datetime.now().strftime("%Y-%m-%d")
                history[pid]["prices"].append({"date": today, "price": p["productPrice"]})
                save_price_history(history)
                st.success(f"已加入追蹤：{p['productName'][:30]}")

    # 追蹤清單
    st.subheader("📋 追蹤清單")
    if not history:
        st.info("尚未追蹤任何商品。")
    else:
        for pid, info in history.items():
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 3, 1])
                with c1:
                    if info.get("image"):
                        st.image(info["image"], width=80)
                with c2:
                    st.markdown(f"**{info['name'][:50]}**")
                    prices = info.get("prices", [])
                    if prices:
                        latest = prices[-1]["price"]
                        st.markdown(f"目前價格：**{format_price(latest)}**")

                        if len(prices) > 1:
                            first = prices[0]["price"]
                            diff = latest - first
                            pct = (diff / first) * 100 if first else 0
                            if diff < 0:
                                st.success(f"📉 降價 {format_price(abs(diff))} ({pct:.1f}%)")
                            elif diff > 0:
                                st.error(f"📈 漲價 {format_price(diff)} ({pct:.1f}%)")
                            else:
                                st.info("➡️ 價格不變")

                        # 簡易價格圖表
                        if len(prices) > 1:
                            import pandas as pd
                            df = pd.DataFrame(prices)
                            df["date"] = pd.to_datetime(df["date"])
                            st.line_chart(df.set_index("date")["price"], height=150)
                with c3:
                    if st.button("🗑️", key=f"del_{pid}"):
                        del history[pid]
                        save_price_history(history)
                        st.rerun()


# ========================================
# ⚖️ 跨平台比價
# ========================================
elif page == "⚖️ 跨平台比價":
    st.header("⚖️ 跨平台比價")
    st.info("搜尋同一商品在 momo / 蝦皮 / PChome / 酷澎 的價格，找出真正最低價。")

    compare_keyword = st.text_input("輸入商品關鍵字", placeholder="例: 衛生紙, 洗衣膠囊")

    if compare_keyword:
        if st.button("🔍 開始比價", width="stretch"):
            with st.spinner("搜尋各平台中...（含 Playwright 瀏覽器，約 15-30 秒）"):
                results = {}

                # 酷澎
                with st.status("搜尋酷澎...", expanded=False) as status:
                    try:
                        coupang_results = search_products(compare_keyword, size=3)
                        items = coupang_results.get("data", {}).get("productData", [])
                        if items:
                            results["coupang"] = items
                        status.update(label="✅ 酷澎完成", state="complete")
                    except Exception as e:
                        status.update(label=f"❌ 酷澎失敗: {e}", state="error")

                # momo
                with st.status("搜尋 momo...", expanded=False) as status:
                    try:
                        momo_results = search_momo(compare_keyword, size=3)
                        if momo_results:
                            results["momo"] = momo_results
                        status.update(label="✅ momo完成", state="complete")
                    except Exception as e:
                        status.update(label=f"❌ momo失敗: {e}", state="error")

                # 蝦皮
                with st.status("搜尋蝦皮...（Playwright）", expanded=False) as status:
                    try:
                        shopee_results = search_shopee(compare_keyword, size=3)
                        if shopee_results:
                            results["shopee"] = shopee_results
                        status.update(label="✅ 蝦皮完成", state="complete")
                    except Exception as e:
                        status.update(label=f"❌ 蝦皮失敗: {e}", state="error")

                # PChome
                with st.status("搜尋PChome...（Playwright）", expanded=False) as status:
                    try:
                        pchome_results = search_pchome(compare_keyword, size=3)
                        if pchome_results:
                            results["pchome"] = pchome_results
                        status.update(label="✅ PChome完成", state="complete")
                    except Exception as e:
                        status.update(label=f"❌ PChome失敗: {e}", state="error")

                st.session_state["compare_results"] = results

        # 顯示比價結果
        results = st.session_state.get("compare_results", {})
        if results:
            st.divider()

            # 找各平台最低價
            platform_cheapest = {}
            for plat, items in results.items():
                if items:
                    cheapest = min(items, key=lambda x: x.get("price", 999999))
                    platform_cheapest[plat] = cheapest

            overall = None
            if platform_cheapest:
                overall = min(platform_cheapest.values(), key=lambda x: x.get("price", 999999))

            # 顯示各平台結果
            st.subheader("📊 各平台最低價")

            col1, col2, col3, col4 = st.columns(4)

            platform_names = {"coupang": "🔥 酷澎", "momo": "🛒 momo", "shopee": "🦐 蝦皮", "pchome": "🏪 PChome"}
            platform_colors = {"coupang": "🔴", "momo": "🟠", "shopee": "🟢", "pchome": "🔵"}

            for i, (plat, item) in enumerate(sorted(platform_cheapest.items(), key=lambda x: x[1].get("price", 999999))):
                col = [col1, col2, col3, col4][i % 4]
                with col:
                    is_cheapest = overall and item.get("price") == overall.get("price")
                    with st.container(border=True, key=f"compare_{plat}"):
                        st.markdown(f"**{platform_names.get(plat, plat)}**")
                        price = item.get("price", 0)
                        first_price = item.get("first_price")
                        price_str = f"NT${price:,}"
                        if first_price and first_price < price:
                            price_str += f" (首購 NT${first_price:,})"
                        st.markdown(f"### {'🏆 ' if is_cheapest else ''}{price_str}")
                        st.caption(item.get("name", "")[:40])
                        if is_cheapest:
                            st.success("👑 最低價!")
                        if item.get("url"):
                            st.link_button("前往", item["url"], width="stretch")

            # 價格比較圖表
            if len(platform_cheapest) >= 2:
                st.subheader("📊 價格比較")
                import pandas as pd
                chart_data = pd.DataFrame([
                    {"平台": platform_names.get(plat, plat), "價格": item.get("price", 0)}
                    for plat, item in platform_cheapest.items()
                ])
                st.bar_chart(chart_data.set_index("平台")["價格"])

                # 價格差異
                prices = [item.get("price", 0) for item in platform_cheapest.values()]
                if len(prices) >= 2:
                    diff = max(prices) - min(prices)
                    diff_pct = round(diff / max(prices) * 100, 1) if max(prices) > 0 else 0
                    st.info(f"💰 最高與最低差 **NT${diff:,}** ({diff_pct}%)")

            # 各平台完整結果
            st.subheader("📋 各平台詳細結果")
            for plat, items in results.items():
                with st.expander(f"{platform_names.get(plat, plat)} ({len(items)} 個商品)"):
                    for item in items[:5]:
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"**{item.get('name', '')[:60]}**")
                            st.caption(f"NT${item.get('price', 0):,}")
                        with c2:
                            if item.get("url"):
                                st.link_button("前往", item["url"], width="stretch")


# ========================================
# 📈 價格歷史
# ========================================
elif page == "📈 價格歷史":
    st.header("📈 價格歷史圖表")
    st.info("顯示追蹤商品的歷史價格變化。資料來自每日自動掃描。")

    history = load_price_history()
    products = load_tracked_products()

    if not history:
        st.info("尚無價格歷史資料。請先在「價格追蹤」頁面新增商品，或等待每日自動掃描。")
    else:
        # 選擇商品
        product_names = [name for name in history.keys() if not name.startswith("goldbox_")]
        if not product_names:
            product_names = list(history.keys())

        selected = st.selectbox("選擇商品", product_names)

        if selected:
            records = history.get(selected, [])
            if not records:
                st.info("該商品尚無價格記錄")
            else:
                import pandas as pd

                df = pd.DataFrame(records)
                df["time"] = pd.to_datetime(df["time"])

                # 基本統計
                prices = df["price"].tolist()
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("目前", f"NT${prices[-1]:,}")
                with col2:
                    st.metric("最低", f"NT${min(prices):,}")
                with col3:
                    st.metric("最高", f"NT${max(prices):,}")
                with col4:
                    avg = round(sum(prices) / len(prices))
                    st.metric("均價", f"NT${avg:,}")

                # 價格走勢圖
                st.subheader("📊 價格走勢")
                chart_df = df.set_index("time")[["price"]]

                # 加入均價線
                import pandas as pd
                chart_df["均價"] = avg

                st.line_chart(chart_df, height=300)

                # 資料表
                st.subheader("📋 記錄明細")
                display_df = df[["time", "price", "source"]].copy()
                display_df["time"] = display_df["time"].dt.strftime("%Y-%m-%d %H:%M")
                display_df.columns = ["時間", "價格", "來源"]
                st.dataframe(display_df, width="stretch")

                # 低點警示歷史
                if len(prices) >= 2:
                    lows = []
                    for i in range(1, len(prices)):
                        if prices[i] < min(prices[:i]):
                            lows.append({
                                "時間": df.iloc[i]["time"].strftime("%Y-%m-%d %H:%M"),
                                "價格": prices[i],
                                "比前低便宜": f"NT${min(prices[:i]) - prices[i]:,}",
                            })
                    if lows:
                        st.subheader("🔥 歷史低點記錄")
                        st.dataframe(pd.DataFrame(lows), width="stretch")


# ========================================
# 💰 分潤報表
# ========================================
elif page == "💰 分潤報表":
    st.header("💰 分潤報表")
    st.info("查詢過去 7 天的分潤與訂單數據。")

    today = datetime.now()
    default_start = today - timedelta(days=7)

    c1, c2 = st.columns(2)
    with c1:
        start = st.date_input("起始日期", value=default_start)
    with c2:
        end = st.date_input("結束日期", value=today)

    if st.button("📊 查詢分潤", width="stretch"):
        s = start.strftime("%Y%m%d")
        e = end.strftime("%Y%m%d")

        with st.spinner("查詢中..."):
            result = get_commission_report(s, e)

        if result.get("rCode") == "0":
            data = result.get("data", [])
            if not data:
                st.info("該期間無分潤資料。")
            else:
                st.success(f"共 {len(data)} 筆記錄")

                import pandas as pd
                df = pd.DataFrame(data)
                st.dataframe(df, width="stretch")

                if "commissionAmount" in df.columns:
                    total = df["commissionAmount"].sum()
                    st.metric("總分潤", format_price(total))
        else:
            st.error(f"API 錯誤: {result.get('rMessage', 'Unknown')}")
