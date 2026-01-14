from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from flask import Flask, request
import threading
import requests, re, mercadopago
import qrcode
import io

# ====== TOKENS ======
BOT_TOKEN = "8145181010:AAH_Biz5U6NoqN3VMrONO72Q_L1iqbdwgB4"
INFOSIMPLES_TOKEN = "mvNtWrN44x0RNbqy0E6adD0_cAVTp_3Ff46AMzoN"
MP_ACCESS_TOKEN = "APP_USR-4667277616891710-011417-dcc261351a5eba41983397da434a1417-328105996"
# ====================

API_URL = "https://api.infosimples.com/api/v2/consultas/placa/{placa}"
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

usuarios = {}      # {telegram_id: creditos}
pagamentos = {}    # {payment_id: telegram_id}

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = [
        [InlineKeyboardButton("🔎 Consultar placa", callback_data="consultar")],
        [InlineKeyboardButton("💳 Comprar 1 consulta (R$0,01)", callback_data="comprar")],
        [InlineKeyboardButton("📊 Meu saldo", callback_data="saldo")]
    ]
    await update.message.reply_text(
        "🚗 Consulta de Placas\nEscolha uma opção:",
        reply_markup=InlineKeyboardMarkup(teclado)
    )

# ===== MENU =====
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except:
        pass

    user_id = query.from_user.id

    if user_id not in usuarios:
        usuarios[user_id] = 0

    if query.data == "saldo":
        await query.edit_message_text(f"📊 Saldo: {usuarios[user_id]} consultas")

    elif query.data == "consultar":
        if usuarios[user_id] <= 0:
            await query.edit_message_text("❌ Sem créditos. Compre primeiro.")
        else:
            await query.edit_message_text("Envie a placa do veículo:")
            context.user_data["aguardando"] = True

    elif query.data == "comprar":
        await gerar_pix(query, user_id)

# ===== GERAR PIX =====
async def gerar_pix(query, user_id):
    valor = 0.01  # 💰 1 centavo por consulta

    pagamento = sdk.payment().create({
        "transaction_amount": valor,
        "description": "1 consulta - Bot Consulta Placa",
        "payment_method_id": "pix",
        "payer": {"email": f"user{user_id}@bot.com"}
    })

    resp = pagamento["response"]

    if "id" not in resp:
        print("ERRO Mercado Pago:", resp)
        await query.edit_message_text(
            "❌ Erro ao gerar PIX.\nVerifique o Access Token do Mercado Pago."
        )
        return

    payment_id = resp["id"]
    pix_code = resp["point_of_interaction"]["transaction_data"]["qr_code"]

    pagamentos[payment_id] = user_id

    # QR Code
    qr = qrcode.make(pix_code)
    bio = io.BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)

    await query.message.reply_photo(
        photo=bio,
        caption=(
            f"💳 *PIX GERADO*\n\n"
            f"Valor: R$ {valor:.2f}\n\n"
            f"*Copia e Cola:*\n`{pix_code}`\n\n"
            f"⏳ Aguardando pagamento...\n"
            f"Após o pagamento, 1 crédito será liberado automaticamente."
        ),
        parse_mode="Markdown"
    )

# ===== RECEBER PLACA =====
async def receber_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("aguardando"):
        return

    placa = update.message.text.upper().strip()
    user_id = update.message.from_user.id

    if not re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', placa):
        await update.message.reply_text("❌ Placa inválida. Ex: ABC1D23")
        return

    if usuarios[user_id] <= 0:
        await update.message.reply_text("❌ Sem créditos. Compre primeiro.")
        return

    await update.message.reply_text("🔎 Consultando veículo...")

    r = requests.get(
        API_URL.format(placa=placa),
        headers={"Authorization": f"Bearer {INFOSIMPLES_TOKEN}"}
    )

    if r.status_code != 200:
        await update.message.reply_text("❌ Erro ao acessar a API InfoSimples.")
        return

    retorno = r.json()

    if "data" not in retorno or len(retorno["data"]) == 0:
        await update.message.reply_text(
            "❌ Nenhum dado retornado.\n"
            "Verifique placa ou saldo da InfoSimples."
        )
        context.user_data["aguardando"] = False
        return

    dados = retorno["data"][0]

    usuarios[user_id] -= 1

    msg = (
        f"🚘 RESULTADO DA CONSULTA\n\n"
        f"Placa: {placa}\n"
        f"Marca: {dados.get('marca','-')}\n"
        f"Modelo: {dados.get('modelo','-')}\n"
        f"Ano: {dados.get('ano_modelo','-')}\n"
        f"Cor: {dados.get('cor','-')}\n"
        f"Situação: {dados.get('situacao','-')}\n\n"
        f"💳 Créditos restantes: {usuarios[user_id]}"
    )

    await update.message.reply_text(msg)
    context.user_data["aguardando"] = False

# ===== WEBHOOK MERCADO PAGO =====
app_web = Flask(__name__)

@app_web.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "data" not in data:
        return "OK", 200

    payment_id = data["data"]["id"]

    pagamento = sdk.payment().get(payment_id)
    status = pagamento["response"]["status"]

    if status == "approved":
        user_id = pagamentos.get(payment_id)
        if user_id:
            usuarios[user_id] += 1   # ✅ Libera 1 consulta
            print(f"PIX aprovado! 1 crédito liberado para {user_id}")

    return "OK", 200

def rodar_webhook():
    app_web.run(host="0.0.0.0", port=5000)

# ===== MAIN =====
def main():
    threading.Thread(target=rodar_webhook).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_placa))
    app.run_polling()

if __name__ == "__main__":
    main()
