import os
import sqlite3
import datetime
import secrets

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)


BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 123456789  # PUT YOUR TELEGRAM ID HERE


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


db.commit()



# ---------------- USER FUNCTIONS ---------------- #


def create_user(user_id):

    cur.execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (user_id,)
    )

    if not cur.fetchone():

        cur.execute(
            "INSERT INTO users(user_id) VALUES(?)",
            (user_id,)
        )

        db.commit()



def get_user(user_id):

    create_user(user_id)

    cur.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,)
    )

    return cur.fetchone()



def is_premium(user_id):

    user = get_user(user_id)

    if not user[2]:
        return False


    return (
        datetime.datetime.fromisoformat(user[2])
        >
        datetime.datetime.now()
    )



# ---------------- START ---------------- #


async def start(update: Update, context):

    create_user(update.effective_user.id)


    buttons = [

        [
            InlineKeyboardButton(
                "🔑 Redeem Key",
                callback_data="redeem"
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
        """
🔥 Premium Income Bot

Welcome!

Use the buttons below:
""",
        reply_markup=InlineKeyboardMarkup(buttons)
    )



# ---------------- BUTTONS ---------------- #


async def buttons(update, context):

    q = update.callback_query

    await q.answer()


    if q.data == "account":

        user = get_user(q.from_user.id)

        await q.edit_message_text(
f"""
👤 Account

Plan:
{user[1]}

Searches:
{user[3]}

Expires:
{user[2] or "Never"}

Premium:
{"YES ✅" if is_premium(q.from_user.id) else "NO ❌"}
"""
        )


    elif q.data == "redeem":

        await q.edit_message_text(
"""
🔑 Redeem Key

Type:

/redeem YOUR_KEY
"""
        )


    elif q.data == "premium":

        await q.edit_message_text(
"""
💎 Premium Benefits

✅ More searches
✅ Faster access
✅ Premium tools
✅ Priority support
"""
        )



# ---------------- REDEEM ---------------- #


async def redeem(update, context):

    if not context.args:

        await update.message.reply_text(
            "Use:\n/redeem KEY"
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
            "❌ Key already used"
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



# ---------------- PREMIUM COMMAND ---------------- #


async def lookup(update, context):

    if not is_premium(update.effective_user.id):

        await update.message.reply_text(
            "❌ Premium only"
        )

        return


    user = get_user(update.effective_user.id)


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
🔍 Search Complete

Premium user:
YES

Search count:
{user[3]+1}
"""
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
🔑 New Premium Key

{key}

Days:
{days}
"""
    )



async def ban(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    uid = int(context.args[0])


    cur.execute(
"""
UPDATE users
SET banned=1
WHERE user_id=?
""",
(uid,)
)


    db.commit()


    await update.message.reply_text(
        "User banned"
    )



async def stats(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    cur.execute(
        "SELECT COUNT(*) FROM users"
    )

    users = cur.fetchone()[0]


    cur.execute(
        "SELECT COUNT(*) FROM keys"
    )

    keys = cur.fetchone()[0]


    await update.message.reply_text(
f"""
📊 Bot Stats

Users:
{users}

Keys:
{keys}
"""
    )



# ---------------- RUN ---------------- #


app = Application.builder().token(BOT_TOKEN).build()


app.add_handler(CommandHandler("start", start))

app.add_handler(CommandHandler("redeem", redeem))

app.add_handler(CommandHandler("lookup", lookup))

app.add_handler(CommandHandler("createkey", createkey))

app.add_handler(CommandHandler("ban", ban))

app.add_handler(CommandHandler("stats", stats))


app.add_handler(
    CallbackQueryHandler(buttons)
)



print("🔥 Premium Bot Running")

app.run_polling()
