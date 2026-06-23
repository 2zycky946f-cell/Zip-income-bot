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

if not TOKEN:
    raise Exception("BOT_TOKEN missing")

if not CENSUS_KEY:
    raise Exception("CENSUS_API_KEY missing")
    
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
ocr = easyocr.Reader(
    ["en"],
    gpu=False,
    verbose=False
)
print("OCR Ready")
print("OCR OBJECT CREATED")

def add_user(uid):
    cur.execute("INSERT OR IGNORE INTO users(id) VALUES(?)", (uid,))
    db.commit()



async def start(update: Update, context):
    add_user(update.effective_user.id)

    keyboard = [
    [InlineKeyboardButton("🔍 Lookup", callback_data="lookup")],
    [InlineKeyboardButton("💎 Premium", callback_data="premium")],
    [InlineKeyboardButton("👤 Account", callback_data="account")]
]

    await update.message.reply_text(
    "🔥 ZIP Income Bot\n\n"
    "📊 Discover median incomes by ZIP code.\n"
    "📸 Upload screenshots or enter ZIP codes manually.\n\n"
    "Choose an option below:",
    reply_markup=InlineKeyboardMarkup(keyboard)
)

async def lookup_zip(zip_code):

    cur.execute(
        "SELECT income,population FROM cache WHERE zip=?",
        (zip_code,)
    )

    row = cur.fetchone()

    if row:
        return (
            f"📊 ZIP: {zip_code}\n"
            f"💰 Income: ${row[0]}\n"
            f"👥 Population: {row[1]}"
        )

    try:

        url = (
            "https://api.census.gov/data/2023/acs/acs5/profile"
            "?get=NAME,DP03_0062E,DP05_0001E"
            f"&for=zip%20code%20tabulation%20area:{zip_code}"
            f"&key={CENSUS_KEY}"
        )

        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(timeout=timeout) as session:

            async with session.get(url) as r:

                data = await r.json()


        if len(data) < 2:
            return f"❌ {zip_code} not found"


        income = data[1][1]
        population = data[1][2]


        cur.execute(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            (zip_code,income,population)
        )

        db.commit()


        return (
            f"📊 ZIP: {zip_code}\n"
            f"💰 Income: ${income}\n"
            f"👥 Population: {population}"
        )


    except Exception as e:

        print("LOOKUP ERROR:",e)

        return (
            f"❌ {zip_code}\n"
            "Income lookup failed"
        )
async def text_zip(update: Update, context):

    zips = list(set(
        re.findall(r"\b\d{5}\b", update.message.text)
    ))

    if not zips:
        await update.message.reply_text(
            "❌ Send a valid ZIP code."
        )
        return

    await update.message.reply_text(
        "🔍 Searching..."
    )

    results = []

    for zip_code in zips:

        result = await lookup_zip(zip_code)

        # pull income number from result
        match = re.search(r"Income: \$(\d+)", result)

        income = int(match.group(1)) if match else 0

        results.append((income, result))


    # HIGH → LOW income sort
    results.sort(reverse=True, key=lambda x: x[0])


    await update.message.reply_text(
        "\n\n".join(x[1] for x in results)
    )
async def image(update: Update, context):

    status = await update.message.reply_text(
        "📸 Reading Screenshot..."
    )

    filename = f"img_{update.effective_user.id}.jpg"

    try:

        print("Downloading photo...")

        file = await update.message.photo[-1].get_file()

        await file.download_to_drive(filename)

        print("Photo downloaded")

        from PIL import Image

        img = Image.open(filename)

        print("ORIGINAL SIZE:", img.size)

        img.thumbnail((1000, 1000))

        img.save(filename)

        print("RESIZED SIZE:", img.size)

        print("Starting OCR...")

        results = await asyncio.to_thread(
            ocr.readtext,
            filename,
            detail=0,
            paragraph=False
        )

        print("OCR Finished")
        await status.edit_text(
    "🔎 Detecting ZIP Codes..."
)
        text = " ".join(
            str(x) for x in results
        )

        print("OCR TEXT:")
        print(text)

        zips = []

        for match in re.findall(
            r"\d{5}",
            text
        ):
            if match not in zips:
                zips.append(match)

        print("ZIPS FOUND:", zips)

        await status.edit_text(
            "📊 Looking Up Income Data..."
        )

        if not zips:

            await update.message.reply_text(
                "❌ No ZIP codes found."
            )

            return

        output = []

        for zip_code in zips:

            print("LOOKING UP:", zip_code)

            result = await lookup_zip(zip_code)

            print(
                "INCOME RESULT:",
                result
            )

            match = re.search(r"Income: \$(\d+)", result)

            income = int(match.group(1)) if match else 0

            output.append((income, result))

        output.sort(
            reverse=True,
            key=lambda x: x[0]
        )
        if not output:
            await status.edit_text("❌ No income results found")
            return
        highest = output[0][0]
        lowest = output[-1][0]
        average = sum(x[0] for x in output) // len(output)
        
        await status.edit_text(
            "✅ Report Ready"
        )
        await update.message.reply_text(
            f"📈 ZIP Report Summary\n\n"
            f"📍 ZIPs Found: {len(output)}\n"
            f"💰 Highest Income: ${highest:,}\n"
            f"📉 Lowest Income: ${lowest:,}\n"
            f"📊 Average Income: ${average:,}\n\n"
            + "\n\n".join(x[1] for x in output)
        )      
        

    except Exception as e:

        print(
            "PHOTO ERROR:",
            e
        )

        await update.message.reply_text(
            f"❌ Image error:\n{e}"
        )

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
            "📸 Send ZIP codes or upload a screenshot\n\n"
            "Examples:\n"
            "93618\n"
            "93646\n"
            "93722\n\n"
            "You can send multiple ZIP codes at once.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="home")]
            ])
        )

    elif q.data == "premium":
        await q.edit_message_text(
            "💎 PREMIUM PLANS 💎\n\n"
            "💎 1 Day — $1\n"
            "💎 1 Week — $5\n"
            "💎 1 Month — $20\n"
            "💎 Lifetime — $30\n\n"
            "₿ Bitcoin Payment Address:\n"
            f"{BTC_ADDRESS}\n\n"
            "📩 After payment, send proof of payment to receive your activation code.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="home")]
            ]) 
        )

    elif q.data == "account":

        cur.execute(
            "SELECT * FROM users WHERE id=?",
            (q.from_user.id,)
        )

        user = cur.fetchone()

        if not user:
            add_user(q.from_user.id)
            cur.execute(
                "SELECT * FROM users WHERE id=?",
                (q.from_user.id,)
            )
            user = cur.fetchone()

        await q.edit_message_text(
            "👤 ACCOUNT\n\n"
            f"⭐ Plan: {user[1]}\n"
            f"🔎 Searches: {user[3]}\n"
            f"📅 Expires: {user[2] or 'Never'}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="home")]
            ]) 
        )


    elif q.data == "home":

        keyboard = [
            [InlineKeyboardButton("🔍 Lookup", callback_data="lookup")],
            [InlineKeyboardButton("💎 Premium", callback_data="premium")],
            [InlineKeyboardButton("👤 Account", callback_data="account")]
        ]

        await q.edit_message_text(
            "🔥 ZIP Income Bot\n\n"
            "📊 Discover median incomes by ZIP code.\n"
            "📸 Upload screenshots or enter ZIP codes manually.\n\n"
            "Choose an option below:",
            reply_markup=InlineKeyboardMarkup(keyboard)
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

print("🔥 Bot running")
app.run_polling()
