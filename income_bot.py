import os, re, sqlite3, secrets, datetime, aiohttp, easyocr

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
    filters
)


TOKEN = os.getenv("BOT_TOKEN")
CENSUS_KEY = os.getenv("CENSUS_API_KEY")

ADMIN = 8834288282

BTC = "bc1qeyfhgadc52lzecacafgh9n7hy84y2gfhd76evc"


# ---------- DATABASE ----------

db = sqlite3.connect(
    "bot.db",
    check_same_thread=False
)

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


cur.execute("""
CREATE TABLE IF NOT EXISTS payments(
user_id INTEGER,
plan TEXT,
status TEXT DEFAULT 'pending'
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



# ---------- HELPERS ----------

def add_user(uid):
    cur.execute(
        "INSERT OR IGNORE INTO users(id) VALUES(?)",
        (uid,)
    )
    db.commit()



async def lookup_zip(z):

    cur.execute(
        "SELECT * FROM cache WHERE zip=?",
        (z,)
    )

    old = cur.fetchone()

    if old:
        return f"⚡ {z}\nIncome: {old[1]}\nPopulation: {old[2]}"


    try:

        url = (
        "https://api.census.gov/data/2023/acs/acs5/profile?"
        "get=NAME,DP03_0062E,DP05_0001E&"
        f"for=zip%20code%20tabulation%20area:{z}"
        f"&key={CENSUS_KEY}"
        )


        async with aiohttp.ClientSession() as s:

            async with s.get(
                url,
                timeout=15
            ) as r:

                data = await r.json()


        income = data[1][1]
        pop = data[1][2]


        cur.execute(
            "INSERT OR REPLACE INTO cache VALUES(?,?,?)",
            (z,income,pop)
        )

        db.commit()


        return f"📊 {z}\nIncome: {income}\nPopulation: {pop}"


    except Exception as e:

        print(e)

        return f"❌ {z} failed"



# ---------- START ----------

async def start(update,context):

    add_user(update.effective_user.id)


    buttons = [
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
        reply_markup=InlineKeyboardMarkup(buttons)
    )



# ---------- TEXT ZIP ----------

async def text_zip(update,context):

    zips = re.findall(
        r"\b\d{5}\b",
        update.message.text
    )

    if not zips:
        return


    await update.message.reply_text(
        "🔍 Searching..."
    )


    result=[]

    for z in zips:
        result.append(
            await lookup_zip(z)
        )


    await update.message.reply_text(
        "\n\n".join(result)
    )



# ---------- IMAGE ----------

async def image(update,context):

    await update.message.reply_text(
        "📷 Reading image..."
    )

    try:
        file = await update.message.photo[-1].get_file()

        await file.download_to_drive("img.jpg")


        results = ocr.readtext("img.jpg")

        text = " ".join(
            item[1]
            for item in results
        )

        print("OCR TEXT:", text)


        zips = re.findall(
            r"\d{5}",
            text
        )


        if not zips:
            await update.message.reply_text(
                "❌ No ZIP found\n\nOCR saw:\n" + text[:200]
            )
            return


        await update.message.reply_text(
            f"✅ Found ZIP:\n{zips}\n\n🔍 Searching..."
        )


        output=[]

        for z in zips:
            output.append(
                await lookup_zip(z)
            )


        await update.message.reply_text(
            "\n\n".join(output)
        )


    except Exception as e:

        print("PHOTO ERROR:", e)

        await update.message.reply_text(
            "❌ Image failed"
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
f"""
💎 Premium Plans

⚡ 1 Day Pass - $1.99
🔥 1 Week Pass - $5.99
💎 1 Month Pass - $14.99
👑 Lifetime - $49.99


₿ Bitcoin Payment Only:

{BTC}


After payment type:
/paid
"""
        )


    elif q.data=="account":

        add_user(q.from_user.id)

        cur.execute(
            "SELECT * FROM users WHERE id=?",
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

Expires:
{u[2] or "Never"}
"""
        )



# ---------- PAYMENT ----------

async def paid(update,context):

    await update.message.reply_text(
"""
✅ Payment request sent.

Admin will verify your Bitcoin payment and send your key.
"""
    )



# ---------- ADMIN ----------

async def approve(update,context):

    if update.effective_user.id != ADMIN:
        return


    if len(context.args) < 2:

        await update.message.reply_text(
            "Use: /approve USER_ID DAYS"
        )

        return


    user_id = int(context.args[0])
    plan = context.args[1]


    key = secrets.token_hex(8)


    cur.execute(
        "INSERT INTO keys VALUES(?,?,0)",
        (key,plan)
    )


    expire = (
        "LIFETIME"
        if plan=="lifetime"
        else
        (
        datetime.datetime.now()
        +
        datetime.timedelta(days=int(plan))
        ).isoformat()
    )


    cur.execute(
        "UPDATE users SET plan='PREMIUM',expire=? WHERE id=?",
        (expire,user_id)
    )

    db.commit()


    await context.bot.send_message(
        chat_id=user_id,
        text=f"""
🔥 Payment Confirmed!

🔑 Key:
{key}

Plan:
{plan}
"""
    )


    await update.message.reply_text(
        "✅ Approved"
    )



async def createkey(update,context):

    if update.effective_user.id != ADMIN:
        return


    if not context.args:
        await update.message.reply_text(
            "Use: /createkey DAYS"
        )
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


    expire = (
        "LIFETIME"
        if days=="lifetime"
        else
        (
        datetime.datetime.now()
        +
        datetime.timedelta(days=int(days))
        ).isoformat()
    )


    cur.execute(
        "UPDATE users SET plan='PREMIUM',expire=? WHERE id=?",
        (expire,uid)
    )

    db.commit()


    await update.message.reply_text(
        "✅ Premium added"
    )



async def menu(app):

    await app.bot.set_my_commands(
        [
            BotCommand("start","Start"),
            BotCommand("paid","Payment sent"),
            BotCommand("lookup","Lookup")
        ]
    )



# ---------- RUN ----------

app = Application.builder().token(TOKEN).build()


app.add_handler(
CommandHandler("start",start)
)

app.add_handler(
CommandHandler("createkey",createkey)
)

app.add_handler(
CommandHandler("givepremium",givepremium)
)

app.add_handler(
CommandHandler("approve",approve)
)

app.add_handler(
CommandHandler("paid",paid)
)


app.add_handler(
MessageHandler(
filters.TEXT & ~filters.COMMAND,
text_zip
)
)


app.add_handler(
MessageHandler(
filters.PHOTO,
image
)
)


app.add_handler(
CallbackQueryHandler(buttons)
)


app.post_init = menu


print("🔥 Bot running")

app.run_polling()
