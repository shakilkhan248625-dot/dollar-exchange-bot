import os
import logging
from datetime import datetime
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

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Render Keep-Alive / Web Server
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dollar Exchange Web App</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; background: #0f172a; color: #fff; text-align: center; padding: 50px 20px; }
                .card { background: #1e293b; padding: 20px; border-radius: 12px; max-width: 400px; margin: auto; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
                h1 { color: #38bdf8; }
                p { font-size: 16px; color: #94a3b8; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Dollar Exchange Service</h1>
                <p>Bot Status: <strong>Active & Running 🟢</strong></p>
                <p>Use our Telegram Bot to Buy and Sell Dollars instantly!</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

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

# MongoDB Setup
client = MongoClient(MONGO_URI) if MONGO_URI else None
db = client["dollar_exchange_db"] if client else None
settings_col = db["settings"] if db is not None else None
orders_col = db["orders"] if db is not None else None

# States for Sell Flow
AMOUNT, RECEIVE_METHOD, ACCOUNT_NO, PAY_METHOD, PROOF = range(5)
# States for Buy Flow
BUY_AMOUNT, BUY_PAY_METHOD, BUY_CRYPTO_ADDR, BUY_PROOF = range(5, 9)
# States for Admin Flow
SET_SELL_RATE, SET_BUY_RATE, SET_METHOD_ADDRESS = range(9, 12)

# Default Payment Addresses & Numbers
DEFAULT_ADDRESSES = {
    "BINANCE": "Binance Pay ID: 123456789",
    "BYBIT": "Bybit UID: 987654321",
    "BITGET": "Bitget UID: 456789123",
    "BEP-20": "0x1234567890abcdef1234567890abcdef12345678",
    "TRC-20": "T1234567890abcdef1234567890abcdef",
    "USDT-SOLANA": "SolanaAddress1234567890abcdef1234567890",
    "BKASH": "01700000000 (Personal)",
    "NAGAD": "01800000000 (Personal)"
}

def get_settings():
    if settings_col is None:
        return {"buy_rate": 125.0, "sell_rate": 118.0, "addresses": DEFAULT_ADDRESSES}
    data = settings_col.find_one({"_id": "config"})
    if not data:
        data = {
            "_id": "config",
            "buy_rate": 125.0,
            "sell_rate": 118.0,
            "addresses": DEFAULT_ADDRESSES
        }
        settings_col.insert_one(data)
    return data

def update_setting(key, value):
    if settings_col is not None:
        settings_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# Main Menu Keyboard
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_keyboard(user_id))
    return ConversationHandler.END

# ----------------- SELL DOLLAR FLOW -----------------

async def sell_dollar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_settings()
    rate = settings.get("sell_rate", 118.0)
    
    text = (
        f"🔴 Current Sell Rate: 1 USD = {rate} BDT\n"
        "❗ (Minimum Order: 0.10$) ❗\n\n"
        "👉 Enter the amount of USD you want to sell:"
    )
    
    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return AMOUNT

async def process_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    try:
        amount = float(text)
        if amount < 0.10:
            await update.message.reply_text("⚠️ Minimum amount is 0.10$. Please try again:")
            return AMOUNT
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a valid number (e.g. 0.10, 5, 10):")
        return AMOUNT

    settings = get_settings()
    rate = settings.get("sell_rate", 118.0)
    total_bdt = amount * rate

    context.user_data['sell_amount'] = amount
    context.user_data['total_bdt'] = total_bdt
    
    keyboard = ReplyKeyboardMarkup([
        ["📱 bKash", "📱 Nagad"],
        ["🏦 Bank Transfer"],
        ["🔙 Cancel"]
    ], resize_keyboard=True)
    
    await update.message.reply_text(
        f"💰 You will receive: **{total_bdt:.2f} BDT**\n\n💳 Select your payment receive method:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return RECEIVE_METHOD

async def process_receive_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    context.user_data['receive_method'] = text
    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    await update.message.reply_text(
        f"📱 Enter your **{text}** account number to receive BDT:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return ACCOUNT_NO

async def process_account_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    context.user_data['account_no'] = text
    keyboard = ReplyKeyboardMarkup([
        ["BINANCE", "BYBIT"],
        ["BITGET", "BEP-20"],
        ["TRC-20", "USDT-SOLANA"],
        ["🔙 Cancel"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "🌐 Select the network/method you will send USD from:",
        reply_markup=keyboard
    )
    return PAY_METHOD

async def process_pay_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    context.user_data['pay_method'] = text
    settings = get_settings()
    addresses = settings.get("addresses", DEFAULT_ADDRESSES)
    address = addresses.get(text, "Address not set.")

    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    msg = (
        f"🚀 **Payment Address / ID ({text}):**\n\n"
        f"`{address}`\n\n"
        "*(👆 Click on address to copy)*\n\n"
        "📸 Send the payment screenshot after transferring USD:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
    return PROOF

async def process_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Cancel": return await cancel(update, context)
    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a valid payment screenshot image:")
        return PROOF

    photo_id = update.message.photo[-1].file_id
    user = update.effective_user
    settings = get_settings()
    rate = settings.get("sell_rate", 118.0)
    
    amount = context.user_data.get('sell_amount', 0)
    total_bdt = context.user_data.get('total_bdt', amount * rate)
    rec_method = context.user_data.get('receive_method', 'N/A')
    account_no = context.user_data.get('account_no', 'N/A')
    pay_method = context.user_data.get('pay_method', 'N/A')
    order_id = f"ORD-S-{int(datetime.now().timestamp())}"

    order_data = {
        "order_id": order_id,
        "user_id": user.id,
        "username": user.username,
        "type": "SELL",
        "amount_usd": amount,
        "rate": rate,
        "total_bdt": total_bdt,
        "receive_method": rec_method,
        "account_no": account_no,
        "pay_method": pay_method,
        "status": "Pending ⏳",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if orders_col is not None:
        orders_col.insert_one(order_data)

    user_receipt = (
        "✅ **SELL ORDER CREATED SUCCESSFULLY** ✅\n\n"
        f"🆔 **Order ID:** `{order_id}`\n"
        f"💵 **Sell Amount:** `{amount:.2f} USD`\n"
        f"💰 **You Receive:** `{total_bdt:.2f} BDT`\n"
        f"📱 **Receive Method:** `{rec_method}` ({account_no})\n\n"
        f"⏳ Processing time: 5-15 minutes. Thank you! ❤️"
    )
    await update.message.reply_text(user_receipt, parse_mode="Markdown", reply_markup=get_main_keyboard(user.id))

    if ADMIN_ID:
        admin_msg = (
            "🔔 **NEW DOLLAR SELL ORDER!**\n\n"
            f"🆔 **Order ID:** `{order_id}`\n"
            f"👤 **User:** {user.full_name} (@{user.username or 'N/A'})\n"
            f"🆔 **User ID:** `{user.id}`\n"
            f"💵 **Amount:** `{amount} USD` ({total_bdt:.2f} BDT)\n"
            f"📱 **Send BDT To:** {rec_method} -> `{account_no}`\n"
            f"🌐 **Received USD Via:** {pay_method}"
        )
        try:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=admin_msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to alert Admin: {e}")

    return ConversationHandler.END

# ----------------- BUY DOLLAR FLOW -----------------

async def buy_dollar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_settings()
    rate = settings.get("buy_rate", 125.0)
    
    text = (
        f"🟢 Current Buy Rate: 1 USD = {rate} BDT\n"
        "❗ (Minimum Order: 1.00$) ❗\n\n"
        "👉 Enter the amount of USD you want to buy:"
    )
    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    return BUY_AMOUNT

async def process_buy_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    try:
        amount = float(text)
        if amount < 1.0:
            await update.message.reply_text("⚠️ Minimum buy order is 1.00$. Try again:")
            return BUY_AMOUNT
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number:")
        return BUY_AMOUNT

    settings = get_settings()
    rate = settings.get("buy_rate", 125.0)
    total_bdt = amount * rate

    context.user_data['buy_amount'] = amount
    context.user_data['buy_total_bdt'] = total_bdt

    keyboard = ReplyKeyboardMarkup([
        ["📱 bKash Send Money", "📱 Nagad Send Money"],
        ["🔙 Cancel"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        f"💰 Total Cost: **{total_bdt:.2f} BDT**\n\n💳 Select your payment method:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return BUY_PAY_METHOD

async def process_buy_pay_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    context.user_data['buy_pay_method'] = text
    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)

    await update.message.reply_text(
        "🌐 Enter your **Wallet Address / Binance Pay ID / UID** where you want to receive USD:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return BUY_CRYPTO_ADDR

async def process_buy_crypto_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel": return await cancel(update, context)

    context.user_data['buy_crypto_addr'] = text
    pay_method = context.user_data.get('buy_pay_method', 'BKASH')
    total_bdt = context.user_data.get('buy_total_bdt', 0)
    
    settings = get_settings()
    addresses = settings.get("addresses", DEFAULT_ADDRESSES)
    method_key = "BKASH" if "bKash" in pay_method else "NAGAD"
    admin_no = addresses.get(method_key, "01700000000")

    keyboard = ReplyKeyboardMarkup([["🔙 Cancel"]], resize_keyboard=True)
    msg = (
        f"🚀 **Send `{total_bdt:.2f} BDT` to this {method_key} Number:**\n\n"
        f"`{admin_no}`\n\n"
        "*(👆 Click to copy number)*\n\n"
        "📸 Send payment screenshot or Transaction ID after sending BDT:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
    return BUY_PROOF

async def process_buy_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Cancel": return await cancel(update, context)
    
    photo_id = update.message.photo[-1].file_id if update.message.photo else None
    proof_text = update.message.text if update.message.text else "Image Provided"

    user = update.effective_user
    settings = get_settings()
    rate = settings.get("buy_rate", 125.0)

    amount = context.user_data.get('buy_amount', 0)
    total_bdt = context.user_data.get('buy_total_bdt', amount * rate)
    pay_method = context.user_data.get('buy_pay_method', 'N/A')
    crypto_addr = context.user_data.get('buy_crypto_addr', 'N/A')
    order_id = f"ORD-B-{int(datetime.now().timestamp())}"

    order_data = {
        "order_id": order_id,
        "user_id": user.id,
        "username": user.username,
        "type": "BUY",
        "amount_usd": amount,
        "rate": rate,
        "total_bdt": total_bdt,
        "pay_method": pay_method,
        "crypto_addr": crypto_addr,
        "status": "Pending ⏳",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    if orders_col is not None:
        orders_col.insert_one(order_data)

    await update.message.reply_text(
        f"✅ **BUY ORDER CREATED SUCCESSFULLY**\n\n🆔 **Order ID:** `{order_id}`\n💵 **Buying:** `{amount} USD`\n💰 **Paid:** `{total_bdt:.2f} BDT`\n📍 **Deliver To:** `{crypto_addr}`\n\n⏳ Order will be processed shortly!",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user.id)
    )

    if ADMIN_ID:
        admin_msg = (
            "🛒 **NEW DOLLAR BUY ORDER!**\n\n"
            f"🆔 **Order ID:** `{order_id}`\n"
            f"👤 **User:** {user.full_name} (@{user.username or 'N/A'})\n"
            f"💵 **Buying:** `{amount} USD` ({total_bdt:.2f} BDT)\n"
            f"📍 **Crypto/Pay Address:** `{crypto_addr}`\n"
            f"📝 **Proof:** {proof_text}"
        )
        try:
            if photo_id:
                await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=admin_msg, parse_mode="Markdown")
            else:
                await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Admin Alert Failed: {e}")

    return ConversationHandler.END

# ----------------- ADMIN PANEL HANDLERS -----------------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Update Sell Rate", callback_data="admin_set_sell_rate")],
        [InlineKeyboardButton("✏️ Update Buy Rate", callback_data="admin_set_buy_rate")],
        [InlineKeyboardButton("✏️ Update Payment Methods", callback_data="admin_update_address")]
    ])
    await update.message.reply_text("⚙️ **ADMIN CONTROL PANEL**", reply_markup=keyboard, parse_mode="Markdown")

async def admin_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "admin_set_sell_rate":
        await query.message.reply_text("🔢 Enter new **Sell Rate** (e.g. 118.5):")
        return SET_SELL_RATE
    elif query.data == "admin_set_buy_rate":
        await query.message.reply_text("🔢 Enter new **Buy Rate** (e.g. 126.0):")
        return SET_BUY_RATE
    elif query.data == "admin_update_address":
        methods = ["BINANCE", "BYBIT", "BITGET", "BEP-20", "TRC-20", "USDT-SOLANA", "BKASH", "NAGAD"]
        buttons = [[InlineKeyboardButton(m, callback_data=f"set_addr_{m}")] for m in methods]
        await query.message.reply_text("Select item to update:", reply_markup=InlineKeyboardMarkup(buttons))
        return SET_METHOD_ADDRESS

async def save_sell_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_rate = float(update.message.text)
        update_setting("sell_rate", new_rate)
        await update.message.reply_text(f"✅ Sell Rate updated to **{new_rate} BDT**", reply_markup=get_main_keyboard(update.effective_user.id))
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number.")
    return ConversationHandler.END

async def save_buy_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_rate = float(update.message.text)
        update_setting("buy_rate", new_rate)
        await update.message.reply_text(f"✅ Buy Rate updated to **{new_rate} BDT**", reply_markup=get_main_keyboard(update.effective_user.id))
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number.")
    return ConversationHandler.END

async def select_address_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("set_addr_", "")
    context.user_data['editing_method'] = method
    await query.message.reply_text(f"📝 Enter new address/number for **{method}**:")
    return SET_METHOD_ADDRESS

async def save_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = context.user_data.get('editing_method')
    new_address = update.message.text
    settings = get_settings()
    addresses = settings.get("addresses", DEFAULT_ADDRESSES)
    addresses[method] = new_address
    update_setting("addresses", addresses)

    await update.message.reply_text(f"✅ Address/Number for **{method}** updated successfully!", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END

# General Handlers
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_id = user.id
    settings = get_settings()

    if text == "📊 EXCHANGE RATES":
        rates_text = (
            "📊 **CURRENT EXCHANGE RATES**\n\n"
            f"🟢 **Buy Rate:** 1 USD = **{settings.get('buy_rate', 125.0)} BDT**\n"
            f"🔴 **Sell Rate:** 1 USD = **{settings.get('sell_rate', 118.0)} BDT**"
        )
        await update.message.reply_text(rates_text, parse_mode="Markdown")

    elif text == "📋 MY ORDERS":
        if orders_col is not None:
            user_orders = list(orders_col.find({"user_id": user_id}).sort("_id", -1).limit(5))
            if user_orders:
                msg = "📋 **YOUR RECENT ORDERS:**\n\n"
                for o in user_orders:
                    order_type = o.get('type', 'SELL')
                    msg += (
                        f"🆔 **ID:** `{o['order_id']}` ({order_type})\n"
                        f"💵 **Amount:** `{o['amount_usd']} USD` ({o['total_bdt']:.2f} BDT)\n"
                        f"📌 **Status:** {o['status']}\n"
                        f"📅 **Date:** {o['date']}\n\n"
                    )
                await update.message.reply_text(msg, parse_mode="Markdown")
                return
        await update.message.reply_text("📋 You have no active or previous orders.")

    elif text == "👤 MY PROFILE":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        profile_text = (
            f"👤 **MY PROFILE**\n\n"
            f"• **Name:** {user.full_name}\n"
            f"• **User ID:** `{user_id}`\n"
            f"• **Username:** @{user.username or 'N/A'}\n"
            f"• **Referral Link:** `{ref_link}`"
        )
        await update.message.reply_text(profile_text, parse_mode="Markdown")

    elif text == "⚙️ Admin Panel" and user_id == ADMIN_ID:
        await admin_panel(update, context)

def main():
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    # Handlers
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

    buy_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💵 BUY DOLLAR$"), buy_dollar_start)],
        states={
            BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy_amount)],
            BUY_PAY_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy_pay_method)],
            BUY_CRYPTO_ADDR: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buy_crypto_addr)],
            BUY_PROOF: [MessageHandler(filters.PHOTO | filters.TEXT, process_buy_proof)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🔙 Cancel$"), cancel)],
    )

    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_button_click, pattern="^admin_"),
            CallbackQueryHandler(select_address_method, pattern="^set_addr_")
        ],
        states={
            SET_SELL_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_sell_rate)],
            SET_BUY_RATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_buy_rate)],
            SET_METHOD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(sell_handler)
    app.add_handler(buy_handler)
    app.add_handler(admin_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
