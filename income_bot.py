import os
import re
import sqlite3
import datetime
import secrets
import aiohttp
import pytesseract

from PIL import Image

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


# ---------------- DATABASE ----------------

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



# ---------------- MENU ----------------


async def setup_commands(app):

    try:

        users = [
            BotCommand("start","Start bot"),
            BotCommand("lookup","ZIP lookup"),
            BotCommand("redeem","Redeem key")
        ]


        admin = users + [
            BotCommand("createkey","Create key"),
            BotCommand("stats","Stats")
        ]


        await app.bot.set_my_commands(users)


        await app.bot.set_my_commands(
            admin,
            scope=BotCommandScopeChat(
                chat_id=ADMIN_ID
            )
        )

        print("Commands loaded")


    except Exception as e:
        print(
            "Command menu error:",
            e
        )



# ---------------- USERS ----------------


def create_user(uid):

    cur.execute(
        "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
        (uid,)
    )

    db.commit()



def is_premium(uid):

    create_user(uid)

    cur.execute(
        "SELECT * FROM users WHERE user_id=?",
        (uid,)
    )

    u = cur.fetchone()


    if not u[2]:
        return False


    return (
        datetime.datetime.fromisoformat(u[2])
        >
        datetime.datetime.now()
    )



# ---------------- START ----------------


async def start(update, context):

    create_user(
        update.effective_user.id
    )


    buttons = [

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
🔥 Income Bot

Send ZIP codes or screenshots.

Choose:
""",
reply_markup=InlineKeyboardMarkup(buttons)
)



# ---------------- ZIP SEARCH ----------------


async def get_income(zipcode):

    cur.execute(
        "SELECT * FROM cache WHERE zip=?",
        (zipcode,)
    )

    old = cur.fetchone()


    if old:

        return (
f"""
📊 ZIP {zipcode}

Income:
{old[1]}

Population:
{old[2]}

⚡ Cached
"""
        )


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
                timeout=10
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


        return (
f"""
📊 ZIP {zipcode}

Income:
{income}

Population:
{population}
"""
        )


    except Exception as e:

        print(
            "ZIP ERROR:",
            e
        )

        return (
f"❌ {zipcode} failed"
        )



# ---------------- TEXT ZIP ----------------


async def zip_text(update, context):

    zips = re.findall(
        r"\b\d{5}\b",
        update.message.text
    )


    if not zips:
        return


    await update.message.reply_text(
        "🔍 Searching..."
    )


    results=[]


    for z in zips:

        results.append(
            await get_income(z)
        )


    await update.message.reply_text(
        "\n\n".join(results)
    )



# ---------------- PHOTO OCR ----------------


async def photo_lookup(update, context):

    await update.message.reply_text(
        "📷 Reading screenshot..."
    )


    photo = update.message.photo[-1]

    file = await photo.get_file()

    path="image.jpg"

    await file.download_to_drive(path)


    text = pytesseract.image_to_string(
        Image.open(path)
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
        f"✅ Found:\n{zips}\n\n🔍 Getting incomes..."
    )


    results=[]


    for z in zips:

        results.append(
            await get_income(z)
        )


    await update.message.reply_text(
        "\n\n".join(results)
    )



# ---------------- BUTTONS ----------------


async def buttons(update, context):

    q = update.callback_query

    await q.answer()


    if q.data=="lookup":

        await q.edit_message_text(
"""
🔍 ZIP Income Lookup

Send:

93725
93291
93654

or upload a screenshot 📷
"""
        )


    if q.data=="account":

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
{"YES ✅" if is_premium(q.from_user.id) else "NO ❌"}
"""
        )



# ---------------- KEYS ----------------


async def createkey(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    days=int(context.args[0])

    key=secrets.token_hex(8)


    cur.execute(
        "INSERT INTO keys VALUES(?,?,0)",
        (key,days)
    )


    db.commit()


    await update.message.reply_text(
        f"🔑 {key}\nDays: {days}"
    )



async def redeem(update, context):

    key=context.args[0]


    cur.execute(
        "SELECT * FROM keys WHERE key=?",
        (key,)
    )

    k=cur.fetchone()


    if not k:
        await update.message.reply_text(
            "Invalid key"
        )
        return


    expire=(
        datetime.datetime.now()
        +
        datetime.timedelta(days=k[1])
    )


    cur.execute(
"""
UPDATE users
SET plan='PREMIUM', expires=?
WHERE user_id=?
""",
(
expire.isoformat(),
update.effective_user.id
)
)


    cur.execute(
        "UPDATE keys SET used=1 WHERE key=?",
        (key,)
    )


    db.commit()


    await update.message.reply_text(
        "🔥 Premium activated"
    )



# ---------------- RUN ----------------


app = Application.builder().token(BOT_TOKEN).build()


app.add_handler(
CommandHandler("start", start)
)

app.add_handler(
CommandHandler("lookup", zip_text)
)

app.add_handler(
CommandHandler("redeem", redeem)
)

app.add_handler(
CommandHandler("createkey", createkey)
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
photo_lookup
)
)


app.post_init = setup_commands


print("🔥 Premium bot running")

app.run_polling()
