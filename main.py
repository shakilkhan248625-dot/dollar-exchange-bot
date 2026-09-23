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
    ConversationHandler,
    ContextTypes,
    filters,
)
from pymongo import MongoClient

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Render Port Keep-Alive Server
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is active!")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    server.serve_forever()

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")
ADMIN_ID_RAW = os.environ.get("ADMIN_ID", "0")
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() else 0

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# MongoDB Connection
client = MongoClient(MONGO_URI) if MONGO_URI else None
db = client["dollar_exchange_db"] if client else None
settings_col = db["settings"] if db is not None else None
orders_col = db["orders"] if db is not None else None

# Conversation States for Sell Dollar Flow
AMOUNT, RECEIVE_METHOD, ACCOUNT_NO, PAY_METHOD, PROOF = range(5)
# Conversation States for Admin Updating Payment Addresses
SET_BUY_RATE, SET_SELL_RATE, SET_METHOD_ADDRESS = range(5, 8)

# Default Payment Methods & Addresses
DEFAULT_PAY_ADDRESSES = {
    "BINANCE": "Binance Pay ID: 123456789",
    "BYBIT": "Bybit UID: 987654321",
    "BITGET": "Bitget UID: 456789123",
    "BEP-20": "0x1234567890abcdef1234567890abcdef12345678",
    "TRC-20": "T1234567890abcdef1234567890abcdef",
    "USDT-SOLANA": "SolanaAddress1234567890abcdef1234567890"
}

def get_settings():
    if settings_col is None:
        return {"buy_rate": 120.0, "sell_rate": 115.0, "addresses": DEFAULT_PAY_ADDRESSES}
    data = settings_col.find_one({"_id": "config"})
    if not data:
        data = {
            "_id": "config",
            "buy_rate": 120.0,
            "sell_rate": 115.0,
            "addresses": DEFAULT_PAY_ADDRESSES
        }
        settings_col.insert_one(data)
    return data

def update_setting(key, value):
    if settings_col is not None:
        settings_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# Main Keyboard Menu
def get_main_keyboard(user_id):
    keyboard = [
        ["💵 BUY DOLLAR", "💰 SELL DOLLAR"],
        ["📋 MY ORDERS", "👤 MY PROFILE"],
        ["📊 EXCHANGE RATES"]
    ]
    if ADMIN_ID and user_id == ADMIN_ID:
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
    return ConversationHandler.END

# Cancel / Back Action
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("❌ অপারেশন বাতিল করা হয়েছে।", reply_markup=get_main_keyboard(user_id))
    return ConversationHandler.END

# ----------------- SELL DOLLAR FLOW -----------------

async def sell_dollar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_settings()
    rate = settings.get("sell_rate", 115.0)
    
    text = (
        "💼 **ডলার বিক্রি সার্ভিস (SELL DOLLAR)** 💼\n\n"
        f"🔴 **বর্তমান সেল রেট:** ১ USD = `{rate}` BDT\n"
        "⚡ নিরাপদ ও দ্রুততম সময়ে আপনার পেমেন্ট পাওয়ার নিশ্চয়তা।\n"
        "🛡️ ১০০% বিশ্বস্ত ও নিরাপদ এক্সচেঞ্জ সুবিধা।\n"
        "⏰ পেমেন্ট সময়কাল: ৫ থেকে ১৫ মিনিট।\n\n"
        "👉 **আপনি কত ডলার সেল করতে চান তা নিচে লিখুন:**\n"
        "*(সর্বনিম্ন / Minimum 0.10$)*"
    )
    
    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return AMOUNT

