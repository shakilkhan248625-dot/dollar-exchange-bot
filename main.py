import os
import logging
from telebot import TeleBot, types
from pymongo import MongoClient

# Logging setup
logging.basicConfig(level=logging.INFO)

# Configs
BOT_TOKEN = os.getenv("BOT_TOKEN", "8829432828:AAHJde41yaLlwf_XANZFlP0UIcZrx3CSEzs")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7753794493"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://shakilkhan248625_db_user:ZbtuKe0gXW5LYG3m@cluster0.hdjqc0o.mongodb.net/?appName=Cluster0")

bot = TeleBot(BOT_TOKEN)

# Database Connection
client = MongoClient(MONGO_URI)
db = client['DollarExchangeBot']
users_col = db['users']
orders_col = db['orders']
rates_col = db['rates']

# Default Rates Setup
if rates_col.count_documents({}) == 0:
    rates_col.insert_one({
        "_id": "rates",
        "buy_rate": 120.0,
        "sell_rate": 115.0,
        "bkash": "01700000000",
        "nagad": "01800000000",
        "binance_pay_id": "12345678"
    })

def get_user(user_id, username=""):
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "username": username,
            "balance_bdt": 0.0,
            "balance_usd": 0.0
        }
        users_col.insert_one(user)
    return user

# Main Keyboards
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("💵 Buy Dollar"),
        types.KeyboardButton("💰 Sell Dollar"),
        types.KeyboardButton("👤 My Profile"),
        types.KeyboardButton("📊 Exchange Rates"),
        types.KeyboardButton("📞 Support")
    )
    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("⚙️ Admin Panel"))
    return markup

# /start Command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_user(message.from_user.id, message.from_user.username)
    welcome_text = f"👋 Hello {message.from_user.first_name}!\n\nWelcome to Dollar Exchange Bot. You can easily buy and sell USD using bKash, Nagad, or Binance."
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu(message.from_user.id))

# Profile
@bot.message_handler(func=lambda message: message.text == "👤 My Profile")
def show_profile(message):
    user = get_user(message.from_user.id)
    text = f"👤 *Your Profile*\n\n" \
           f"🆔 User ID: `{user['user_id']}`\n" \
           f"💵 USD Balance: `${user['balance_usd']}`\n" \
           f"৳ BDT Balance: `{user['balance_bdt']} BDT`"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Exchange Rates
@bot.message_handler(func=lambda message: message.text == "📊 Exchange Rates")
def show_rates(message):
    rates = rates_col.find_one({"_id": "rates"})
    text = f"📊 *Current Exchange Rates*\n\n" \
           f"🟢 Buy Dollar: 1 USD = {rates['buy_rate']} BDT\n" \
           f"🔴 Sell Dollar: 1 USD = {rates['sell_rate']} BDT"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Admin Panel
@bot.message_handler(func=lambda message: message.text == "⚙️ Admin Panel")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Update Buy Rate", callback_data="admin_set_buy"),
        types.InlineKeyboardButton("Update Sell Rate", callback_data="admin_set_sell")
    )
    bot.send_message(message.chat.id, "⚙️ *Admin Control Panel*", parse_mode="Markdown", reply_markup=markup)

# Fallback Message Handler
@bot.message_handler(func=lambda message: True)
def handle_all(message):
    bot.send_message(message.chat.id, "Please use the menu buttons below.", reply_markup=main_menu(message.from_user.id))

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
