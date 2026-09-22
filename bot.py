import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============================================================
# الإعدادات - ضع مفاتيحك هنا
# ============================================================

API_KEY = 'Te2SJU8bбuhGXjWaNЗgijm3FBgUQ
TlqOrVzMMzH8GElgvsnjPtрХy3DPD
mdJHfNN'
API_SECRET = 'OBKIJKOC9KhqnXaZCstBfc4JnuvUF
2LOd7BvA3YaxyJHvSOniuksb1Th1ra
M2Qaz'
TELEGRAM_TOKEN = '8911308822:AAH4EPvsJzoXbG7iCAfq1t_a_sswQf2RqRY'

BASE_URL = "https://api.binance.com"

# ============================================================
# إعداد السجل
# ============================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ============================================================
# إنشاء التوقيع
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
# البحث عن معاملة
# ============================================================

def find_transaction(order_id):
    order_id = str(order_id).strip()

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
            return None, "فشل الاتصال بـ Binance"

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

    # التحقق من أن المدخل رقم
    if not order_id.isdigit():
        await update.message.reply_text("⚠️ الرجاء إرسال رقم معاملة صحيح (أرقام فقط).")
        return

    msg = await update.message.reply_text("🔍 جاري البحث...")

    transaction, error = find_transaction(order_id)

    if error:
        await msg.edit_text(f"❌ {error}")
        return

    # تنسيق النتيجة
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
