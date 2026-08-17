import os
import feedparser
from google import genai
import requests

# خواندن متغیرها از بخش امن گیت‌هاب
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

def run_bot():
    for source_name, rss_url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                continue
                
            entry = feed.entries[0]  # جدیدترین خبر
            title = entry.title
            summary = entry.summary if 'summary' in entry else title
            link = entry.link
            
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
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            
            final_message = f"{response.text}\n\n🔗 [مطالعه اصل خبر]({link})\n\n🆔 {TELEGRAM_CHAT_ID}"
            
            telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": final_message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }
            requests.post(telegram_url, data=payload)
            break # ارسال یک خبر در هر بار اجرا کافیست
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    run_bot()
