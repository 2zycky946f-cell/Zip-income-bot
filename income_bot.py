import os
import re
import requests
import pandas as pd

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ZipIncome Bot\n\n"
        "Send:\n"
        "- ZIP codes as text\n"
        "- A picture with ZIP codes\n"
        "- CSV/XLSX files"
    )


def get_income(zip_code):

    try:
        url = (
            "https://api.census.gov/data/2023/acs/acs5"
            f"?get=B19013_001E"
            f"&for=zip%20code%20tabulation%20area:{zip_code}"
            f"&key={CENSUS_API_KEY}"
        )

        response = requests.get(url, timeout=15)
        data = response.json()

        if len(data) > 1:
            return int(data[1][0])

    except Exception:
        return None

    return None


def make_excel(zips):

    results = []

    for z in zips:
        results.append(
            {
                "ZIP": z,
                "Median_Household_Income": get_income(z)
            }
        )

    df = pd.DataFrame(results)

    path = "/tmp/zip_income_results.xlsx"

    df.to_excel(path, index=False)

    return path


def read_zips(image_path):

    try:

        url = "https://api.ocr.space/parse/image"

        with open(image_path, "rb") as image:

            response = requests.post(
                url,
                files={"filename": image},
                data={
                    "language": "eng",
                    "isOverlayRequired": False,
                    "scale": True
                },
                timeout=30
            )


        data = response.json()

        text = ""

        for item in data.get("ParsedResults", []):
            text += item.get("ParsedText", "") + "\n"


        print("OCR TEXT:")
        print(repr(text))


        zips = re.findall(r"\d{5}", text)

        return list(dict.fromkeys(zips))


    except Exception as e:

        print(e)

        return []


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    zips = re.findall(r"\d{5}", text)

    if not zips:

        await update.message.reply_text(
            "No ZIP codes found.\nExample: 93618 93722 90210"
        )

        return


    zips = list(dict.fromkeys(zips))

    await update.message.reply_text(
        "Processing..."
    )


    output = make_excel(zips)


    with open(output, "rb") as f:

        await update.message.reply_document(
            document=f,
            filename="zip_income_results.xlsx"
        )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Reading image..."
    )


    photo = update.message.photo[-1]

    file = await context.bot.get_file(
        photo.file_id
    )


    image_path = "/tmp/photo.jpg"

    await file.download_to_drive(image_path)


    zips = read_zips(image_path)


    if not zips:

        await update.message.reply_text(
            "No ZIP codes found. Try a clearer picture."
        )

        return


    output = make_excel(zips)


    with open(output, "rb") as f:

        await update.message.reply_document(
            document=f,
            filename="zip_income_results.xlsx"
        )


async def file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    document = update.message.document

    file_name = document.file_name.lower()


    if not (
        file_name.endswith(".csv")
        or file_name.endswith(".xlsx")
    ):

        await update.message.reply_text(
            "Upload CSV or XLSX files only."
        )

        return


    telegram_file = await context.bot.get_file(
        document.file_id
    )


    path = f"/tmp/{document.file_name}"

    await telegram_file.download_to_drive(path)


    if file_name.endswith(".csv"):
        df = pd.read_csv(path)

    else:
        df = pd.read_excel(path)


    if "ZIP" not in df.columns:

        await update.message.reply_text(
            "File needs a ZIP column."
        )

        return


    zips = df["ZIP"].astype(str).tolist()

    output = make_excel(zips)


    with open(output, "rb") as f:

        await update.message.reply_document(
            document=f,
            filename="zip_income_results.xlsx"
        )


app = Application.builder().token(BOT_TOKEN).build()


app.add_handler(
    CommandHandler(
        "start",
        start
    )
)


app.add_handler(
    MessageHandler(
        filters.PHOTO,
        photo_handler
    )
)


app.add_handler(
    MessageHandler(
        filters.Document.ALL,
        file_handler
    )
)


app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        text_handler
    )
)


print("Bot running")

app.run_polling()
