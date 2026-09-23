import os
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Render Port Keep-Alive Server
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    server.serve_forever()

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MONGO_URI = os.environ.get("MONGO_URI", "YOUR_MONGO_URI_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# MongoDB Setup
client = MongoClient(MONGO_URI)
db = client["dollar_exchange_db"]
settings_col = db["settings"]
orders_col = db["orders"]

def get_rates():
    rates = settings_col.find_one({"_id": "exchange_rates"})
    if not rates:
        rates = {"_id": "exchange_rates", "buy_rate": 120.0, "sell_rate": 115.0}
        settings_col.insert_one(rates)
    return rates

# Custom Keyboard Layout
def get_main_keyboard(user_id):
    keyboard = [
        ["💵 BUY DOLLAR", "💰 SELL DOLLAR"],
        ["📋 MY ORDERS", "👤 MY PROFILE"],
        ["📊 Exchange Rates", "📞 Support"]
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# /start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    welcome_text = (
        f"👋 **Hello {update.effective_user.first_name}!**\n\n"
        "Welcome to **Dollar Exchange Bot**.\n"
        "Please select an option from the menu below:"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user_id)
    )

# Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    rates = get_rates()

    if text == "💵 BUY DOLLAR":
        msg = f"💵 **BUY DOLLAR**\n\nCurrent Buy Rate: **1 USD = {rates['buy_rate']} BDT**\n\nSend the amount you want to buy."
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "💰 SELL DOLLAR":
        msg = f"💰 **SELL DOLLAR**\n\nCurrent Sell Rate: **1 USD = {rates['sell_rate']} BDT**\n\nSend the amount you want to sell."
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "📋 MY ORDERS":
        await update.message.reply_text("📋 **MY ORDERS**\n\nYou have no active orders.", parse_mode="Markdown")

    elif text == "👤 MY PROFILE":
        profile_text = (
            f"👤 **MY PROFILE**\n\n"
            f"• **Name:** {update.effective_user.full_name}\n"
            f"• **User ID:** `{user_id}`\n"
            f"• **Username:** @{update.effective_user.username or 'N/A'}"
        )
        await update.message.reply_text(profile_text, parse_mode="Markdown")

    elif text == "📊 Exchange Rates":
        rates_text = (
            "📊 **Current Exchange Rates**\n\n"
            f"🟢 **Buy Rate:** 1 USD = **{rates['buy_rate']} BDT**\n"
            f"🔴 **Sell Rate:** 1 USD = **{rates['sell_rate']} BDT**"
        )
        await update.message.reply_text(rates_text, parse_mode="Markdown")

    elif text == "📞 Support":
        await update.message.reply_text("📞 For support contact Admin.")

    elif text == "⚙️ Admin Panel" and user_id == ADMIN_ID:
        admin_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Update Buy Rate", callback_data="update_buy")],
            [InlineKeyboardButton("Update Sell Rate", callback_data="update_sell")]
        ])
        await update.message.reply_text("⚙️ **Admin Control Panel**", reply_markup=admin_keyboard, parse_mode="Markdown")

def main():
    # Start Dummy Web Server in background thread for Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
