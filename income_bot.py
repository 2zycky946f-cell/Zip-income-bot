import os
import sqlite3
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 123456789  # put your Telegram ID here


# ---------------- DATABASE ---------------- #

db = sqlite3.connect("bot.db", check_same_thread=False)
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


# ---------------- USER SYSTEM ---------------- #

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



def premium(user_id):

    user = get_user(user_id)

    if user[2]:

        expire = datetime.datetime.fromisoformat(user[2])

        if expire > datetime.datetime.now():
            return True

    return False



# ---------------- START ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    create_user(user.id)

    keyboard = [
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
    ]

    await update.message.reply_text(
        "🔥 Premium Income Bot\n\n"
        "Access your tools below:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )



# ---------------- ACCOUNT ---------------- #

async def account(update, context):

    q = update.callback_query
    await q.answer()

    user = get_user(q.from_user.id)

    await q.edit_message_text(
        f"""
👤 Account

Plan: {user[1]}
Searches: {user[3]}

Expires:
{user[2] or 'Never'}

Premium:
{"YES ✅" if premium(q.from_user.id) else "NO ❌"}
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
        "✅ Premium activated!"
    )



# ---------------- ADMIN ---------------- #

async def createkey(update, context):

    if update.effective_user.id != ADMIN_ID:
        return


    days = int(context.args[0])

    import secrets

    key = secrets.token_hex(8)


    cur.execute(
        "INSERT INTO keys(key,days) VALUES(?,?)",
        (key,days)
    )

    db.commit()


    await update.message.reply_text(
        f"🔑 New Key:\n\n{key}\n\nExpires after {days} days"
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

Users: {users}
Keys Created: {keys}
"""
    )



# ---------------- RUN ---------------- #

app = Application.builder().token(BOT_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("createkey", createkey))
app.add_handler(CommandHandler("stats", stats))


app.add_handler(
    CallbackQueryHandler(account, pattern="account")
)


print("Premium bot running")

app.run_polling()
