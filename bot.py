# bot.py
from dotenv import load_dotenv
import os
load_dotenv()

from telegram import Update
from keep_alive import keep_alive

from sheet import (
    is_slot_available,
    save_booking,
    get_alternative_times,
    is_valid_date,
    is_weekend,
    get_available_slots,
    sheet  
)

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove  
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

# Conversation states
CHOOSING_OFFICER, GET_NAME, GET_PHONE, GET_EMAIL, GET_PURPOSE, GET_DATE, GET_TIME = range(7)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Selamat datang ke Sistem Temu Janji Pejabat Daerah Keningau! 🏛️\n"
        "Taip /book untuk menempah janji temu."
    )

# /book
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Sila pilih pegawai yang ingin anda temui:\n"
        "1. Pegawai Daerah (DO)\n"
        "2. Penolong Pegawai Daerah (ADO)"
    )
    return CHOOSING_OFFICER

# Officer selection
async def choose_officer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    if choice == "1":
        officer = "DO"
    elif choice == "2":
        officer = "ADO"
    else:
        await update.message.reply_text("Sila pilih 1 atau 2.")
        return CHOOSING_OFFICER

    context.user_data["officer"] = officer
    await update.message.reply_text("Masukkan nama penuh anda:")
    return GET_NAME

# Name
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Masukkan nombor telefon anda (cth: 0134567890):")
    return GET_PHONE

# Phone
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("Masukkan alamat emel anda:")
    return GET_EMAIL

# Email
async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text("Nyatakan tujuan janji temu:")
    return GET_PURPOSE

# Purpose
async def get_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["purpose"] = update.message.text.strip()
    await update.message.reply_text("Masukkan tarikh pilihan (DD/MM/YYYY):")
    return GET_DATE

# Date
async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text.strip()
    
    # Validate date format and future date
    if not is_valid_date(date):
        await update.message.reply_text(
            "⚠️ Tarikh yang dimasukkan tidak sah!\n"
            "Sila masukkan tarikh akan datang (DD/MM/YYYY).\n"
        )
        return GET_DATE

    # Validate not weekend
    if is_weekend(date):
        await update.message.reply_text(
            "⛔ Tempahan tidak boleh dibuat pada hujung minggu.\n"
            "Sila pilih tarikh bekerja (Isnin-Jumaat):"
        )
        return GET_DATE

    # Get available slots
    available_slots = get_available_slots(date)
    if not available_slots:
        await update.message.reply_text(
            "⛔ Tiada slot tersedia pada tarikh ini.\n"
            "Sila cuba tarikh lain:"
        )
        return GET_DATE

    # Store all necessary data
    context.user_data.update({
        "date": date,
        "available_slots": available_slots
    })

    # Show time slot buttons
    keyboard = [[slot] for slot in available_slots]
    await update.message.reply_text(
        "⌚ Sila pilih masa temu janji:",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return GET_TIME

async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = context.user_data
        chosen_time = update.message.text.strip()
        available_slots = data["available_slots"]
        date = data["date"]
        officer = data["officer"]
    except KeyError:
        await update.message.reply_text(
            "⚠️ Sesi dibatalkan. Sila cuba lagi dengan menaip /book",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    # Check slot availability
    if not is_slot_available(date, chosen_time, officer):
        # Get booked slots from the sheet
        records = sheet.get_all_records()  
        booked_slots = [row['Time'] for row in records 
                       if row['Date'] == date and row['Officer'] == officer]
        
        alternatives = [slot for slot in available_slots if slot not in booked_slots]
        
        if alternatives:
            await update.message.reply_text(
                f"⛔Slot {chosen_time} sudah penuh. Pilih masa lain:",
                reply_markup=ReplyKeyboardMarkup(
                    [[slot] for slot in alternatives],
                    one_time_keyboard=True
                )
            )
            return GET_TIME
        else:
            await update.message.reply_text(
                "⛔ Semua slot sudah penuh. Sila cuba tarikh lain dengan /book",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    # Complete booking
    save_booking(
        user_id=update.message.from_user.id,
        name=data["name"],
        phone=data["phone"],
        email=data["email"],
        officer=officer,
        purpose=data["purpose"],
        date=date,
        time=chosen_time
    )

    await update.message.reply_text(
        f"✅ Tempahan berjaya!\n"
        f"Tarikh: {date}\n"
        f"Masa: {chosen_time}\n"
        f"Pegawai: {officer}",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# /cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tempahan dibatalkan.")
    return ConversationHandler.END

# Main
def main():

    import os
    app = ApplicationBuilder().token(os.environ['TELEGRAM_BOT_TOKEN']).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("book", book)],
        states={
            CHOOSING_OFFICER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_officer)],
            GET_NAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_PHONE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            GET_EMAIL:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            GET_PURPOSE:     [MessageHandler(filters.TEXT & ~filters.COMMAND, get_purpose)],
            GET_DATE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            GET_TIME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("Bot is running... Press Ctrl+C to stop.")
    keep_alive()
    app.run_polling()

if __name__ == "__main__":
    main()

