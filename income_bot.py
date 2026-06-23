import os
import re
import sqlite3
import asyncio
import aiohttp
import easyocr

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

TOKEN = os.getenv("BOT_TOKEN")
CENSUS_KEY = os.getenv("CENSUS_API_KEY")

ADMIN_ID = 8834288282
BTC_ADDRESS = "bc1qeyfhgadc52lzecacafgh9n7hy84y2gfhd76evc"

# ---------- DATABASE ----------

db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY,
    plan TEXT DEFAULT 'FREE',
    expire TEXT,
    searches INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS cache(
    zip TEXT PRIMARY KEY,
    income TEXT,
    population TEXT
)
""")

db.commit()

# ---------- OCR ----------

print("Loading OCR...")
ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
print("OCR Ready")

def add_user(uid):
    cur.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
    db.commit()

async def lookup_zip(zip_code):

    cur.execute(
        "SELECT income,population FROM cache WHERE zip=?",
        (zip_code,)
    )
    row = cur.fetchone()

    if row:
        return f"ð {zip_code}\nIncome: ${row[0]}\nPopulation: {row[1]}"

    try:

        url = (
            f"https://api.census.gov/data/2023/acs/acs5/profile"
            f"?get=NAME,DP03_0062E,DP05_0001E"
            f"&for=zip%20code%20tabulation%20area:{zip_code}"
            f"&key={CENSUS_KEY}"
        )

        timeout = aiohttp.ClientTimeout(total=60)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:

                if resp.status != 200:
                    return f"â {zip_code} lookup failed"

                data = await resp.json()

        print(f"ZIP {zip_code} RESPONSE:", data)

        if len(data) < 2:
            return f"â {zip_code} not found"

        income = data[1][1]
        population = data[1][2]

        cur.execute(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            (zip_code, income, population)
        )
        db.commit()

        return (
            f"ð {zip_code}\n"
            f"Income: ${income}\n"
            f"Population: {population}"
        )

    except Exception as e:
        print("INCOME ERROR:", e)
        return f"â {zip_code} failed"

async def start(update: Update, context):
    add_user(update.effective_user.id)

    keyboard = [
        [InlineKeyboardButton("ð Lookup", callback_data="lookup")],
        [InlineKeyboardButton("ð Premium", callback_data="premium")],
        [InlineKeyboardButton("ð¤ Account", callback_data="account")]
    ]

    await update.message.reply_text(
        "ð¥ ZIP Income Bot",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def text_zip(update: Update, context):

    zips = list(set(re.findall(r"\b\d{5}\b", update.message.text)))

    if not zips:
        await update.message.reply_text("Send a valid ZIP code.")
        return

    await update.message.reply_text("ð Searching...")

    results = [await lookup_zip(z) for z in zips]

    await update.message.reply_text("\n\n".join(results))

async def image(update: Update, context):

    await update.message.reply_text("ð· Reading screenshot...")

    filename = f"img_{update.effective_user.id}.jpg"

    try:

        print("Downloading photo...")

        file = await update.message.photo[-1].get_file()
        await file.download_to_drive(filename)

        print("Photo downloaded")

        results = await asyncio.wait_for(
            asyncio.to_thread(
                ocr.readtext,
                filename,
                detail=0,
                paragraph=True
            ),
            timeout=60
        )

        print("OCR complete")

        text = " ".join(results)

        print("OCR TEXT:")
        print(text)

        zips = list(set(re.findall(r"\b\d{5}\b", text)))

        print("ZIPS FOUND:", zips)

        if not zips:
            await update.message.reply_text("â No ZIP codes found.")
            return

        output = []

        for zip_code in zips:
            result = await lookup_zip(zip_code)
            print("INCOME RESULT:", result)
            output.append(result)

        await update.message.reply_text("\n\n".join(output))

    except asyncio.TimeoutError:
        await update.message.reply_text("â OCR timed out.")

    except Exception as e:
        print("PHOTO ERROR:", e)
        await update.message.reply_text(f"â Image error:\n{e}")

    finally:
        try:
            os.remove(filename)
        except:
            pass

async def buttons(update: Update, context):

    q = update.callback_query
    await q.answer()

    if q.data == "lookup":
        await q.edit_message_text(
            "Send ZIP codes or upload a screenshot."
        )

    elif q.data == "premium":
        await q.edit_message_text(
            f"ð Premium\n\nBitcoin:\n{BTC_ADDRESS}"
        )

    elif q.data == "account":

        cur.execute(
            "SELECT * FROM users WHERE id=?",
            (q.from_user.id,)
        )

        user = cur.fetchone()

        await q.edit_message_text(
            f"Plan: {user[1]}\n"
            f"Searches: {user[3]}\n"
            f"Expires: {user[2] or 'Never'}"
        )

async def set_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start")
    ])

app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_zip))
app.add_handler(MessageHandler(filters.PHOTO, image))
app.add_handler(CallbackQueryHandler(buttons))

app.post_init = set_commands

print("ð¥ Bot running")
app.run_polling()
