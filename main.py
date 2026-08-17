import os
import feedparser
from google import genai
from google.genai import types
import requests
import time

# خواندن متغیرهای امنیتی
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

client = genai.Client(api_key=GEMINI_API_KEY)

# منابع خبری
RSS_SOURCES = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CoinTelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "CryptoPotato": "https://cryptopotato.com/feed/"
}

DB_FILE = "posted_links.txt"

def load_posted_links():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted_link(link):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")

def run_bot():
    posted_links = load_posted_links()

    for source_name, rss_url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(rss_url)
            
            # بررسی ۲ خبر جدید از هر سایت برای کاهش تعداد درخواست‌ها
            for entry in reversed(feed.entries[:2]):
                link = entry.link
                
                if link in posted_links:
                    continue
                
                title = entry.title
                summary = entry.summary if 'summary' in entry else title
                
                print(f"جدیدترین خبر از {source_name}: {title}")
                
                prompt = f"""
تو یک تحلیل‌گر و مترجم ارشد بازار کریپتو هستی. 
خبر زیر از منبع {source_name} منتشر شده است:
تیتر: {title}
خلاصه: {summary}

لطفاً خروجی را دقیقاً به این فرمت فارسی بنویس:
📌 **تیتر:** (ترجمه جذاب)
🌐 **منبع اصلی:** {source_name}
📝 **خلاصه خبر:** (ترجمه در ۳ جمله)
💡 **تحلیل کوتاه:** (تحلیل در ۲ جمله)
"""
                # ارسال به جمینای به همراه غیرفعال‌سازی هشدار AFC
                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
                )
                
                final_message = f"{response.text}\n\n🔗 [مطالعه اصل خبر]({link})\n\n🆔 {TELEGRAM_CHAT_ID}"
                
                telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": final_message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
                
                res = requests.post(telegram_url, data=payload)
                
                if res.status_code == 200:
                    print(f"✅ خبر از {source_name} ارسال شد.")
                    save_posted_link(link)
                    posted_links.add(link)
                    # مکث ۱۰ ثانیه‌ای برای عبور از محدودیت API گوگل
                    time.sleep(10)
                
        except Exception as e:
            print(f"Error processing {source_name}: {e}")

if __name__ == "__main__":
    run_bot()
