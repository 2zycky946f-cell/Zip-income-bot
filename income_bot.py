import os
import re
import sqlite3
import datetime
import secrets
import aiohttp
import easyocr

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    BotCommandScopeChat
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)


BOT_TOKEN = os.getenv("BOT_TOKEN")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

ADMIN_ID = 8834288282


# ---------- OCR ---------- #

reader = easyocr.Reader(["en"])



# ---------- DATABASE ---------- #

db = sqlite3.connect(
    "bot.db",
    check_same_thread=False
)

cur = db.cursor()


cur.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
plan TEXT DEFAULT 'FREE',
expires TEXT,
searches INTEGER DEFAULT 0
)
""")


cur.execute("""
CREATE TABLE IF NOT EXISTS keys(
key TEXT PRIMARY KEY,
days INTEGER,
used INTEGER DEFAULT 0
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



# ---------- COMMAND MENU ---------- #

async def setup_commands(app):

    try:

        normal = [
            BotCommand("start","Start"),
            BotCommand("lookup","Lookup ZIP"),
            BotCommand("redeem","Redeem key")
        ]


        admin = normal + [
            BotCommand("createkey","Create key"),
            BotCommand("stats","Stats")
        ]


        await app.bot.set_my_commands(normal)

        await app.bot.set_my_commands(
            admin,
            scope=BotCommandScopeChat(
                chat_id=ADMIN_ID
            )
        )

        print("Commands loaded")

    except Exception as e:

        print(
            "Command error:",
            e
        )



# ---------- USERS ---------- #

def create_user(uid):

    cur.execute(
        "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
        (uid,)
    )

    db.commit()



def premium(uid):

    create_user(uid)

    cur.execute(
        "SELECT * FROM users WHERE user_id=?",
        (uid,)
    )

    user = cur.fetchone()


    if not user[2]:
        return False


    return (
        datetime.datetime.fromisoformat(user[2])
        >
        datetime.datetime.now()
    )



# ---------- START ---------- #

async def start(update, context):

    create_user(
        update.effective_user.id
    )


    keyboard = [

        [
            InlineKeyboardButton(
                "🔍 Lookup ZIP",
                callback_data="lookup"
            )
        ],

        [
            InlineKeyboardButton(
                "👤 Account",
                callback_data="account"
            )
        ]

    ]


    await update.message.reply_text(
"""
🔥 ZIP Income Bot

Send ZIP codes or screenshots.

Example:
93725
93291
93654
""",
reply_markup=InlineKeyboardMarkup(keyboard)
)



# ---------- ZIP SEARCH ---------- #

async def search_zip(zipcode):

    cur.execute(
        "SELECT * FROM cache WHERE zip=?",
        (zipcode,)
    )

    saved = cur.fetchone()


    if saved:

        return f"""
⚡ {zipcode}

Income:
{saved[1]}

Population:
{saved[2]}

Cached
"""


    try:

        url = (
        "https://api.census.gov/data/2023/acs/acs5/profile?"
        "get=NAME,DP03_0062PE,DP05_0001E&"
        f"for=zip%20code%20tabulation%20area:{zipcode}"
        f"&key={CENSUS_API_KEY}"
        )


        async with aiohttp.ClientSession() as session:

            async with session.get(
                url,
                timeout=15
            ) as r:

                data = await r.json()


        income = data[1][1]
        population = data[1][2]


        cur.execute(
"""
INSERT OR REPLACE INTO cache
VALUES(?,?,?)
""",
(
zipcode,
income,
population
)
)

        db.commit()


        return f"""
📊 {zipcode}

Income:
{income}

Population:
{population}
"""


    except Exception as e:

        print(
            "SEARCH ERROR:",
            e
        )

        return f"❌ {zipcode} failed"



# ---------- TEXT ---------- #

async def zip_text(update, context):

    zips = re.findall(
        r"\b\d{5}\b",
        update.message.text
    )


    if not zips:
        return


    await update.message.reply_text(
        "🔍 Checking ZIP codes..."
    )


    results=[]


    for z in zips:

        results.append(
            await search_zip(z)
        )


    await update.message.reply_text(
        "\n\n".join(results)
    )



# ---------- IMAGE OCR ---------- #

async def image_zip(update, context):

    await update.message.reply_text(
        "📷 Reading image..."
    )


    photo = update.message.photo[-1]

    file = await photo.get_file()

    path = "photo.jpg"

    await file.download_to_drive(path)


    results = reader.readtext(path)


    text = " ".join(
        item[1]
        for item in results
    )


    zips = re.findall(
        r"\b\d{5}\b",
        text
    )


    if not zips:

        await update.message.reply_text(
            "❌ No ZIP codes found"
        )

        return



    await update.message.reply_text(
        f"✅ Found:\n{zips}"
    )


    answers=[]


    for z in zips:

        answers.append(
            await search_zip(z)
        )


    await update.message.reply_text(
        "\n\n".join(answers)
    )



# ---------- BUTTONS ---------- #

async def buttons(update, context):

    q = update.callback_query

    await q.answer()


    if q.data=="lookup":

        await q.edit_message_text(
"""
🔍 Send ZIP codes

Examples:

93725
93291
93654

Or upload a screenshot 📷
"""
        )


    elif q.data=="account":

        cur.execute(
            "SELECT * FROM users WHERE user_id=?",
            (q.from_user.id,)
        )

        u = cur.fetchone()


        await q.edit_message_text(
f"""
👤 Account

Plan:
{u[1]}

Searches:
{u[3]}

Premium:
{"YES ✅" if premium(q.from_user.id) else "NO ❌"}
"""
        )



# ---------- ADMIN ---------- #

async def createkey(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    days = int(context.args[0])

    key = secrets.token_hex(8)


    cur.execute(
        "INSERT INTO keys VALUES(?,?,0)",
        (key,days)
    )

    db.commit()


    await update.message.reply_text(
        f"🔑 {key}\nDays: {days}"
    )



# ---------- RUN ---------- #

app = Application.builder().token(BOT_TOKEN).build()


app.add_handler(
CommandHandler("start",start)
)

app.add_handler(
CommandHandler("lookup",zip_text)
)

app.add_handler(
CommandHandler("createkey",createkey)
)


app.add_handler(
CallbackQueryHandler(buttons)
)


app.add_handler(
MessageHandler(
filters.TEXT & ~filters.COMMAND,
zip_text
)
)


app.add_handler(
MessageHandler(
filters.PHOTO,
image_zip
)
)


app.post_init = setup_commands


print("🔥 Premium bot running")


app.run_polling()
