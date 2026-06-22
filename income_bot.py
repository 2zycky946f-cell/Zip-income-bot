import os
import re
import requests

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
        "Send ZIP codes like:\n"
        "93618 93722 90210"
    )


def get_income(zip_code):

    try:

        zip_code = str(zip_code).strip().zfill(5)

        url = (
            "https://api.census.gov/data/2023/acs/acs5"
            f"?get=B19013_001E"
            f"&for=zip%20code%20tabulation%20area:{zip_code}"
            f"&key={CENSUS_API_KEY}"
        )


        response = requests.get(
            url,
            timeout=15
        )


        print("CENSUS RESPONSE:")
        print(response.text)


        data = response.json()


        if len(data) > 1:
            return int(data[1][0])


    except Exception as e:

        print("INCOME ERROR:")
        print(e)


    return "Not found"



def make_message(zips):


    results = []


    for z in zips:

        income = get_income(z)

        results.append(
            {
                "zip": z,
                "income": income
            }
        )


    results.sort(
        key=lambda x: x["income"]
        if isinstance(x["income"], int)
        else 0,
        reverse=True
    )


    message = "ZIP Income Results:\n\n"


    for item in results:

        if item["income"] == "Not found":

            message += (
                f"{item['zip']}: Not found\n"
            )

        else:

            message += (
                f"{item['zip']}: "
                f"${item['income']:,}\n"
            )


    return message



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

            text += (
                item.get("ParsedText", "")
                + "\n"
            )


        print("OCR TEXT:")
        print(text)


        zips = re.findall(
            r"\d{5}",
            text
        )


        return list(dict.fromkeys(zips))


    except Exception as e:

        print("OCR ERROR:")
        print(e)

        return []



async def text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text


    zips = re.findall(
        r"\d{5}",
        text
    )


    if not zips:

        await update.message.reply_text(
            "No ZIP codes found."
        )

        return



    zips = list(dict.fromkeys(zips))


    await update.message.reply_text(
        "Checking incomes..."
    )


    message = make_message(zips)


    await update.message.reply_text(
        message
    )



async def photo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "Reading image..."
    )


    photo = update.message.photo[-1]


    file = await context.bot.get_file(
        photo.file_id
    )


    image_path = "/tmp/photo.jpg"


    await file.download_to_drive(
        image_path
    )


    zips = read_zips(
        image_path
    )


    if not zips:

        await update.message.reply_text(
            "No ZIP codes found in image."
        )

        return


    message = make_message(
        zips
    )


    await update.message.reply_text(
        message
    )



app = Application.builder().token(
    BOT_TOKEN
).build()



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
        filters.TEXT & ~filters.COMMAND,
        text_handler
    )
)



print("ZipIncome Bot running")


app.run_polling()
