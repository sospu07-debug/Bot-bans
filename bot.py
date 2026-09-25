import requests
import time
import hmac
import hashlib
import asyncio
from urllib.parse import urlencode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# استيراد دوال قاعدة البيانات من ملف db.py
from db import (
    init_db, get_balance, add_balance, deduct_balance,
    is_order_used, save_order,
    set_pending, get_pending, clear_pending
)

# ============================================================
# الإعدادات
# ============================================================

API_KEY = (
    'WFHIGs8VvN4IXWOIMJBRAjRVGYviS5005UNQJbOvP5t5mOeoZDtuQAeRByRTxfu8'
)

API_SECRET = (
    'FGKMYgMc9iI3VL1z6UhEzm1aGAk68aLMO3WxLapyhPnTrP6GjWeuahpXaE5LhKUs'
)

TELEGRAM_TOKEN =('8911308822:AAGeFsK8GTFP2f35vrKlGszP2-w_YGUFMGw'
)
ADMIN_ID = 8993088092
BINANCE_PAY_ID = '1124632840'

SMM_API_URL = 'https://smmnine.com/api/v2'
SMM_API_KEY = 'e4bab45c291769a570babc86b3f718c5c8a81b0e'

BASE_URL = "https://api.binance.com"
TIME_WINDOW = 3 * 24 * 60 * 60 * 1000

# ============================================================
# قفل المعالجة
# ============================================================

processing_lock = asyncio.Lock()

# ============================================================
# دوال Binance
# ============================================================

def create_signature(params):
    query_string = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return query_string, signature

def find_transaction(order_id):
    order_id = str(order_id).strip()
    params = {
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000,
        "limit": 100
    }
    query_string, signature = create_signature(params)
    url = BASE_URL + "/sapi/v1/pay/transactions?" + query_string + "&signature=" + signature
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
                tx_time = transaction.get("timestamp", 0)
                if tx_time and (int(time.time() * 1000) - tx_time) > TIME_WINDOW:
                    return None, "المعاملة قديمة (أكثر من 3 أيام)"
                return transaction, None
        return None, "لم يتم العثور على المعاملة"
    except Exception as e:
        return None, f"حدث خطأ: {str(e)}"

# ============================================================
# دوال SMMNine
# ============================================================

def smm_add_order(service_id, link, quantity):
    payload = {
        'key': SMM_API_KEY,
        'action': 'add',
        'service': service_id,
        'link': link,
        'quantity': quantity
    }
    try:
        response = requests.post(SMM_API_URL, data=payload, timeout=30)
        result = response.json()
        if 'order' in result:
            return result['order'], None
        else:
            return None, result.get('error', 'خطأ غير معروف من الموقع')
    except Exception as e:
        return None, f"فشل الاتصال بالموقع: {str(e)}"

# ============================================================
# الخدمات
# ============================================================

SERVICES = {
    "tg_members": {
        "name": "أعضاء تليجرام",
        "price": 0.5,
        "unit": 1000,
        "warranty": "14 يوم",
        "service_id": "8411"
    },
    "reactions": {
        "name": "ردود فعل",
        "price": 0.1,
        "unit": 1000,
        "warranty": "لا يوجد",
        "service_id": "ضع_رقم_الخدمة_هنا"
    }
}

