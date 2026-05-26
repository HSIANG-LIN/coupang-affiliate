#!/usr/bin/env python3
"""
酷澎分潤 — Simon 聲音推薦影片產生器
Dreaming 分析 → 推薦文案 → Simon 聲音 TTS → LivePortrait 嘴型同步 → MP4
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# === 路徑設定 ===
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = Path.home() / ".hermes"
VOICE_CLONE_DIR = Path.home() / "workspace" / "ai" / "voice-clone"
COUPANG_DIR = SCRIPT_DIR  # 本地目錄
TTS_SCRIPT = VOICE_CLONE_DIR / "cosyvoice_tts.py"
LIVEPORTRAIT_DIR = VOICE_CLONE_DIR / "LivePortrait"
REFERENCE_VOICE = BASE_DIR / "SimonVoice" / "SimonVoice.wav"
REFERENCE_IMAGE = BASE_DIR / "SimonVoice" / "圖片_20260520132832_73_5.jpg"
OUTPUT_DIR = COUPANG_DIR / "videos"
STRATEGY_FILE = COUPANG_DIR / "weekly_strategy.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_strategy():
    """讀取 Dreaming 產出的策略"""
    if STRATEGY_FILE.exists():
        with open(STRATEGY_FILE) as f:
            return json.load(f)
    return None


def generate_recommendation_text(strategy):
    """根據策略產出推薦文案（口語風格，適合 TTS）"""
    if not strategy:
        return None
    
    picks = []
    
    # 🔥 強烈推薦
    for p in strategy.get("top_picks", []):
        name = p.get("product", "")
        price = p.get("current_price", "")
        drop = p.get("drop_pct", 0)
        trend = p.get("recent_trend", "")
        
        text = (
            f"嘿！告訴你一個好康的！"
            f"酷澎的{name}現在只要{price}元，"
            f"比均價便宜了{drop}%！"
            f"這價格真的很划算，火箭速配隔天就到，不用自己扛回家。"
            f"連結在下面，趕快去搶！"
        )
        picks.append({
            "product": name,
            "priority": "hot",
            "text": text,
            "price": price,
            "drop_pct": drop,
        })
    
    # ✅ 可考慮
    for p in strategy.get("recommended", []):
        name = p.get("product", "")
        price = p.get("current_price", "")
        drop = p.get("drop_pct", 0)
        
        text = (
            f"另外，{name}現在{price}元，"
            f"比平常便宜{drop}%，"
            f"如果有需要的話，這個價格值得入手。"
        )
        picks.append({
            "product": name,
            "priority": "good",
            "text": text,
            "price": price,
            "drop_pct": drop,
        })
    
    # 合併成完整文案
    if not picks:
        return None
    
    full_text = ""
    for pick in picks:
        full_text += pick["text"] + " "
    
    # 加上結尾
    full_text += "我是 Simon，這些都是我親自比價的結果。連結在資訊欄，記得去看喔！"
    
    return {
        "full_text": full_text,
        "items": picks,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def generate_tts(text, output_wav):
    """用 CosyVoice2 + Simon 聲音生成語音"""
    print(f"🎙️ 生成 Simon 語音...")
    
    cmd = [
        sys.executable, str(TTS_SCRIPT),
        "--text", text,
        "--reference", str(REFERENCE_VOICE),
        "--output", str(output_wav),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    if result.returncode != 0:
        print(f"❌ TTS 失敗: {result.stderr[-500:]}")
        return False
    
    print(f"✅ 語音生成完成: {output_wav}")
    return True


def generate_lip_sync(audio_wav, image_path, output_mp4):
    """用 LivePortrait 生成嘴型同步影片"""
    print(f"🎬 生成 LivePortrait 嘴型同步...")
    
    inference_script = LIVEPORTRAIT_DIR / "inference.py"
    
    cmd = [
        sys.executable, str(inference_script),
        "--driven_audio", str(audio_wav),
        "--source_image", str(image_path),
        "--output_dir", str(output_mp4.parent),
        "--flag_relative",  # 使用相對運動
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        print(f"❌ LivePortrait 失敗: {result.stderr[-500:]}")
        return False
    
    # LivePortrait 預設輸出檔名可能不同，需要找到實際輸出
    # 找最新的 mp4 在 output_dir
    mp4_files = sorted(output_mp4.parent.glob("*.mp4"), key=os.path.getmtime, reverse=True)
    if mp4_files:
        actual_output = mp4_files[0]
        if actual_output != output_mp4:
            actual_output.rename(output_mp4)
    
    print(f"✅ 嘴型同步完成: {output_mp4}")
    return True


def generate_text_video(text, audio_wav, output_mp4, style="dark"):
    """用 FFmpeg 產生字幕影片（備用方案，不需要 LivePortrait）"""
    print(f"🎬 產生字幕影片（FFmpeg）...")
    
    # 先取得語音長度
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(audio_wav)
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    duration = float(result.stdout.strip()) if result.stdout.strip() else 30
    
    # FFmpeg 指令：背景 + 字幕 + 音訊
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"color=c=black:s=1080x1920:d={duration}:r=30",
        "-i", str(audio_wav),
        "-vf",
        f"drawtext=text='Simon 推薦':fontcolor=white:fontsize=60:x=(w-text_w)/2:y=h/4,"
        f"drawtext=text='{text[:40]}':fontcolor=yellow:fontsize=40:x=(w-text_w)/2:y=h/2,"
        f"drawtext=text='酷澎分潤推薦':fontcolor=#00ff00:fontsize=36:x=(w-text_w)/2:y=h*3/4",
        "-c:v", "libx264", "-c:a", "aac",
        "-shortest",
        str(output_mp4)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    if result.returncode != 0:
        print(f"❌ FFmpeg 失敗: {result.stderr[-300:]}")
        return False
    
    print(f"✅ 字幕影片完成: {output_mp4}")
    return True


def full_pipeline():
    """完整 pipeline：策略 → 文案 → TTS → 影片"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # 1. 讀取策略
    print("📖 讀取 Dreaming 策略...")
    strategy = load_strategy()
    if not strategy:
        print("❌ 沒有策略檔案，請先執行 coupang_dreaming.py")
        return
    
    # 2. 產出推薦文案
    print("✍️ 產出推薦文案...")
    rec = generate_recommendation_text(strategy)
    if not rec:
        print("❌ 沒有可推薦的商品")
        return
    
    print(f"   文案長度: {len(rec['full_text'])} 字")
    print(f"   推薦商品: {[i['product'] for i in rec['items']]}")
    
    # 3. TTS
    wav_path = OUTPUT_DIR / f"rec_{timestamp}.wav"
    if not generate_tts(rec["full_text"], wav_path):
        return
    
    # 4. 產影片
    mp4_path = OUTPUT_DIR / f"rec_{timestamp}.mp4"
    
    if REFERENCE_IMAGE.exists():
        # 用 LivePortrait
        success = generate_lip_sync(wav_path, REFERENCE_IMAGE, mp4_path)
        if not success:
            # 備用：FFmpeg 字幕影片
            success = generate_text_video(rec["full_text"], wav_path, mp4_path)
    else:
        # 沒有圖片，用 FFmpeg 字幕影片
        success = generate_text_video(rec["full_text"], wav_path, mp4_path)
    
    if success:
        print(f"\n🎉 完成！影片在: {mp4_path}")
        print(f"   語音在: {wav_path}")
        
        # 儲存文案
        rec_file = OUTPUT_DIR / f"rec_{timestamp}_text.json"
        with open(rec_file, "w") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        print(f"   文案在: {rec_file}")
    
    return mp4_path


# === CLI ===
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--text-only":
        # 只產文案不產影片
        strategy = load_strategy()
        rec = generate_recommendation_text(strategy)
        if rec:
            print("📝 推薦文案：")
            print(rec["full_text"])
            print(f"\n📊 推薦商品: {[i['product'] for i in rec['items']]}")
        else:
            print("❌ 沒有可推薦的商品")
    else:
        full_pipeline()