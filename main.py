import os
import feedparser
from google import genai
from google.genai import types
import requests
import time
import re
import html

# =========================================================
# CONFIG
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

if not TELEGRAM_CHAT_ID:
    raise RuntimeError("TELEGRAM_CHAT_ID is not set")


client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3.6-flash"

RSS_SOURCES = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CoinTelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
    "CryptoPotato": "https://cryptopotato.com/feed/"
}

DB_FILE = "posted_links.txt"

# تعداد خبرهایی که از هر سایت می‌گیریم
NEWS_PER_SOURCE = 2

# تعداد خبرهایی که در هر درخواست به Gemini می‌فرستیم
BATCH_SIZE = 4

# فاصله بین درخواست‌های موفق Gemini
REQUEST_DELAY = 8

# =========================================================
# DATABASE
# =========================================================

def load_posted_links():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return set(
                line.strip()
                for line in f
                if line.strip()
            )

    return set()


def save_posted_link(link):
    with open(DB_FILE, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")


# =========================================================
# RSS
# =========================================================

def fetch_news(posted_links):
    """
    دریافت اخبار جدید از تمام RSSها.
    """

    news = []

    for source_name, rss_url in RSS_SOURCES.items():

        try:
            print(f"\n🔎 بررسی {source_name} ...")

            feed = feedparser.parse(rss_url)

            if not feed.entries:
                print(f"⚠️ هیچ خبری از {source_name} دریافت نشد.")
                continue

            # آخرین NEWS_PER_SOURCE خبر
            entries = feed.entries[:NEWS_PER_SOURCE]

            for entry in entries:

                link = entry.get("link", "").strip()

                if not link:
                    continue

                # اگر قبلاً ارسال شده، رد شود
                if link in posted_links:
                    continue

                title = entry.get("title", "").strip()

                summary = (
                    entry.get("summary")
                    or entry.get("description")
                    or title
                )

                # حذف HTML از summary
                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()

                if not title:
                    continue

                article = {
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": link
                }

                news.append(article)

                print(f"📰 خبر جدید: {title}")

        except Exception as e:
            print(f"❌ خطا در دریافت {source_name}: {e}")

    return news


# =========================================================
# GEMINI
# =========================================================

def create_prompt(batch):
    """
    ساخت prompt برای چند خبر به صورت همزمان.
    """

    articles_text = ""

    for i, article in enumerate(batch, 1):

        articles_text += f"""
================ ARTICLE {i} ================

SOURCE:
{article['source']}

TITLE:
{article['title']}

SUMMARY:
{article['summary']}

LINK:
{article['link']}

================================================
"""

    prompt = f"""
تو یک تحلیل‌گر ارشد بازار ارزهای دیجیتال و مترجم حرفه‌ای اخبار کریپتو هستی.

من تعدادی خبر جدید از منابع معتبر کریپتویی به تو می‌دهم.

وظایف تو:

1. تیتر هر خبر را به فارسی روان و جذاب ترجمه کن.
2. محتوای خبر را به صورت دقیق و بی‌طرفانه در 3 جمله خلاصه کن.
3. یک تحلیل کوتاه و کاربردی در 2 جمله ارائه بده.
4. اگر خبر می‌تواند روی Bitcoin، Ethereum یا Altcoins تأثیر داشته باشد، در تحلیل به آن اشاره کن.
5. از ساختن اطلاعاتی که در متن خبر وجود ندارد خودداری کن.
6. تحلیل باید واقع‌بینانه باشد و نباید توصیه مستقیم برای خرید یا فروش بدهد.
7. اگر چند خبر درباره یک اتفاق مشابه هستند، آن‌ها را تشخیص بده و از تکرار بی‌مورد تحلیل خودداری کن.

خیلی مهم:

برای هر مقاله دقیقاً با این فرمت پاسخ بده:

### ARTICLE 1
📌 تیتر: ...
🌐 منبع اصلی: ...
📝 خلاصه خبر: ...
💡 تحلیل کوتاه: ...

### ARTICLE 2
📌 تیتر: ...
🌐 منبع اصلی: ...
📝 خلاصه خبر: ...
💡 تحلیل کوتاه: ...

و به همین ترتیب.

هیچ توضیح اضافه‌ای خارج از این ساختار ننویس.

اخبار:

{articles_text}
"""

    return prompt


def ask_gemini(batch):
    """
    ارسال batch به Gemini با retry و exponential backoff.
    """

    prompt = create_prompt(batch)

    # تلاش‌های مجاز
    max_retries = 4

    # exponential backoff
    # 10 → 20 → 40 → 80
    delays = [10, 20, 40, 80]

    for attempt in range(max_retries):

        try:

            print(
                f"\n🤖 ارسال {len(batch)} خبر به Gemini "
                f"(تلاش {attempt + 1}/{max_retries})..."
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                    temperature=0.3
                )
            )

            if response and response.text:

                print("✅ پاسخ Gemini دریافت شد.")

                return response.text.strip()

            print("⚠️ Gemini پاسخ خالی برگرداند.")

        except Exception as e:

            error_text = str(e)

            is_retryable = (
                "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
                or "503" in error_text
                or "UNAVAILABLE" in error_text
            )

            if is_retryable:

                delay = delays[attempt]

                print(
                    f"⚠️ Gemini محدودیت/خطای موقت داد."
                )

                print(
                    f"⏳ {delay} ثانیه تا تلاش بعدی..."
                )

                time.sleep(delay)

            else:

                print(
                    f"❌ خطای غیرقابل retry در Gemini:"
                )

                print(error_text)

                return None

    print("❌ Gemini بعد از چند تلاش پاسخ نداد.")

    return None