# ============================================================
# دوال البوت
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.full_name
    balance = get_balance(user_id)

    text = (
        f"👋 أهلاً {name}\n\n"
        f"💰 رصيدك الحالي: `{balance} USDT`\n\n"
        f"اختر من الأزرار أدناه:"
    )
    keyboard = [
        [InlineKeyboardButton("💳 دفع بينانس", callback_data="pay_binance")],
        [InlineKeyboardButton("📱 خدمات تليجرام", callback_data="services_tg")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "pay_binance":
        await query.message.reply_text("💵 أرسل المبلغ الذي تريد شحنه (بالأرقام فقط).\nمثال: `5`", parse_mode="Markdown")
        context.user_data['awaiting_amount'] = True

    elif query.data == "services_tg":
        text = "📱 **خدمات تليجرام**\n\nاختر الخدمة:"
        keyboard = [
            [InlineKeyboardButton(f"👥 أعضاء تليجرام — {SERVICES['tg_members']['price']} USDT / {SERVICES['tg_members']['unit']}", callback_data="svc_tg_members")],
            [InlineKeyboardButton(f"💬 ردود فعل — {SERVICES['reactions']['price']} USDT / {SERVICES['reactions']['unit']}", callback_data="svc_reactions")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "svc_tg_members":
        svc = SERVICES["tg_members"]
        text = (
            f"👥 **{svc['name']}**\n\n"
            f"💰 السعر: `{svc['price']} USDT` لكل {svc['unit']}\n"
            f"🛡️ الضمان: {svc['warranty']}\n"
            f"🆔 رقم الخدمة: `{svc['service_id']}`\n\n"
            f"📎 أرسل **رابط القناة أو الحساب** الآن."
        )
        context.user_data['awaiting_service'] = "tg_members"
        context.user_data['service_link'] = None
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="services_tg")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "svc_reactions":
        svc = SERVICES["reactions"]
        text = (
            f"💬 **{svc['name']}**\n\n"
            f"💰 السعر: `{svc['price']} USDT` لكل {svc['unit']}\n"
            f"🛡️ الضمان: {svc['warranty']}\n"
            f"🆔 رقم الخدمة: `{svc['service_id']}`\n\n"
            f"📎 أرسل **رابط المنشور أو الحساب** الآن."
        )
        context.user_data['awaiting_service'] = "reactions"
        context.user_data['service_link'] = None
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="services_tg")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "back_main":
        user_id = query.from_user.id
        name = query.from_user.full_name
        balance = get_balance(user_id)
        text = f"👋 أهلاً {name}\n\n💰 رصيدك الحالي: `{balance} USDT`\n\nاختر من الأزرار أدناه:"
        keyboard = [
            [InlineKeyboardButton("💳 دفع بينانس", callback_data="pay_binance")],
            [InlineKeyboardButton("📱 خدمات تليجرام", callback_data="services_tg")],
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # 1. انتظار مبلغ الشحن
    if context.user_data.get('awaiting_amount'):
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ أرسل مبلغاً صحيحاً (أرقام فقط).")
            return
        set_pending(user_id, amount)
        context.user_data['awaiting_amount'] = False
        await update.message.reply_text(
            f"✅ تم تسجيل المبلغ: `{amount} USDT`\n\n"
            f"⏳ **في انتظار التحويل**\n\n"
            f"حوّل المبلغ إلى حساب Binance Pay التالي:\n"
            f"🆔 `{BINANCE_PAY_ID}`\n\n"
            f"بعد التحويل، أرسل **رقم المعاملة (Order ID)** هنا.",
            parse_mode="Markdown"
        )
        return

    # 2. انتظار رابط الخدمة
    if context.user_data.get('awaiting_service') and context.user_data.get('service_link') is None:
        context.user_data['service_link'] = text
        await update.message.reply_text(
            "✅ تم تسجيل الرابط.\n\n"
            "📊 أرسل **الكمية** المطلوبة (مثال: `1000`)."
        )
        return

    # 3. انتظار كمية الخدمة
    if context.user_data.get('awaiting_service') and context.user_data.get('service_link'):
        service_key = context.user_data['awaiting_service']
        link = context.user_data['service_link']
        svc = SERVICES[service_key]

        try:
            qty = int(text)
            if qty <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("⚠️ أرسل كمية صحيحة (أرقام فقط).")
            return

        total_price = (qty / svc['unit']) * svc['price']
        balance = get_balance(user_id)

        if balance < total_price:
            await update.message.reply_text(
                f"❌ رصيدك غير كافٍ.\nالمطلوب: `{total_price} USDT`\nرصيدك: `{balance} USDT`",
                parse_mode="Markdown"
            )
            context.user_data['awaiting_service'] = None
            context.user_data['service_link'] = None
            return

        deduct_balance(user_id, total_price)

        msg = await update.message.reply_text("⏳ جاري إرسال الطلب إلى الموقع...")
        order_id, error = smm_add_order(svc['service_id'], link, qty)

        if error:
            add_balance(user_id, total_price)
            await msg.edit_text(f"❌ فشل إنشاء الطلب:\n`{error}`", parse_mode="Markdown")
            context.user_data['awaiting_service'] = None
            context.user_data['service_link'] = None
            return

        new_balance = get_balance(user_id)
        await msg.edit_text(
            f"✅ **تم إنشاء طلبك بنجاح**\n\n"
            f"🛒 الخدمة: {svc['name']}\n"
            f"📦 الكمية: `{qty}`\n"
            f"🔗 الرابط: `{link}`\n"
            f"💰 التكلفة: `{total_price} USDT`\n"
            f"🆔 رقم الطلب: `{order_id}`\n"
            f"💳 رصيدك الجديد: `{new_balance} USDT`",
            parse_mode="Markdown"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🛒 **طلب جديد**\n"
                    f"المستخدم: `{user_id}`\n"
                    f"الخدمة: {svc['name']}\n"
                    f"الكمية: `{qty}`\n"
                    f"الرابط: `{link}`\n"
                    f"السعر: `{total_price} USDT`\n"
                    f"رقم الطلب: `{order_id}`"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"فشل إشعار الأدمن: {e}")

        context.user_data['awaiting_service'] = None
        context.user_data['service_link'] = None
        return

    # 4. التحقق من رقم المعاملة
    if text.isdigit():
        async with processing_lock:
            pending_amount = get_pending(user_id)
            if pending_amount is None:
                await update.message.reply_text("⚠️ لم تحدد مبلغاً بعد. اضغط على زر دفع بينانس أولاً.")
                return

            msg = await update.message.reply_text("🔍 جاري التحقق...")
            if is_order_used(text):
                await msg.edit_text("❌ رقم الأوردر مستخدم من قبل.")
                return

            transaction, error = find_transaction(text)
            if error:
                await msg.edit_text(f"❌ {error}")
                return

            tx_amount = float(transaction.get("amount", 0))
            tx_currency = transaction.get("currency", "USDT")
            save_order(text, user_id, tx_amount)

            if abs(tx_amount - pending_amount) < 0.001:
                add_balance(user_id, pending_amount)
                clear_pending(user_id)
                new_balance = get_balance(user_id)
                await msg.edit_text(
                    f"✅ **تم شحن رصيدك بنجاح**\n\n💰 المبلغ: `{tx_amount} {tx_currency}`\n💳 رصيدك الجديد: `{new_balance} USDT`",
                    parse_mode="Markdown"
                )
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"✅ شحن ناجح\nالمستخدم: `{user_id}`\nالمبلغ: `{tx_amount}`\nرقم: `{text}`",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"فشل إشعار الأدمن: {e}")
            else:
                await msg.edit_text(
                    f"❌ **المبلغ غير مطابق**\n\nالمطلوب: `{pending_amount} USDT`\nالمدفوع: `{tx_amount} {tx_currency}`\n\n⚠️ لم يتم شحن رصيدك.",
                    parse_mode="Markdown"
                )
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"⚠️ مبلغ غير مطابق\nالمستخدم: `{user_id}`\nالمطلوب: `{pending_amount}`\nالمدفوع: `{tx_amount}`\nرقم: `{text}`",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    print(f"فشل إشعار الأدمن: {e}")

# ============================================================
# تشغيل البوت
# ============================================================

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()