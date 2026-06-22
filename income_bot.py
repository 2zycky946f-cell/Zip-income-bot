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
        "Send a picture with ZIP codes and I will find the income data."
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


        found = re.findall(r"\d{5}", text)


        print("FOUND ZIP CODES:")
        print(found)


        return list(dict.fromkeys(found))


    except Exception as e:

        print("OCR ERROR:")
        print(e)

        return []


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
            "No ZIP codes found. Try a clearer picture with larger numbers."
        )
        return


    results = []

    for z in zips:
        results.append(
            {
                "ZIP": z,
                "Median_Household_Income": get_income(z)
            }
        )


    df = pd.DataFrame(results)

    output = "/tmp/zip_results.xlsx"

    df.to_excel(
        output,
        index=False
    )


    with open(output, "rb") as f:

        await update.message.reply_document(
            document=f,
            filename="zip_results.xlsx"
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


print("Bot running")

app.run_polling()

app.run_polling()
