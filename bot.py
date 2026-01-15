from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from flask import Flask, request
import requests, re, mercadopago
import asyncio

# ===== CONFIG =====
BOT_TOKEN = "8145181010:AAH_Biz5U6NoqN3VMrONO72Q_L1iqbdwgB4"
INFOSIMPLES_TOKEN = "mvNtWrN44x0RNbqy0E6adD0_cAVTp_3Ff46AMzoN"
MP_ACCESS_TOKEN = "APP_USR-4667277616891710-011417-dcc261351a5eba41983397da434a1417-328105996"
RENDER_URL = "https://bot-placa-1.onrender.com"
# ==================

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

usuarios = {}
usuarios_aceitos = {}

app = Flask(__name__)
bot_app = None


# ===== TERMOS =====

TERMOS_TEXTO = (
    "📄 *TERMOS DE USO*\n\n"
    "Este bot realiza consultas de *dados veiculares* através da placa.\n"
    "Nenhum dado pessoal de proprietários é exibido.\n\n"
    "*É proibido utilizar este serviço para:*\n"
    "• Identificar proprietários de veículos\n"
    "• Perseguir, ameaçar ou causar dano a terceiros\n"
    "• Qualquer atividade ilegal\n\n"
    "Ao clicar em *Aceitar Termos*, você concorda com estas condições."
)

GUIA_TEXTO = (
    "📘 *GUIA RÁPIDO DE USO*\n\n"
    "🔎 Consultar placa → Envie a placa ABC1D23\n"
    "💳 Comprar consulta → Escolha PIX ou Cartão → Pague\n"
    "📊 Meu saldo → Veja seus créditos\n\n"
    "Após o pagamento, os créditos são liberados automaticamente."
)


# ===== MENU =====

def menu_principal():
    teclado = [
        [InlineKeyboardButton("🔎 Consultar placa", callback_data="consultar")],
        [InlineKeyboardButton("💳 Comprar consulta", callback_data="comprar")],
        [InlineKeyboardButton("📊 Meu saldo", callback_data="saldo")],
        [InlineKeyboardButton("📘 Guia", callback_data="guia")]
    ]
    return InlineKeyboardMarkup(teclado)


# ===== DESCOBRIR ESTADO =====

def descobrir_estado_placa(placa):
    letra = placa[0]
    mapa = {
        'A':'sp','B':'sp','C':'sp','D':'sp','E':'sp',
        'F':'rj','G':'rj','H':'mg','I':'mg','J':'es',
        'K':'ba','L':'ba','M':'se','N':'al','O':'pb','P':'pe',
        'Q':'pe','R':'ce','S':'rn','T':'pi',
        'U':'ma','V':'pa','W':'to','X':'go','Y':'mt','Z':'rs'
    }
    return mapa.get(letra, 'sp')


# ===== START =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not usuarios_aceitos.get(user_id):
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Aceitar Termos", callback_data="aceitar_termos")],
            [InlineKeyboardButton("❌ Recusar", callback_data="recusar_termos")]
        ])
        await update.message.reply_text(
            TERMOS_TEXTO, parse_mode="Markdown", reply_markup=teclado
        )
        return

    usuarios.setdefault(user_id, 0)
    await update.message.reply_text(
        "🚗 *Bot Consulta de Placas*",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )


# ===== CALLBACK MENU =====

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Termos
    if query.data == "aceitar_termos":
        usuarios_aceitos[user_id] = True
        usuarios.setdefault(user_id, 0)
        await query.message.reply_text("✅ Termos aceitos!", reply_markup=menu_principal())
        return

    if query.data == "recusar_termos":
        await query.message.reply_text("❌ É necessário aceitar os termos. Digite /start")
        return

    if not usuarios_aceitos.get(user_id):
        await query.message.reply_text("❌ Use /start para aceitar os termos.")
        return

    usuarios.setdefault(user_id, 0)

    if query.data == "guia":
        await query.message.reply_text(GUIA_TEXTO, parse_mode="Markdown", reply_markup=menu_principal())

    elif query.data == "saldo":
        await query.message.reply_text(f"📊 Seu saldo: {usuarios[user_id]}", reply_markup=menu_principal())

    elif query.data == "consultar":
        if usuarios[user_id] <= 0:
            await query.message.reply_text("❌ Sem créditos.", reply_markup=menu_principal())
        else:
            await query.message.reply_text("🔎 Envie a placa ABC1D23:")
            context.user_data["aguardando"] = True

    elif query.data == "comprar":
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("💠 Pagar por PIX", callback_data="pagar_pix")],
            [InlineKeyboardButton("💳 Pagar por Cartão", callback_data="pagar_cartao")]
        ])
        await query.message.reply_text("💰 Escolha o pagamento:", reply_markup=teclado)

    elif query.data == "pagar_pix":
        await gerar_pagamento_pix(query, user_id)

    elif query.data == "pagar_cartao":
        await gerar_pagamento_cartao(query, user_id)


