import os
import re
import sqlite3
import secrets
import datetime
import aiohttp
import easyocr

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
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)


TOKEN = os.getenv("BOT_TOKEN")
CENSUS_KEY = os.getenv("CENSUS_API_KEY")

ADMIN = 8834288282

BTC = "YOUR_BTC_ADDRESS"
USDT = "YOUR_USDT_ADDRESS"


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
CREATE TABLE IF NOT EXISTS keys(
key TEXT PRIMARY KEY,
days TEXT,
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


ocr = easyocr.Reader(["en"])



# ---------- HELPERS ----------

def user(uid):
    cur.execute(
        "INSERT OR IGNORE INTO users(id) VALUES(?)",
        (uid,)
    )
    db.commit()


async def income(zipcode):

    cur.execute(
        "SELECT * FROM cache WHERE zip=?",
        (zipcode,)
    )

    old = cur.fetchone()

    if old:
        return f"⚡ {zipcode}\nIncome: {old[1]}\nPopulation: {old[2]}"


    try:

        url = (
        "https://api.census.gov/data/2023/acs/acs5/profile?"
        "get=NAME,DP03_0062PE,DP05_0001E&"
        f"for=zip%20code%20tabulation%20area:{zipcode}"
        f"&key={CENSUS_KEY}"
        )

        async with aiohttp.ClientSession() as s:

            async with s.get(url,timeout=15) as r:

                data = await r.json()


        inc = data[1][1]
        pop = data[1][2]


        cur.execute(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            (zipcode,inc,pop)
        )

        db.commit()


        return f"📊 {zipcode}\nIncome: {inc}\nPopulation: {pop}"


    except:

        return f"❌ {zipcode} failed"



# ---------- START ----------

async def start(update,context):

    user(update.effective_user.id)


    keys = [
        [
            InlineKeyboardButton(
                "🔍 Lookup",
                callback_data="lookup"
            )
        ],
        [
            InlineKeyboardButton(
                "💎 Premium",
                callback_data="premium"
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
        "🔥 ZIP Income Bot",
        reply_markup=InlineKeyboardMarkup(keys)
    )



# ---------- ZIP TEXT ----------

async def zip_text(update,context):

    zips = re.findall(
        r"\b\d{5}\b",
        update.message.text
    )

    if not zips:
        return


    await update.message.reply_text(
        "🔍 Searching..."
    )


    out=[]

    for z in zips:
        out.append(
            await income(z)
        )


    await update.message.reply_text(
        "\n\n".join(out)
    )



# ---------- OCR ----------

async def photo(update,context):

    await update.message.reply_text(
        "📷 Reading image..."
    )


    f = await update.message.photo[-1].get_file()

    await f.download_to_drive("img.jpg")


    text = " ".join(
        x[1]
        for x in ocr.readtext("img.jpg")
    )


    zips = re.findall(
        r"\b\d{5}\b",
        text
    )


    if not zips:

        await update.message.reply_text(
            "❌ No ZIP found"
        )
        return


    result=[]

    for z in zips:
        result.append(
            await income(z)
        )


    await update.message.reply_text(
        "✅ Found:\n" +
        str(zips) +
        "\n\n" +
        "\n\n".join(result)
    )



# ---------- BUTTONS ----------

async def buttons(update,context):

    q = update.callback_query
    await q.answer()


    if q.data=="lookup":

        await q.edit_message_text(
"""
🔍 Send ZIP codes

Example:

93725
93291
93654

or upload screenshot 📷
"""
        )


    elif q.data=="premium":

        await q.edit_message_text(
"""
💎 Premium

⚡ 1 Day - $1.99
🔥 1 Week - $5.99
💎 1 Month - $14.99
👑 Lifetime - $49.99

Crypto only.

BTC:
%s

USDT:
%s
"""%(BTC,USDT)
        )


    elif q.data=="account":

        user(q.from_user.id)

        cur.execute(
            "SELECT * FROM users WHERE id=?",
            (q.from_user.id,)
        )

        u=cur.fetchone()


        await q.edit_message_text(
f"""
👤 Account

Plan:
{u[1]}

Searches:
{u[3]}

Expires:
{u[2] or "Never"}
"""
        )



# ---------- ADMIN ----------

async def createkey(update,context):

    if update.effective_user.id != ADMIN:
        return


    days=context.args[0]

    key=secrets.token_hex(8)


    cur.execute(
        "INSERT INTO keys VALUES(?,?,0)",
        (key,days)
    )

    db.commit()


    await update.message.reply_text(
        f"🔑 {key}\nPlan: {days}"
    )



async def givepremium(update,context):

    if update.effective_user.id != ADMIN:
        return


    uid=int(context.args[0])
    days=context.args[1]


    expire="LIFETIME" if days=="lifetime" else (
        datetime.datetime.now()
        +
        datetime.timedelta(days=int(days))
    ).isoformat()


    cur.execute(
        "UPDATE users SET plan='PREMIUM',expire=? WHERE id=?",
        (expire,uid)
    )

    db.commit()


    await update.message.reply_text(
        "✅ Premium added"
    )



async def menu(app):

    try:

        await app.bot.set_my_commands(
            [
                BotCommand("start","Start"),
                BotCommand("lookup","Lookup")
            ]
        )

        await app.bot.set_my_commands(
            [
                BotCommand("createkey","Create key"),
                BotCommand("givepremium","Give premium")
            ],
            scope=BotCommandScopeChat(
                chat_id=ADMIN
            )
        )

    except Exception as e:
        print(e)



# ---------- RUN ----------

app = Application.builder().token(TOKEN).build()


app.add_handler(CommandHandler("start",start))
app.add_handler(CommandHandler("createkey",createkey))
app.add_handler(CommandHandler("givepremium",givepremium))


app.add_handler(
MessageHandler(
filters.TEXT & ~filters.COMMAND,
zip_text
)
)


app.add_handler(
MessageHandler(
filters.PHOTO,
photo
)
)


app.add_handler(
CallbackQueryHandler(buttons)
)


app.post_init = menu


print("🔥 Bot running")

app.run_polling()
