from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from flask import Flask, request
import requests, re, mercadopago
import qrcode, io, threading

# ====== TOKENS ======
BOT_TOKEN = "8145181010:AAH_Biz5U6NoqN3VMrONO72Q_L1iqbdwgB4"
INFOSIMPLES_TOKEN = "mvNtWrN44x0RNbqy0E6adD0_cAVTp_3Ff46AMzoN"
MP_ACCESS_TOKEN = "APP_USR-4667277616891710-011417-dcc261351a5eba41983397da434a1417-328105996"
# ====================

API_URL = "https://api.infosimples.com/api/v2/consultas/placa/{placa}"
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

usuarios = {}      # {telegram_id: creditos}
pagamentos = {}    # {payment_id: telegram_id}


# ====== MENSAGENS PADRÃO ======

def menu_principal():
    teclado = [
        [InlineKeyboardButton("🔎 Consultar placa", callback_data="consultar")],
        [InlineKeyboardButton("💳 Comprar 1 consulta (R$0,01)", callback_data="comprar")],
        [InlineKeyboardButton("📊 Meu saldo", callback_data="saldo")]
    ]
    return InlineKeyboardMarkup(teclado)


async def mensagem_sem_saldo(update_or_query, user_id):
    texto = (
        "❌ *Você não possui créditos suficientes!*\n\n"
        "Para consultar uma placa, é necessário ter saldo.\n\n"
        "💳 *Como recarregar:*\n"
        "Clique em **Comprar 1 consulta (R$0,01)** no menu.\n"
        "Pague o PIX gerado.\n"
        "Assim que o pagamento for confirmado, seu crédito será liberado automaticamente.\n\n"
        "Após recarregar, use /consultarplaca"
    )

    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(texto, parse_mode="Markdown", reply_markup=menu_principal())
    else:
        await update_or_query.edit_message_text(texto, parse_mode="Markdown", reply_markup=menu_principal())


# ====== TELEGRAM BOT ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚗 *Bem-vindo ao Bot Consulta de Placas!*\n\n"
        "📌 Comandos disponíveis:\n"
        "/start → Iniciar bot\n"
        "/saldo → Ver saldo\n"
        "/consultarplaca → Consultar uma placa\n\n"
        "Ou utilize o menu abaixo:",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )


async def saldo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in usuarios:
        usuarios[user_id] = 0

    await update.message.reply_text(
        f"📊 *Seu saldo atual:*\n{usuarios[user_id]} consulta(s)",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )


async def consultarplaca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in usuarios:
        usuarios[user_id] = 0

    if usuarios[user_id] <= 0:
        await mensagem_sem_saldo(update, user_id)
        return

    await update.message.reply_text(
        "🔎 *Envie agora a placa do veículo*\nExemplo: ABC1D23",
        parse_mode="Markdown"
    )
    context.user_data["aguardando"] = True


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
        await query.edit_message_text(
            f"📊 *Seu saldo atual:*\n{usuarios[user_id]} consulta(s)",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )

    elif query.data == "consultar":
        if usuarios[user_id] <= 0:
            await mensagem_sem_saldo(query, user_id)
        else:
            await query.edit_message_text(
                "🔎 *Envie agora a placa do veículo*\nExemplo: ABC1D23",
                parse_mode="Markdown"
            )
            context.user_data["aguardando"] = True

    elif query.data == "comprar":
        await gerar_pix(query, user_id)


# ====== GERAR PIX ======

async def gerar_pix(query, user_id):
    valor = 0.01

    pagamento = sdk.payment().create({
        "transaction_amount": valor,
        "description": "1 consulta - Bot Consulta Placa",
        "payment_method_id": "pix",
        "payer": {"email": f"user{user_id}@bot.com"}
    })

    resp = pagamento["response"]

    if "id" not in resp:
        print("ERRO MP:", resp)
        await query.edit_message_text(
            "❌ Erro ao gerar PIX.\nTente novamente em instantes."
        )
        return

    payment_id = resp["id"]
    pix_code = resp["point_of_interaction"]["transaction_data"]["qr_code"]

    pagamentos[payment_id] = user_id

    qr = qrcode.make(pix_code)
    bio = io.BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)

    await query.message.reply_photo(
        photo=bio,
        caption=(
            f"💳 *PIX GERADO COM SUCESSO*\n\n"
            f"Valor: R$ {valor:.2f}\n\n"
            f"*Copia e Cola:*\n`{pix_code}`\n\n"
            f"⏳ *Aguardando pagamento...*\n"
            f"Assim que o pagamento for confirmado, "
            f"seu crédito será liberado automaticamente.\n\n"
            f"Após a liberação, use /consultarplaca"
        ),
        parse_mode="Markdown"
    )


# ====== RECEBER PLACA ======

async def receber_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("aguardando"):
        return

    placa = update.message.text.upper().strip()
    user_id = update.message.from_user.id

    if not re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', placa):
        await update.message.reply_text("❌ Placa inválida. Ex: ABC1D23")
        return

    if usuarios[user_id] <= 0:
        await mensagem_sem_saldo(update, user_id)
        return

    await update.message.reply_text("🔎 Consultando veículo...")

    r = requests.get(
        API_URL.format(placa=placa),
        headers={"Authorization": f"Bearer {INFOSIMPLES_TOKEN}"}
    )

    retorno = r.json()

    if "data" not in retorno or not retorno["data"]:
        await update.message.reply_text(
            "❌ Nenhum dado encontrado.\nVerifique a placa ou saldo da InfoSimples."
        )
        context.user_data["aguardando"] = False
        return

    dados = retorno["data"][0]
    usuarios[user_id] -= 1

    await update.message.reply_text(
        f"🚘 *RESULTADO DA CONSULTA*\n\n"
        f"Placa: {placa}\n"
        f"Marca: {dados.get('marca','-')}\n"
        f"Modelo: {dados.get('modelo','-')}\n"
        f"Cor: {dados.get('cor','-')}\n"
        f"Situação: {dados.get('situacao','-')}\n\n"
        f"📊 Créditos restantes: {usuarios[user_id]}\n\n"
        f"Para nova consulta use /consultarplaca",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )

    context.user_data["aguardando"] = False


# ====== WEBHOOK MERCADO PAGO ======

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
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
            usuarios[user_id] += 1

            # Mensagem automática de liberação
            try:
                bot_app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "✅ *Pagamento confirmado!*\n\n"
                        "Seu crédito foi liberado com sucesso.\n\n"
                        "Agora você já pode consultar uma placa.\n"
                        "Use o comando:\n/consultarplaca"
                    ),
                    parse_mode="Markdown",
                    reply_markup=menu_principal()
                )
            except:
                print("Não foi possível enviar mensagem ao usuário.")

            print(f"PIX aprovado → crédito liberado para {user_id}")

    return "OK", 200


# ====== INICIAR TELEGRAM EM THREAD ======

def iniciar_bot():
    global bot_app
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("saldo", saldo_cmd))
    bot_app.add_handler(CommandHandler("consultarplaca", consultarplaca_cmd))

    bot_app.add_handler(CallbackQueryHandler(menu_handler))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_placa))

    bot_app.run_polling()


# ====== MAIN ======

if __name__ == "__main__":
    threading.Thread(target=iniciar_bot).start()
    app.run(host="0.0.0.0", port=5000)
