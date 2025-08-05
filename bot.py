# bot.py
from flask import Flask, request
from dotenv import load_dotenv
import os
import logging

from telegram import Bot, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackContext
)

from sheet import (
    is_slot_available,
    save_booking,
    get_alternative_times,
    is_valid_date,
    is_weekend,
    get_available_slots,
    sheet
)

load_dotenv()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = Bot(token=TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot, None, workers=0)

# Conversation states
CHOOSING_OFFICER, GET_NAME, GET_PHONE, GET_EMAIL, GET_PURPOSE, GET_DATE, GET_TIME = range(7)

# Handlers
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Selamat datang ke Sistem Temu Janji Pejabat Daerah Keningau! \U0001F3DB\uFE0F\n"
        "Taip /book untuk menempah janji temu."
    )

def book(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Sila pilih pegawai yang ingin anda temui:\n"
        "1. Pegawai Daerah (DO)\n"
        "2. Penolong Pegawai Daerah (ADO)"
    )
    return CHOOSING_OFFICER

def choose_officer(update: Update, context: CallbackContext):
    choice = update.message.text.strip()
    if choice == "1":
        officer = "DO"
    elif choice == "2":
        officer = "ADO"
    else:
        update.message.reply_text("Sila pilih 1 atau 2.")
        return CHOOSING_OFFICER

    context.user_data["officer"] = officer
    update.message.reply_text("Masukkan nama penuh anda:")
    return GET_NAME

def get_name(update: Update, context: CallbackContext):
    context.user_data["name"] = update.message.text.strip()
    update.message.reply_text("Masukkan nombor telefon anda (cth: 0134567890):")
    return GET_PHONE

def get_phone(update: Update, context: CallbackContext):
    context.user_data["phone"] = update.message.text.strip()
    update.message.reply_text("Masukkan alamat emel anda:")
    return GET_EMAIL

def get_email(update: Update, context: CallbackContext):
    context.user_data["email"] = update.message.text.strip()
    update.message.reply_text("Nyatakan tujuan janji temu:")
    return GET_PURPOSE

def get_purpose(update: Update, context: CallbackContext):
    context.user_data["purpose"] = update.message.text.strip()
    update.message.reply_text("Masukkan tarikh pilihan (DD/MM/YYYY):")
    return GET_DATE

def get_date(update: Update, context: CallbackContext):
    date = update.message.text.strip()

    if not is_valid_date(date):
        update.message.reply_text(
            "\u26A0\uFE0F Tarikh yang dimasukkan tidak sah!\n"
            "Sila masukkan tarikh akan datang (DD/MM/YYYY)."
        )
        return GET_DATE

    if is_weekend(date):
        update.message.reply_text(
            "\u26D4 Tempahan tidak boleh dibuat pada hujung minggu.\n"
            "Sila pilih tarikh bekerja (Isnin-Jumaat):"
        )
        return GET_DATE

    available_slots = get_available_slots(date)
    if not available_slots:
        update.message.reply_text("\u26D4 Tiada slot tersedia pada tarikh ini. Sila cuba tarikh lain:")
        return GET_DATE

    context.user_data.update({"date": date, "available_slots": available_slots})
    keyboard = [[slot] for slot in available_slots]
    update.message.reply_text("\u231A Sila pilih masa temu janji:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return GET_TIME

def get_time(update: Update, context: CallbackContext):
    try:
        data = context.user_data
        chosen_time = update.message.text.strip()
        available_slots = data["available_slots"]
        date = data["date"]
        officer = data["officer"]
    except KeyError:
        update.message.reply_text("\u26A0\uFE0F Sesi dibatalkan. Sila cuba lagi dengan menaip /book", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if not is_slot_available(date, chosen_time, officer):
        records = sheet.get_all_records()
        booked_slots = [row['Time'] for row in records if row['Date'] == date and row['Officer'] == officer]
        alternatives = [slot for slot in available_slots if slot not in booked_slots]

        if alternatives:
            update.message.reply_text(f"\u26D4 Slot {chosen_time} sudah penuh. Pilih masa lain:", reply_markup=ReplyKeyboardMarkup([[slot] for slot in alternatives], one_time_keyboard=True))
            return GET_TIME
        else:
            update.message.reply_text("\u26D4 Semua slot sudah penuh. Sila cuba tarikh lain dengan /book", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

    save_booking(update.message.from_user.id, data["name"], data["phone"], data["email"], officer, data["purpose"], date, chosen_time)
    update.message.reply_text(f"\u2705 Tempahan berjaya!\nTarikh: {date}\nMasa: {chosen_time}\nPegawai: {officer}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Tempahan dibatalkan.")
    return ConversationHandler.END

# Register handlers
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("book", book)],
    states={
        CHOOSING_OFFICER: [MessageHandler(Filters.text & ~Filters.command, choose_officer)],
        GET_NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
        GET_PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
        GET_EMAIL: [MessageHandler(Filters.text & ~Filters.command, get_email)],
        GET_PURPOSE: [MessageHandler(Filters.text & ~Filters.command, get_purpose)],
        GET_DATE: [MessageHandler(Filters.text & ~Filters.command, get_date)],
        GET_TIME: [MessageHandler(Filters.text & ~Filters.command, get_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

# === Add handlers to dispatcher ===
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(conv_handler)

# === Webhook route ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok", 200

@app.route("/")
def index():
    return "Bot is live!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
