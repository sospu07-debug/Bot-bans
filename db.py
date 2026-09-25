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

# استيراد دوال قاعدة البيانات
from db import (
    init_db, get_balance, add_balance, deduct_balance,
    is_order_used, save_order,
    set_pending, get_pending, clear_pending
)

# ============================================================
# الإعدادات
# ============================================================

API_KEY = 'ضع_مفتاح_API_هنا'
API_SECRET = 'ضع_المفتاح_السري_هنا'
TELEGRAM_TOKEN = 'ضع_توكن_البوت_هنا'
ADMIN_ID = 123456789
BINANCE_PAY_ID = '1252306038'

SMM_API_URL = 'https://smmnine.com/api/v2'
SMM_API_KEY = 'ضع_مفتاح_SMMNine_هنا'

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
# باقي دوال البوت (start, button_handler, handle_message)
# ============================================================

# ... (نفس الكود السابق من start إلى النهاية، لا تغيير)