# =========================================================
# PARSE GEMINI RESPONSE
# =========================================================

def split_gemini_response(response_text, batch):
    """
    پاسخ Gemini را به خروجی هر خبر تقسیم می‌کند.
    """

    results = []

    # پیدا کردن ARTICLE 1 / ARTICLE 2 / ...
    pattern = r"###\s*ARTICLE\s*(\d+)"

    matches = list(re.finditer(pattern, response_text, re.IGNORECASE))

    if not matches:
        print("⚠️ ساختار پاسخ Gemini قابل تشخیص نبود.")
        return results

    for index, match in enumerate(matches):

        article_number = int(match.group(1))

        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
            content = response_text[start:end].strip()
        else:
            content = response_text[start:].strip()

        if 1 <= article_number <= len(batch):

            article = batch[article_number - 1].copy()

            article["analysis"] = content

            results.append(article)

    return results


# =========================================================
# TELEGRAM
# =========================================================

def send_to_telegram(article):
    """
    ارسال یک خبر به Telegram.
    """

    source = html.escape(article["source"])
    analysis = article["analysis"]

    # جلوگیری از خراب شدن HTML
    # فقط محتوای Gemini را escape می‌کنیم
    analysis = html.escape(analysis)

    link = html.escape(article["link"], quote=True)

    final_message = (
        f"{analysis}\n\n"
        f'🔗 <a href="{link}">مطالعه اصل خبر</a>'
    )

    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": final_message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            telegram_url,
            data=payload,
            timeout=30
        )

        if response.status_code == 200:

            print(
                f"✅ خبر ارسال شد: {article['title']}"
            )

            return True

        else:

            print(
                f"❌ Telegram Error: "
                f"{response.status_code}"
            )

            print(response.text)

            return False

    except Exception as e:

        print(
            f"❌ خطا در اتصال به Telegram: {e}"
        )

        return False


# =========================================================
# MAIN
# =========================================================

def run_bot():

    print("\n======================================")
    print("🚀 Crypto News Bot Started")
    print("======================================\n")

    posted_links = load_posted_links()

    print(
        f"📚 تعداد اخبار قبلاً ارسال‌شده: "
        f"{len(posted_links)}"
    )

    # -----------------------------------------------------
    # 1. دریافت اخبار جدید
    # -----------------------------------------------------

    news = fetch_news(posted_links)

    if not news:

        print("\nℹ️ هیچ خبر جدیدی پیدا نشد.")
        return

    print(
        f"\n📰 تعداد اخبار جدید: {len(news)}"
    )

    # -----------------------------------------------------
    # 2. تقسیم اخبار به batch
    # -----------------------------------------------------

    batches = [
        news[i:i + BATCH_SIZE]
        for i in range(0, len(news), BATCH_SIZE)
    ]

    print(
        f"📦 تعداد Batchها: {len(batches)}"
    )

    # -----------------------------------------------------
    # 3. پردازش هر Batch
    # -----------------------------------------------------

    for batch_number, batch in enumerate(batches, 1):

        print(
            f"\n======================================"
        )

        print(
            f"📦 Batch {batch_number}/{len(batches)}"
        )

        print(
            f"📰 تعداد اخبار این Batch: {len(batch)}"
        )

        print(
            f"======================================"
        )

        # -------------------------------------------------
        # Gemini
        # -------------------------------------------------

        response_text = ask_gemini(batch)

        if not response_text:

            print(
                "❌ این Batch پردازش نشد."
            )

            continue

        # -------------------------------------------------
        # Parse
        # -------------------------------------------------

        processed_articles = split_gemini_response(
            response_text,
            batch
        )

        if not processed_articles:

            print(
                "❌ نتوانستیم پاسخ Gemini را "
                "به اخبار تقسیم کنیم."
            )

            continue

        print(
            f"✅ تعداد اخبار پردازش‌شده: "
            f"{len(processed_articles)}"
        )

        # -------------------------------------------------
        # Telegram
        # -------------------------------------------------

        for article in processed_articles:

            success = send_to_telegram(article)

            if success:

                save_posted_link(
                    article["link"]
                )

                posted_links.add(
                    article["link"]
                )

                # فاصله بین ارسال‌های Telegram
                time.sleep(3)

            else:

                print(
                    "⚠️ خبر در Telegram ارسال نشد؛ "
                    "در DB ذخیره نمی‌شود."
                )

        # فاصله بین Batchهای Gemini
        if batch_number < len(batches):

            print(
                f"\n⏳ {REQUEST_DELAY} ثانیه "
                f"تا Batch بعدی..."
            )

            time.sleep(REQUEST_DELAY)

    print("\n======================================")
    print("🏁 Bot Finished")
    print("======================================")


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    run_bot()
