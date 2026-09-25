# ============================================================
# Binance Pay Bot - البحث عن معاملة برقم Order ID
# ============================================================

import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============================================================
# ضع مفاتيحك هنا
# ============================================================

API_KEY = (
    'WFHIGs8VvN4IXWOIMJBRAjRVGYviS5005UNQJbOvP5t5mOeoZDtuQAeRByRTxfu8'
)

API_SECRET = (
    'FGKMYgMc9iI3VL1z6UhEzm1aGAk68aLMO3WxLapyhPnTrP6GjWeuahpXaE5LhKUs'
)

TELEGRAM_TOKEN =('8911308822:AAGeFsK8GTFP2f35vrKlGszP2-w_YGUFMGw'
)

BASE_URL = "https://api.binance.com"

# ============================================================
# إنشاء Signature
# ============================================================

def create_signature(params):
    query_string = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return query_string, signature

# ============================================================
# البحث عن معاملة باستخدام Order ID
# ============================================================

def find_transaction_by_order_id(order_id):
    order_id = str(order_id).strip()

    if not order_id:
        return None, "Order ID فارغ"

    params = {
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000,
        "limit": 100
    }

    query_string, signature = create_signature(params)

    url = (
        BASE_URL
        + "/sapi/v1/pay/transactions?"
        + query_string
        + "&signature="
        + signature
    )

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(url, headers=headers, timeout=20)
        result = response.json()

        if not result.get("success"):
            error_msg = result.get("message", result.get("msg", "خطأ غير معروف"))
            return None, f"Binance: {error_msg}"

        transactions = result.get("data", [])

        for transaction in transactions:
            transaction_order_id = str(transaction.get("orderId", "")).strip()
            if transaction_order_id == order_id:
                return transaction, None

        return None, "لم يتم العثور على المعاملة"

    except Exception as e:
        return None, f"حدث خطأ: {str(e)}"

# ============================================================
# دوال البوت
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحبًا!\n\n"
        "أرسل لي **رقم المعاملة (Order ID)** وسأبحث عنها في Binance Pay.\n\n"
        "مثال: `455443275906285568`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = update.message.text.strip()

    if not order_id.isdigit():
        await update.message.reply_text("⚠️ الرجاء إرسال رقم معاملة صحيح (أرقام فقط).")
        return

    msg = await update.message.reply_text("🔍 جاري البحث...")

    transaction, error = find_transaction_by_order_id(order_id)

    if error:
        await msg.edit_text(f"❌ {error}")
        return

    text = "✅ **تم العثور على المعاملة**\n\n"
    text += f"🆔 **رقم المعاملة**: `{transaction.get('orderId', 'غير متوفر')}`\n"
    text += f"💰 **المبلغ**: `{transaction.get('amount', 'غير متوفر')}`\n"
    text += f"💵 **العملة**: `{transaction.get('currency', 'غير متوفر')}`\n"
    text += f"📌 **الحالة**: `{transaction.get('status', 'غير متوفر')}`\n"
    text += f"🕐 **الوقت**: `{transaction.get('timestamp', 'غير متوفر')}`\n"
    text += f"📝 **الملاحظة**: `{transaction.get('note', 'لا يوجد')}`\n"

    await msg.edit_text(text, parse_mode="Markdown")

# ============================================================
# تشغيل البوت
# ============================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()