import os
import feedparser
import requests
import time
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

client = Groq(api_key=GROQ_API_KEY)

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

def get_active_groq_model():
    """شناسایی خودکار و اولویت‌بندی مدل‌های فعال جدید Groq"""
    preferred_order = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "qwen/qwen3.6-27b"
    ]
    
    try:
        models_page = client.models.list()
        active_models = [m.id for m in models_page.data]
        print(f"📋 مدل‌های فعال حساب شما: {active_models}")
        
        for pref in preferred_order:
            if pref in active_models:
                return pref
                
        if active_models:
            return active_models[0]
            
    except Exception as e:
        print(f"⚠️ خطا در لیست کردن مدل‌ها از API: {e}")
        
    return "openai/gpt-oss-20b"

def summarize_with_groq(prompt, selected_model):
    try:
        completion = client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=1500  # افزایش ظرفیت برای جلوگیری از نصفه ماندن متن
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"❌ خطای اجرای مدل {selected_model}: {e}")
        return None

def run_bot():
    posted_links = load_posted_links()

    working_model = get_active_groq_model()
    print(f"🚀 مدل انتخاب شده: {working_model}")

    for source_name, rss_url in RSS_SOURCES.items():
        try:
            feed = feedparser.parse(rss_url)
            
            for entry in reversed(feed.entries[:5]):
                link = entry.link
                
                if link in posted_links:
                    continue
                
                title = entry.title
                summary = entry.summary if 'summary' in entry else title
                
                print(f"\n📰 خبر جدید پیدا شد از {source_name}: {title}")
                
                prompt = f"""
تو یک مترجم حرفه‌ای و روزنامه‌نگار ارشد حوزه کریپتو هستی.
خبر زیر را از منبع {source_name} به فارسی روان ترجمه و خلاصه کن.

قوانین مهم برای نگارش:
۱. از ترجمه کلمه به کلمه و خشک خودداری کن. اصطلاحات را به فارسی سلیس و مطبوعاتی ترجمه کن.
۲. تمام جملات باید کامل باشند و کلام نیمه‌کاره رها نشود.
۳. فرمت خروجی باید دقیقاً به شکل زیر باشد و هیچ متن اضافه دیگری همراه آن فرستاده نشود:

📌 **تیتر:** [ترجمه تیتر به صورت جذاب و روان]
🌐 **منبع اصلی:** {source_name}
📝 **خلاصه خبر:** [ترجمه روان خلاصه خبر در ۳ جمله کامل]
💡 **تحلیل کوتاه:** [یک تحلیل کوتاه و کاربردی در ۲ جمله کامل]

اطلاعات خبر اصلی:
تیتر اصلی: {title}
متن خبر: {summary}
"""
                response_text = summarize_with_groq(prompt, working_model)

                if not response_text:
                    print("❌ عدم دریافت پاسخ، عبور به خبر بعدی...")
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
                    print(f"✅ خبر با موفقیت در تلگرام ارسال شد.")
                    save_posted_link(link)
                    posted_links.add(link)
                    time.sleep(20)
                else:
                    print(f"❌ خطا در ارسال به تلگرام: {res.status_code}")
                
        except Exception as e:
            print(f"Error processing {source_name}: {e}")

if __name__ == "__main__":
    run_bot()
