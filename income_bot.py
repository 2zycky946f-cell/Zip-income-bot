import os
import re
import requests
import sqlite3
import secrets
import time
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

ADMIN_ID = 8834288282

db = sqlite3.connect("licenses.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    plan TEXT,
    used INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    expires_at INTEGER
)
""")

db.commit()

def create_key(plan):
    key = f"{plan.upper()}-{secrets.token_hex(4).upper()}"
    cur.execute("INSERT INTO keys VALUES (?, ?, 0)", (key, plan))
    db.commit()
    return key

def has_access(user_id):
    cur.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        return False
    return row[0] > int(time.time())

def redeem_key(user_id, key):
    cur.execute("SELECT plan, used FROM keys WHERE key=?", (key,))
    row = cur.fetchone()

    if not row:
        return "Invalid key."

    plan, used = row

    if used:
        return "Key already used."

    now = int(time.time())

    cur.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
    current = cur.fetchone()

    expires = current[0] if current and current[0] > now else now

    if plan == "day":
        expires += 86400
    elif plan == "week":
        expires += 604800
    elif plan == "month":
        expires += 2592000

    cur.execute(
        "INSERT OR REPLACE INTO users VALUES (?, ?)",
        (user_id, expires)
    )

    cur.execute(
        "UPDATE keys SET used=1 WHERE key=?",
        (key,)
    )

    db.commit()
    return f"{plan} activated."

def get_status(user_id):
    cur.execute("SELECT expires_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if not row:
        return "No active subscription."

    remaining = row[0] - int(time.time())

    if remaining <= 0:
        return "Subscription expired."

    days = round(remaining / 86400, 2)

    return f"Days left: {days}\nExpires: {datetime.fromtimestamp(row[0])}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ZipIncome Bot\n\nSend ZIP codes like:\n93618 93722 90210"
    )

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /genkey day|week|month")
        return

    await update.message.reply_text(create_key(context.args[0].lower()))

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /redeem KEY")
        return

    await update.message.reply_text(
        redeem_key(update.effective_user.id, context.args[0])
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_status(update.effective_user.id)
    )

def get_income(zip_code):
    try:
        zip_code = str(zip_code).strip().zfill(5)

        url = (
            "https://api.census.gov/data/2023/acs/acs5"
            f"?get=B19013_001E"
            f"&for=zip%20code%20tabulation%20area:{zip_code}"
            f"&key={CENSUS_API_KEY}"
        )

        response = requests.get(url, timeout=60)

        if response.status_code != 200:
            return "Not found"

        data = response.json()

        if len(data) > 1:
            return int(data[1][0])

    except Exception:
        pass

    return "Timeout"

def make_message(zips):
    results = []

    for z in zips:
        results.append({"zip": z, "income": get_income(z)})

    results.sort(
        key=lambda x: x["income"] if isinstance(x["income"], int) else 0,
        reverse=True
    )

    message = "ZIP Income Results:\n\n"

    for item in results:
        if item["income"] == "Not found":
            message += f"{item['zip']}: Not found\n"
        else:
            try:
                message += f"{item['zip']}: ${item['income']:,}\n"
            except:
                message += f"{item['zip']}: {item['income']}\n"

    return message

def read_zips(image_path):
    try:
        url = "https://api.ocr.space/parse/image"

        with open(image_path, "rb") as image:
            response = requests.post(
                url,
                files={"filename": image},
                data={
                    "apikey": "helloworld",
                    "language": "eng",
                    "OCREngine": 2,
                    "scale": True
                },
                timeout=30
            )

        data = response.json()
        text = ""

        for item in data.get("ParsedResults", []):
            text += item.get("ParsedText", "") + "\n"

        found = re.findall(r"\d{5}", text)

        if not found:
            found = re.findall(r"\d+", text)
            found = [x.zfill(5) for x in found if len(x) >= 4]

        return list(dict.fromkeys(found))

    except Exception:
        return []

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not has_access(update.effective_user.id):
        await update.message.reply_text(
            "Subscription required. Contact @paperboyza"
        )
        return

    text = update.message.text
    zips = re.findall(r"\d{5}", text)

    if not zips:
        await update.message.reply_text("No ZIP codes found.")
        return

    await update.message.reply_text("Checking incomes...")
    await update.message.reply_text(make_message(list(dict.fromkeys(zips))))

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not has_access(update.effective_user.id):
        await update.message.reply_text(
            "Subscription required. Contact @paperboyza"
        )
        return

    await update.message.reply_text("Reading image...")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)

    image_path = "/tmp/photo.jpg"
    await file.download_to_drive(image_path)

    zips = read_zips(image_path)

    if not zips:
        await update.message.reply_text("No ZIP codes found in image.")
        return

    await update.message.reply_text(make_message(zips))

app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("status", status))

app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("ZipIncome Bot running")
app.run_polling()