async def process_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel":
        return await cancel(update, context)

    try:
        amount = float(text)
        if amount < 0.10:
            await update.message.reply_text("⚠️ সর্বনিম্ন 0.10$ সেল করতে পারবেন। আবার চেষ্টা করুন:")
            return AMOUNT
    except ValueError:
        await update.message.reply_text("⚠️ অনুগ্রহ করে সঠিক সংখ্যা লিখুন (যেমন: 5.0, 10, 0.50):")
        return AMOUNT

    context.user_data['sell_amount'] = amount
    
    keyboard = ReplyKeyboardMarkup([
        ["📱 bKash (বিকাশ)", "📱 Nagad (নগদ)"],
        ["🏦 Bank Transfer (ব্যাংক)"],
        ["🔙 Cancel"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        "💳 **টাকা গ্রহণ করার মাধ্যম নির্বাচন করুন:**\n\nআপনি কোন অ্যাকাউন্টে টাকা নিতে চান তা নির্বাচন করুন 👇",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return RECEIVE_METHOD

async def process_receive_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel":
        return await cancel(update, context)

    context.user_data['receive_method'] = text
    
    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    await update.message.reply_text(
        f"✅ আপনি **{text}** নির্বাচন করেছেন।\n\n"
        "📥 **পেমেন্ট রিসিভ করার জন্য আপনার নম্বর / অ্যাকাউন্ট ডিটেইলস লিখুন:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return ACCOUNT_NO

async def process_account_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel":
        return await cancel(update, context)

    context.user_data['account_no'] = text

    keyboard = ReplyKeyboardMarkup([
        ["BINANCE", "BYBIT"],
        ["BITGET", "BEP-20"],
        ["TRC-20", "USDT-SOLANA"],
        ["🔙 Cancel"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "🌐 **কোন মেথড / নেটওয়ার্কে ডলার পাঠাবেন তা নির্বাচন করুন:**",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return PAY_METHOD

async def process_pay_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel":
        return await cancel(update, context)

    context.user_data['pay_method'] = text
    settings = get_settings()
    addresses = settings.get("addresses", DEFAULT_PAY_ADDRESSES)
    address = addresses.get(text, "ঠিকানা দেওয়া হয়নি। এডমিনের সাথে যোগাযোগ করুন।")

    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    
    msg = (
        f"🚀 **পেমেন্ট এড্রেস / আইডি:**\n\n"
        f"আপনি **{text}** বেছে নিয়েছেন। নিচে দেওয়া এড্রেসে ডলার সেন্ড করুন:\n\n"
        f"`{address}`\n\n"
        "*(👆 এড্রেসের ওপর এক ক্লিকে ক্লিক করলেই কপি হয়ে যাবে)*\n\n"
        "📸 **ডলার পাঠানোর পর পেমেন্টের স্ক্রিনশট (Screenshot) প্রোভাইড করুন:**"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
    return PROOF

async def process_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Cancel":
        return await cancel(update, context)

    if not update.message.photo:
        await update.message.reply_text("⚠️ অনুগ্রহ করে ডলার পাঠানোর পেমেন্ট স্ক্রিনশটের ছবি (Photo) পাঠান:")
        return PROOF

    photo_id = update.message.photo[-1].file_id
    user = update.effective_user
    settings = get_settings()
    rate = settings.get("sell_rate", 115.0)
    
    amount = context.user_data.get('sell_amount', 0)
    total_bdt = amount * rate
    rec_method = context.user_data.get('receive_method', 'N/A')
    account_no = context.user_data.get('account_no', 'N/A')
    pay_method = context.user_data.get('pay_method', 'N/A')

    # Success receipt for user
    user_receipt = (
        "✅ **DOLLAR SELL ORDER CREATE SUCCESSFUL** ✅\n\n"
        f"💵 **সেল পরিমাণ:** `{amount:.2f} USD`\n"
        f"💵 **এক্সচেঞ্জ রেট:** `{rate} BDT`\n"
        f"💰 **আপনি রিসিভ করবেন:** `{total_bdt:.2f} BDT`\n"
        f"📱 **রিসিভ মেথড:** `{rec_method}`\n"
        f"🔢 **অ্যাকাউন্ট নম্বর:** `{account_no}`\n"
        f"🌐 **ডলার পাঠানোর নেটওয়ার্ক:** `{pay_method}`\n\n"
        "⏳ **দয়া করে কিছুক্ষণ অপেক্ষা করুন।**\n"
        f"আপনার পেমেন্ট ভেরিফাই প্রসেসিং হচ্ছে, কিছু মিনিটের মধ্যে আপনার একাউন্টে `{total_bdt:.2f} BDT` চলে যাবে। ❤️"
    )

    await update.message.reply_text(user_receipt, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))

    # Send Notification to Admin
    if ADMIN_ID:
        admin_msg = (
            "🔔 **NEW DOLLAR SELL ORDER RECEIVED!**\n\n"
            f"👤 **ইউজার:** {user.full_name} (@{user.username or 'N/A'})\n"
            f"🆔 **User ID:** `{user.id}`\n"
            f"💵 **পরিমাণ:** `{amount} USD` ({total_bdt:.2f} BDT)\n"
            f"📱 **মেথড & নম্বর:** {rec_method} -> `{account_no}`\n"
            f"🌐 **ডলার পাঠানোর নেটওয়ার্ক:** {pay_method}"
        )
        try:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=admin_msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to notify admin: {e}")

    return ConversationHandler.END

# ----------------- ADMIN PANEL HANDLERS -----------------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Set Sell Rate", callback_data="admin_set_sell_rate")],
        [InlineKeyboardButton("✏️ Update Pay Addresses", callback_data="admin_update_address")]
    ])
    await update.message.reply_text("⚙️ **ADMIN CONTROL PANEL**", reply_markup=keyboard, parse_mode="Markdown")

async def admin_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "admin_set_sell_rate":
        await query.message.reply_text("🔢 নতুন **Sell Rate** টাইপ করুন (যেমন: 118.5):")
        return SET_SELL_RATE
    elif query.data == "admin_update_address":
        methods = ["BINANCE", "BYBIT", "BITGET", "BEP-20", "TRC-20", "USDT-SOLANA"]
        buttons = [[InlineKeyboardButton(m, callback_data=f"set_addr_{m}")] for m in methods]
        await query.message.reply_text("যেটির এড্রেস/আইডি পরিবর্তন করতে চান তা নির্বাচন করুন:", reply_markup=InlineKeyboardMarkup(buttons))
        return SET_METHOD_ADDRESS

async def save_sell_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_rate = float(update.message.text)
        update_setting("sell_rate", new_rate)
        await update.message.reply_text(f"✅ Sell Rate পরিবর্তন করে **{new_rate} BDT** করা হয়েছে।", reply_markup=get_main_keyboard(update.effective_user.id))
    except ValueError:
        await update.message.reply_text("⚠️ সঠিক সংখ্যা দিন।")
    return ConversationHandler.END

async def select_address_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("set_addr_", "")
    context.user_data['editing_method'] = method
    await query.message.reply_text(f"📝 **{method}** এর জন্য নতুন এড্রেস/আইডি লিখুন:")
    return SET_METHOD_ADDRESS

async def save_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = context.user_data.get('editing_method')
    new_address = update.message.text
    settings = get_settings()
    addresses = settings.get("addresses", DEFAULT_PAY_ADDRESSES)
    addresses[method] = new_address
    update_setting("addresses", addresses)

    await update.message.reply_text(f"✅ **{method}** এর এড্রেস সফলভাবে আপডেট করা হয়েছে!", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END

# General Handlers
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    settings = get_settings()

    if text == "📊 EXCHANGE RATES":
        rates_text = (
            "📊 **CURRENT EXCHANGE RATES**\n\n"
            f"🟢 **Buy Rate:** 1 USD = **{settings.get('buy_rate', 120.0)} BDT**\n"
            f"🔴 **Sell Rate:** 1 USD = **{settings.get('sell_rate', 115.0)} BDT**"
        )
        await update.message.reply_text(rates_text, parse_mode="Markdown")

    elif text == "👤 MY PROFILE":
        profile_text = (
            f"👤 **MY PROFILE**\n\n"
            f"• **Name:** {update.effective_user.full_name}\n"
            f"• **User ID:** `{user_id}`\n"
            f"• **Username:** @{update.effective_user.username or 'N/A'}"
        )
        await update.message.reply_text(profile_text, parse_mode="Markdown")

    elif text == "⚙️ Admin Panel" and user_id == ADMIN_ID:
        await admin_panel(update, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    # Sell Dollar Conversation Handler
    sell_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 SELL DOLLAR$"), sell_dollar_start)],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_amount)],
            RECEIVE_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_receive_method)],
            ACCOUNT_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_account_no)],
            PAY_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pay_method)],
            PROOF: [MessageHandler(filters.PHOTO | filters.TEXT, process_proof)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🔙 Cancel$"), cancel)],
    )

    # Admin Settings Conversation Handler
    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_button_click, pattern="^admin_"),
            CallbackQueryHandler(select_address_method, pattern="^set_addr_")
        ],
        states={
            SET_SELL_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_sell_rate)],
            SET_METHOD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(sell_handler)
    app.add_handler(admin_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