# ===== PAGAMENTO PIX =====

async def gerar_pagamento_pix(query, user_id):
    valor = 1.00

    pref = sdk.preference().create({
        "items": [{
            "title": "Consulta Veicular (PIX)",
            "quantity": 1,
            "unit_price": valor
        }],
        "payment_methods": {"excluded_payment_types": [{"id": "credit_card"}]},
        "external_reference": str(user_id),
        "notification_url": f"{RENDER_URL}/webhook"
    })

    link = pref["response"]["init_point"]
    await query.message.reply_text(
        "💠 Pagamento PIX gerado!\nClique abaixo:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💠 Abrir PIX", url=link)]])
    )


# ===== PAGAMENTO CARTÃO =====

async def gerar_pagamento_cartao(query, user_id):
    valor = 1.00

    pref = sdk.preference().create({
        "items": [{
            "title": "Consulta Veicular (Cartão)",
            "quantity": 1,
            "unit_price": valor
        }],
        "payment_methods": {"excluded_payment_types": [{"id": "pix"}]},
        "external_reference": str(user_id),
        "notification_url": f"{RENDER_URL}/webhook"
    })

    link = pref["response"]["init_point"]
    await query.message.reply_text(
        "💳 Pagamento Cartão gerado!\nClique abaixo:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Abrir Cartão", url=link)]])
    )


# ===== RECEBER PLACA =====

async def receber_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("aguardando"):
        return

    placa = update.message.text.upper().strip()
    user_id = update.message.from_user.id

    if not re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', placa):
        await update.message.reply_text("❌ Placa inválida.")
        return

    if usuarios[user_id] <= 0:
        await update.message.reply_text("❌ Sem créditos.", reply_markup=menu_principal())
        return

    await update.message.reply_text("🔎 Consultando...")

    estado = descobrir_estado_placa(placa)
    url = f"https://api.infosimples.com/api/v2/consultas/detran/{estado}/veiculo"

    payload = {"token": INFOSIMPLES_TOKEN, "placa": placa}
    r = requests.post(url, json=payload, timeout=60)
    retorno = r.json()

    if "data" not in retorno or not retorno["data"]:
        await update.message.reply_text("❌ Nenhum dado encontrado.")
        context.user_data["aguardando"] = False
        return

    dados = retorno["data"][0]
    usuarios[user_id] -= 1

    await update.message.reply_text(
        f"🚘 RESULTADO\n\n"
        f"Placa: {placa}\n"
        f"Marca: {dados.get('marca','-')}\n"
        f"Modelo: {dados.get('modelo','-')}\n"
        f"Cor: {dados.get('cor','-')}\n"
        f"Situação: {dados.get('situacao','-')}\n\n"
        f"📊 Saldo restante: {usuarios[user_id]}",
        reply_markup=menu_principal()
    )

    context.user_data["aguardando"] = False


# ===== WEBHOOK MERCADO PAGO =====

@app.route("/webhook", methods=["POST"])
def webhook_mp():
    data = request.json
    if "data" not in data:
        return "OK", 200

    payment_id = data["data"]["id"]
    pagamento = sdk.payment().get(payment_id)

    if pagamento["response"]["status"] == "approved":
        user_id = int(pagamento["response"]["external_reference"])
        usuarios[user_id] = usuarios.get(user_id, 0) + 1

        asyncio.run(bot_app.bot.send_message(
            chat_id=user_id,
            text=f"✅ Pagamento aprovado!\n📊 Novo saldo: {usuarios[user_id]}",
            reply_markup=menu_principal()
        ))

    return "OK", 200


# ===== WEBHOOK TELEGRAM =====

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.json, bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK", 200


# ===== STARTUP =====

async def iniciar_bot():
    global bot_app
    bot_app = Application.builder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(menu_handler))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_placa))

    await bot_app.bot.set_webhook(f"{RENDER_URL}/telegram")
    await bot_app.initialize()
    await bot_app.start()


if __name__ == "__main__":
    asyncio.run(iniciar_bot())
    app.run(host="0.0.0.0", port=5000)
