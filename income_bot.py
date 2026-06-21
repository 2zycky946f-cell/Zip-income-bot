import os
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
"📊 ZipIncome Bot\n\n"
“Upload a CSV or XLSX file containing a column named ZIP.\n\n”
“Example:\n”
“ZIP\n”
“93618\n”
“93722\n”
“90210”
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
    response = requests.get(url, timeout=15)
    if response.status_code != 200:
        return None
    data = response.json()
    if len(data) > 1:
        return int(data[1][0])
except Exception:
    pass
return None

async def process_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
document = update.message.document

if not document:
    return
file_name = document.file_name.lower()
if not (
    file_name.endswith(".csv")
    or file_name.endswith(".xlsx")
):
    await update.message.reply_text(
        "Please upload a CSV or XLSX file."
    )
    return
await update.message.reply_text(
    "Processing file... please wait."
)
telegram_file = await context.bot.get_file(
    document.file_id
)
input_path = f"/tmp/{document.file_name}"
await telegram_file.download_to_drive(input_path)
try:
    if file_name.endswith(".csv"):
        df = pd.read_csv(input_path)
    else:
        df = pd.read_excel(input_path)
    if "ZIP" not in df.columns:
        await update.message.reply_text(
            "Your file must contain a column named ZIP."
        )
        return
    incomes = []
    for zip_code in df["ZIP"]:
        income = get_income(zip_code)
        incomes.append(income)
    df["Median_Household_Income"] = incomes
    output_path = "/tmp/zip_income_results.xlsx"
    df.to_excel(output_path, index=False)
    with open(output_path, "rb") as result_file:
        await update.message.reply_document(
            document=result_file,
            filename="zip_income_results.xlsx",
            caption="Finished processing ZIP income data."
        )
except Exception as e:
    await update.message.reply_text(
        f"Error processing file: {str(e)}"
    )

app = Application.builder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler(“start”, start))
app.add_handler(
MessageHandler(
filters.Document.ALL,
process_file
)
)

print(“ZipIncome Bot running…”)
app.run_polling()
