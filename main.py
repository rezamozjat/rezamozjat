import os
import feedparser
from google import genai
from google.genai import types
import requests
import time

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

client = genai.Client(api_key=GEMINI_API_KEY)

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
            
            # بررسی ۲ خبر اخیر هر سایت
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
                response_text = None
                
                for attempt in range(2):
                    try:
                        response = client.models.generate_content(
                            model='gemini-3.6-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
                        )
                        response_text = response.text
                        break
                    except Exception as api_err:
                        err_msg = str(api_err)
                        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "503" in err_msg:
                            print(f"⚠️ محدودیت یا ترافیک سرور ({err_msg[:30]})... ۱۰ ثانیه مکث")
                            time.sleep(10)
                        else:
                            print(f"خطا: {err_msg}")
                            break

                if not response_text:
                    print("❌ عدم دریافت پاسخ از مدل، عبور به خبر بعدی.")
                    continue

                final_message = f"{response_text}\n\n🔗 [مطالعه اصل خبر]({link})\n\n🆔 {TELEGRAM_CHAT_ID}"
                
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
                    time.sleep(5)
                
        except Exception as e:
            print(f"Error processing {source_name}: {e}")

if __name__ == "__main__":
    run_bot()
