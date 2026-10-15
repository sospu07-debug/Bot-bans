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
#
from db import (
    init_db, get_balance, add_balance, deduct_balance,
    is_order_used, save_order,
    set_pending, get_pending, clear_pending,
    add_insta_account, get_insta_accounts,
    get_insta_account_by_id, delete_insta_account
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

TELEGRAM_TOKEN =('8784722345:AAFY7gkzM1Zzsrjlb6zzu5ed5GM-k0QOCUs'
)
ADMIN_ID = 8993088092
BINANCE_PAY_ID = '1124632840'

BASE_URL = "https://api.binance.com"
TIME_WINDOW = 3 * 24 * 60 * 60 * 1000

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
# القوائم
# ============================================================

def main_menu(user_id):
    keyboard = [
        [InlineKeyboardButton("💳 دفع بينانس", callback_data="pay_binance")],
        [InlineKeyboardButton("📸 حسابات انستا", callback_data="insta_accounts")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

def main_menu_text(name, balance):
    return (
        f"👋 أهلاً {name}\n\n"
        f"💰 رصيدك الحالي: `{balance} USDT`\n\n"
        f"اختر من الأزرار أدناه:"
    )

# ============================================================
# دوال البوت
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.full_name
    balance = get_balance(user_id)

    await update.message.reply_text(
        main_menu_text(name, balance),
        reply_markup=main_menu(user_id),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # ------- دفع بينانس -------
    if data == "pay_binance":
        await query.message.reply_text(
            "💵 أرسل المبلغ الذي تريد شحنه (بالأرقام فقط).\nمثال: `5`",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_amount'] = True

    # ------- قائمة الحسابات -------
    elif data == "insta_accounts":
        accounts = get_insta_accounts()
        if not accounts:
            await query.message.edit_text("📭 لا توجد حسابات متاحة حالياً.")
            return

        await query.message.edit_text("📸 **حسابات إنستغرام المتاحة:**")
        for acc in accounts:
            text = (
                f"👤 **{acc['name']}**\n"
                f"📝 {acc['description']}\n"
                f"💰 السعر: `{acc['price']} USDT`"
            )
            keyboard = [[InlineKeyboardButton(
                f"🛒 شراء — {acc['name']}",
                callback_data=f"buy_insta_{acc['id']}"
            )]]
            await query.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )

        await query.message.reply_text(
            "🔙 اضغط للرجوع.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
        )

    # ------- شراء حساب -------
    elif data.startswith("buy_insta_"):
        acc_id = int(data.replace("buy_insta_", ""))
        acc = get_insta_account_by_id(acc_id)
        if not acc:
            await query.message.reply_text("❌ الحساب غير موجود.")
            return

        balance = get_balance(user_id)
        if balance < acc['price']:
            await query.message.reply_text(
                f"❌ رصيدك غير كافٍ.\nالمطلوب: `{acc['price']} USDT`\nرصيدك: `{balance} USDT`",
                parse_mode="Markdown"
            )
            return

        # خصم الرصيد وحذف الحساب
        deduct_balance(user_id, acc['price'])
        delete_insta_account(acc_id)
        new_balance = get_balance(user_id)

        # إرسال رسالة التسليم
        await query.message.reply_text(
            f"✅ **تم الشراء بنجاح**\n\n"
            f"📦 **معلومات الحساب:**\n\n"
            f"{acc['deliver_message']}\n\n"
            f"💰 السعر: `{acc['price']} USDT`\n"
            f"💳 رصيدك الجديد: `{new_balance} USDT`",
            parse_mode="Markdown"
        )

        # إشعار الأدمن
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🛒 **بيع حساب**\n"
                    f"المشتري: `{user_id}`\n"
                    f"الحساب: `{acc['name']}`\n"
                    f"السعر: `{acc['price']} USDT`"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"فشل إشعار الأدمن: {e}")

    # ------- لوحة الأدمن -------
    elif data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.message.reply_text("❌ هذا الزر للأدمن فقط.")
            return
        text = "🛠️ **لوحة الأدمن**\n\nاختر:"
        keyboard = [
            [InlineKeyboardButton("➕ إضافة حساب إنستا", callback_data="admin_add_insta")],
            [InlineKeyboardButton("📋 عرض الحسابات", callback_data="admin_list_insta")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "admin_add_insta":
        if user_id != ADMIN_ID:
            return
        await query.message.reply_text(
            "📝 **الخطوة 1/4**: أرسل **اسم الحساب** (سيظهر في الزر).\n"
            "مثال: `حساب إنستا مميز`",
            parse_mode="Markdown"
        )
        context.user_data['add_insta_step'] = 1
        context.user_data['new_insta'] = {}

    elif data == "admin_list_insta":
        if user_id != ADMIN_ID:
            return
        accounts = get_insta_accounts()
        if not accounts:
            await query.message.edit_text(
                "📭 لا توجد حسابات.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]])
            )
            return
        text = "📋 **الحسابات المتاحة:**\n\n"
        for acc in accounts:
            text += f"🆔 `{acc['id']}` — `{acc['name']}` — {acc['price']} USDT\n"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # ------- رجوع -------
    elif data == "back_main":
        name = query.from_user.full_name
        balance = get_balance(user_id)
        await query.message.edit_text(
            main_menu_text(name, balance),
            reply_markup=main_menu(user_id),
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # ============================================================
    # استقبال بيانات حساب إنستا من الأدمن (4 خطوات)
    # ============================================================
    if context.user_data.get('add_insta_step') and user_id == ADMIN_ID:
        step = context.user_data['add_insta_step']
        new_insta = context.user_data.get('new_insta', {})

        if step == 1:
            new_insta['name'] = text
            context.user_data['new_insta'] = new_insta
            context.user_data['add_insta_step'] = 2
            await update.message.reply_text(
                "📝 **الخطوة 2/4**: أرسل **وصف الحساب** (يظهر أسفل الاسم).\n"
                "مثال: `حساب قديم 2015، متابعين 10k`",
                parse_mode="Markdown"
            )
            return

        elif step == 2:
            new_insta['description'] = text
            context.user_data['new_insta'] = new_insta
            context.user_data['add_insta_step'] = 3
            await update.message.reply_text(
                "📝 **الخطوة 3/4**: أرسل **الرسالة التي ستُرسل للمشتري بعد البيع**.\n"
                "هنا تضع معلومات الحساب كاملة (الإيميل، كلمة المرور، إلخ).",
                parse_mode="Markdown"
            )
            return

        elif step == 3:
            new_insta['deliver_message'] = text
            context.user_data['new_insta'] = new_insta
            context.user_data['add_insta_step'] = 4
            await update.message.reply_text(
                "📝 **الخطوة 4/4**: أرسل **السعر** بالدولار (أرقام فقط).\n"
                "مثال: `1.5`",
                parse_mode="Markdown"
            )
            return

        elif step == 4:
            try:
                price = float(text)
                if price <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("⚠️ أرسل سعراً صحيحاً (أرقام فقط).")
                return

            add_insta_account(
                new_insta['name'],
                new_insta['description'],
                new_insta['deliver_message'],
                price
            )
            context.user_data['add_insta_step'] = None
            context.user_data['new_insta'] = {}
            await update.message.reply_text(
                f"✅ **تم إضافة الحساب بنجاح**\n\n"
                f"👤 الاسم: `{new_insta['name']}`\n"
                f"📝 الوصف: `{new_insta['description']}`\n"
                f"💰 السعر: `{price} USDT`",
                parse_mode="Markdown"
            )
            return

    # ============================================================
    # انتظار مبلغ الشحن
    # ============================================================
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

    # ============================================================
    # التحقق من رقم المعاملة
    # ============================================================
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
                    f"✅ **تم شحن رصيدك بنجاح**\n\n"
                    f"💰 المبلغ: `{tx_amount} {tx_currency}`\n"
                    f"💳 رصيدك الجديد: `{new_balance} USDT`",
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
                    f"❌ **المبلغ غير مطابق**\n\n"
                    f"المطلوب: `{pending_amount} USDT`\n"
                    f"المدفوع: `{tx_amount} {tx_currency}`\n\n"
                    f"⚠️ لم يتم شحن رصيدك.",
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