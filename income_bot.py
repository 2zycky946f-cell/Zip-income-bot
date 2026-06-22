import os
import sqlite3
import datetime
import secrets
import aiohttp

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
    ContextTypes
)


BOT_TOKEN = os.getenv("BOT_TOKEN")
CENSUS_API_KEY = os.getenv("CENSUS_API_KEY")

ADMIN_ID = 8834288282


# ---------------- DATABASE ---------------- #

db = sqlite3.connect(
    "premium_bot.db",
    check_same_thread=False
)

cur = db.cursor()


cur.execute("""
CREATE TABLE IF NOT EXISTS users(
user_id INTEGER PRIMARY KEY,
plan TEXT DEFAULT 'FREE',
expires TEXT,
searches INTEGER DEFAULT 0,
banned INTEGER DEFAULT 0
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
CREATE TABLE IF NOT EXISTS zip_cache(
zip TEXT PRIMARY KEY,
income TEXT,
population TEXT,
saved TEXT
)
""")


db.commit()



# ---------------- SAFE COMMAND MENU ---------------- #

async def set_commands(app):

    users = [
        BotCommand("start", "Start bot"),
        BotCommand("lookup", "Lookup ZIP income"),
        BotCommand("redeem", "Redeem key"),
    ]


    admin = [
        BotCommand("start", "Start bot"),
        BotCommand("lookup", "Lookup ZIP income"),
        BotCommand("redeem", "Redeem key"),
        BotCommand("createkey", "Create key"),
        BotCommand("stats", "View stats"),
        BotCommand("ban", "Ban user"),
    ]


    try:

        await app.bot.set_my_commands(users)


        await app.bot.set_my_commands(
            admin,
            scope=BotCommandScopeChat(
                chat_id=ADMIN_ID
            )
        )


        print("✅ Command menu loaded")


    except Exception as e:

        print(
            "⚠️ Command menu failed but bot continues:",
            e
        )



# ---------------- USERS ---------------- #

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



# ---------------- START ---------------- #

async def start(update, context):

    create_user(update.effective_user.id)


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
        ],

        [
            InlineKeyboardButton(
                "💎 Premium",
                callback_data="premium"
            )
        ]

    ]


    await update.message.reply_text(
        "🔥 Premium Income Bot\nChoose:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )



# ---------------- LOOKUP ---------------- #

async def lookup(update, context):

    if not context.args:

        await update.message.reply_text(
            "Use:\n/lookup ZIP"
        )
        return


    zipcode = context.args[0]


    # cache check

    cur.execute(
        "SELECT * FROM zip_cache WHERE zip=?",
        (zipcode,)
    )

    cached = cur.fetchone()


    if cached:

        await update.message.reply_text(
f"""
⚡ FAST RESULT

ZIP:
{zipcode}

Income:
{cached[1]}

Population:
{cached[2]}

Saved:
{cached[3]}
"""
        )

        return



    await update.message.reply_text(
        "🔍 Searching..."
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
            ) as response:

                data = await response.json()



        income = data[1][1]
        population = data[1][2]



        cur.execute(
"""
INSERT INTO zip_cache
(zip,income,population,saved)
VALUES(?,?,?,?)
""",
(
zipcode,
income,
population,
datetime.datetime.now().strftime("%Y-%m-%d")
)
)


        cur.execute(
"""
UPDATE users
SET searches=searches+1
WHERE user_id=?
""",
(update.effective_user.id,)
)


        db.commit()



        await update.message.reply_text(
f"""
📊 ZIP REPORT

ZIP:
{zipcode}

Income:
{income}

Population:
{population}

✅ Saved for instant future searches
"""
        )



    except Exception as e:

        print("LOOKUP ERROR:", e)


        await update.message.reply_text(
            "⚠️ Census failed. Try again later."
        )



# ---------------- REDEEM ---------------- #

async def redeem(update, context):

    if not context.args:

        await update.message.reply_text(
            "Use /redeem KEY"
        )

        return


    key = context.args[0]


    cur.execute(
        "SELECT * FROM keys WHERE key=?",
        (key,)
    )

    data = cur.fetchone()


    if not data:

        await update.message.reply_text(
            "❌ Invalid key"
        )
        return


    if data[2]:

        await update.message.reply_text(
            "❌ Used key"
        )
        return



    expire = (
        datetime.datetime.now()
        +
        datetime.timedelta(days=data[1])
    )


    cur.execute(
"""
UPDATE users
SET plan='PREMIUM',
expires=?
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
        "🔥 Premium activated!"
    )



# ---------------- BUTTONS ---------------- #

async def buttons(update, context):

    q = update.callback_query
    await q.answer()


    if q.data == "account":

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


    elif q.data == "lookup":

        await q.edit_message_text(
            "Use:\n/lookup ZIP"
        )


    elif q.data == "premium":

        await q.edit_message_text(
            "💎 Premium = faster access + extra features"
        )



# ---------------- ADMIN ---------------- #

async def createkey(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    days = int(context.args[0])

    key = secrets.token_hex(10)


    cur.execute(
        "INSERT INTO keys(key,days) VALUES(?,?)",
        (key,days)
    )

    db.commit()


    await update.message.reply_text(
f"""
🔑 KEY

{key}

Days:
{days}
"""
    )



async def stats(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    cur.execute(
        "SELECT COUNT(*) FROM users"
    )

    users = cur.fetchone()[0]


    await update.message.reply_text(
        f"📊 Users: {users}"
    )



# ---------------- RUN ---------------- #

app = Application.builder().token(BOT_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("lookup", lookup))
app.add_handler(CommandHandler("redeem", redeem))

app.add_handler(CommandHandler("createkey", createkey))
app.add_handler(CommandHandler("stats", stats))

app.add_handler(
    CallbackQueryHandler(buttons)
)


app.post_init = set_commands


print("🔥 Premium bot running")


app.run_polling()
