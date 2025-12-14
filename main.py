# main.py
import os
import time
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
import uvicorn

from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from storage import init_db, create_invoice, update_invoice, get_invoice_by_ref, get_invoice_by_reference
from tripay import (
    list_payment_channels,
    create_transaction,
    signature_closed_payment,
    callback_signature,
)

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

TRIPAY_MERCHANT_CODE = os.getenv("TRIPAY_MERCHANT_CODE", "")
TRIPAY_PRIVATE_KEY = os.getenv("TRIPAY_PRIVATE_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# Pilih default channel (boleh kamu ganti)
DEFAULT_METHOD = os.getenv("TRIPAY_DEFAULT_METHOD", "QRIS")  # contoh: "BRIVA", "BCAVA", "QRIS"

# ========= INIT =========
init_db()
app = FastAPI()
bot = Client("tripay-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def rupiah(n: int) -> str:
    return f"Rp{n:,}".replace(",", ".")

def new_merchant_ref(user_id: int) -> str:
    return f"TG{user_id}{int(time.time())}"

# ========= BOT COMMANDS =========
@bot.on_message(filters.command("start"))
async def start_cmd(_, m: Message):
    await m.reply(
        "Yo. Ini bot payment Tripay.\n\n"
        "Commands:\n"
        "/methods = lihat metode aktif\n"
        "/buy <amount> [method] = bikin invoice\n"
        "Contoh: /buy 10000 QRIS"
    )

@bot.on_message(filters.command("methods"))
async def methods_cmd(_, m: Message):
    try:
        chans = list_payment_channels()
        active = [c for c in chans if c.get("active")]
        # tampilkan singkat biar nggak kepanjangan
        lines = []
        for c in active[:30]:
            lines.append(f"- `{c['code']}` | {c['name']} ({c['group']})")
        more = "" if len(active) <= 30 else f"\n…dan {len(active)-30} lainnya"
        await m.reply("Metode aktif (sample):\n" + "\n".join(lines) + more)
    except Exception as e:
        await m.reply(f"Gagal ambil channel: {e}")

@bot.on_message(filters.command("buy"))
async def buy_cmd(_, m: Message):
    parts = m.text.split()
    if len(parts) < 2:
        return await m.reply("Format: /buy <amount> [method]\nContoh: /buy 10000 QRIS")

    try:
        amount = int(parts[1])
        if amount < 1000:
            return await m.reply("Amount kekecilan. Minimal 1000 biar niat.")
    except:
        return await m.reply("Amount harus angka. Contoh: /buy 10000 QRIS")

    method = parts[2].upper() if len(parts) >= 3 else DEFAULT_METHOD

    user = m.from_user
    if not user:
        return await m.reply("User tidak terdeteksi.")

    merchant_ref = new_merchant_ref(user.id)
    signature = signature_closed_payment(TRIPAY_MERCHANT_CODE, merchant_ref, amount, TRIPAY_PRIVATE_KEY)

    callback_url = f"{PUBLIC_BASE_URL}/tripay/callback"  # callback transaction status :contentReference[oaicite:6]{index=6}

    payload = {
        "method": method,
        "merchant_ref": merchant_ref,
        "amount": amount,
        "customer_name": user.first_name or "Telegram User",
        "customer_email": f"{user.id}@telegram.local",
        "customer_phone": "0000000000",
        "order_items[0][name]": "Topup / Digital Item",
        "order_items[0][price]": amount,
        "order_items[0][quantity]": 1,
        "callback_url": callback_url,
        "expired_time": int(time.time() + 3600),  # 1 jam
        "signature": signature,
    }

    try:
        data = create_transaction(payload)
        # Beberapa field yang biasanya penting untuk user:
        reference = data.get("reference")
        pay_url = data.get("pay_url") or data.get("checkout_url")  # tergantung channel
        qr_url = data.get("qr_url")  # biasanya ada kalau QRIS

        create_invoice({
            "merchant_ref": merchant_ref,
            "user_id": user.id,
            "amount": amount,
            "method": method,
            "reference": reference,
            "status": "UNPAID",
            "pay_url": pay_url,
            "qr_url": qr_url,
            "created_at": int(time.time()),
            "paid_at": None,
        })

        kb = []
        if pay_url:
            kb.append([InlineKeyboardButton("Buka halaman bayar", url=pay_url)])
        if qr_url:
            kb.append([InlineKeyboardButton("QR (gambar)", url=qr_url)])

        text = (
            f"Invoice dibuat.\n"
            f"- Ref: `{merchant_ref}`\n"
            f"- Method: `{method}`\n"
            f"- Amount: {rupiah(amount)}\n"
            f"- Tripay Ref: `{reference}`\n\n"
            f"Status: UNPAID\n"
            f"Nanti kalau udah PAID, bot auto nge-chat kamu."
        )
        await m.reply(text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)

    except Exception as e:
        await m.reply(f"Gagal bikin transaksi: {e}")

# ========= WEBHOOK / CALLBACK =========
@app.post("/tripay/callback")
async def tripay_callback(
    request: Request,
    x_callback_signature: Optional[str] = Header(default=None, convert_underscores=False),
    x_callback_event: Optional[str] = Header(default=None, convert_underscores=False),
):
    # Tripay kirim event "payment_status" dan signature via header :contentReference[oaicite:7]{index=7}
    raw = await request.body()

    if not x_callback_signature or not x_callback_event:
        return JSONResponse({"success": False, "message": "Missing headers"}, status_code=400)

    if x_callback_event != "payment_status":
        return JSONResponse({"success": False, "message": f"Unrecognized event: {x_callback_event}"}, status_code=400)

    expected = callback_signature(raw, TRIPAY_PRIVATE_KEY)
    if x_callback_signature != expected:
        return JSONResponse({"success": False, "message": "Invalid signature"}, status_code=401)

    data = await request.json()
    reference = data.get("reference")
    merchant_ref = data.get("merchant_ref")
    status = (data.get("status") or "").upper()
    paid_at = data.get("paid_at")

    if not reference:
        return JSONResponse({"success": False, "message": "Missing reference"}, status_code=400)

    inv = None
    if merchant_ref:
        inv = get_invoice_by_ref(merchant_ref)
    if not inv:
        inv = get_invoice_by_reference(reference)

    if not inv:
        # balikin success true biar Tripay nggak spam retry kalau invoice memang sudah dibuang
        return JSONResponse({"success": True})

    update_invoice(inv["merchant_ref"], status=status, paid_at=paid_at)

    # Kalau PAID -> notif user
    if status == "PAID":
        try:
            await bot.send_message(
                inv["user_id"],
                f"Payment masuk.\n"
                f"- Ref: `{inv['merchant_ref']}`\n"
                f"- Amount: {rupiah(inv['amount'])}\n"
                f"- Method: `{inv['method']}`\n"
                f"Status: PAID\n\n"
                f"Next step: tinggal kamu sambungin ke logic 'aktifkan premium / deliver produk'."
            )
        except Exception:
            # jangan bikin callback gagal kalau telegram gagal kirim
            pass

    # Tripay mengharapkan respons {"success": true}; kalau tidak, mereka retry :contentReference[oaicite:8]{index=8}
    return JSONResponse({"success": True})

# ========= RUNNER =========
async def run_all():
    await bot.start()
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(run_all())
