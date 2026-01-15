from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

from flask import Flask, request
import threading
import requests, re, mercadopago

# ====== TOKENS ======
BOT_TOKEN = "8145181010:AAH_Biz5U6NoqN3VMrONO72Q_L1iqbdwgB4"
INFOSIMPLES_TOKEN = "mvNtWrN44x0RNbqy0E6adD0_cAVTp_3Ff46AMzoN"
MP_ACCESS_TOKEN = "APP_USR-4667277616891710-011417-dcc261351a5eba41983397da434a1417-328105996"
RENDER_URL = "https://bot-placa-1.onrender.com"  # <- altere
# ====================

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

usuarios = {}          # {telegram_id: creditos}
usuarios_aceitos = {} # termos aceitos

app = Flask(__name__)
bot_app = None


# ===== TERMOS =====

TERMOS_TEXTO = """
📄 *TERMOS DE USO*

Este bot fornece consultas de *dados veiculares*.
Nenhum dado pessoal de proprietário é exibido.

É proibido usar o serviço para:
• Identificar proprietários  
• Perseguir terceiros  
• Atividades ilegais  

Ao clicar em *Aceitar*, você concorda com os termos.
"""


# ===== MENU =====

def menu_principal():
    teclado = [
        [InlineKeyboardButton("🔎 Consultar placa", callback_data="consultar")],
        [InlineKeyboardButton("💳 Comprar consulta (PIX / Cartão)", callback_data="comprar")],
        [InlineKeyboardButton("📊 Meu saldo", callback_data="saldo")]
    ]
    return InlineKeyboardMarkup(teclado)


# ===== DESCOBRIR ESTADO PELA PLACA =====

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
        "🚗 *Bem-vindo ao Bot Consulta de Placas!*",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )


# ===== SALDO =====

async def saldo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    usuarios.setdefault(user_id, 0)

    await update.message.reply_text(
        f"📊 *Seu saldo:* {usuarios[user_id]} consulta(s)",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )


# ===== CONSULTAR COMANDO =====

async def consultarplaca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    usuarios.setdefault(user_id, 0)

    if usuarios[user_id] <= 0:
        await update.message.reply_text(
            "❌ Sem créditos. Clique em *Comprar consulta*.",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )
        return

    await update.message.reply_text("🔎 Envie a placa (ABC1D23):")
    context.user_data["aguardando"] = True


# ===== MENU CALLBACK =====

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Termos
    if query.data == "aceitar_termos":
        usuarios_aceitos[user_id] = True
        usuarios.setdefault(user_id, 0)
        await query.message.reply_text(
            "✅ Termos aceitos! Acesso liberado.",
            reply_markup=menu_principal()
        )
        return

    if query.data == "recusar_termos":
        await query.message.reply_text("❌ É necessário aceitar os termos para usar o bot.")
        return

    if not usuarios_aceitos.get(user_id):
        await query.message.reply_text("❌ Use /start para aceitar os termos.")
        return

    usuarios.setdefault(user_id, 0)

    if query.data == "saldo":
        await query.message.reply_text(
            f"📊 *Seu saldo:* {usuarios[user_id]} consulta(s)",
            parse_mode="Markdown",
            reply_markup=menu_principal()
        )

    elif query.data == "consultar":
        if usuarios[user_id] <= 0:
            await query.message.reply_text(
                "❌ Sem créditos. Compre uma consulta.",
                reply_markup=menu_principal()
            )
        else:
            await query.message.reply_text("🔎 Envie a placa (ABC1D23):")
            context.user_data["aguardando"] = True

    elif query.data == "comprar":
        await gerar_pagamento(query, user_id)


# ===== GERAR PAGAMENTO (PIX + CARTÃO) =====

async def gerar_pagamento(query, user_id):
    valor = 1.00  # valor por consulta

    preference = sdk.preference().create({
        "items": [{
            "title": "Consulta Veicular",
            "quantity": 1,
            "unit_price": valor
        }],
        "external_reference": str(user_id),
        "notification_url": f"{RENDER_URL}/webhook",
        "back_urls": {
            "success": f"{RENDER_URL}/sucesso",
            "failure": f"{RENDER_URL}/erro"
        },
        "auto_return": "approved"
    })

    link_pagamento = preference["response"]["init_point"]

    await query.message.reply_text(
        "💳 *Pagamento gerado!*\n\n"
        "Clique no link abaixo para pagar com PIX ou Cartão:\n\n"
        f"{link_pagamento}\n\n"
        "Após o pagamento, o crédito será liberado automaticamente.",
        parse_mode="Markdown"
    )


# ===== CONSULTA PLACA =====

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

    payload = {
        "token": INFOSIMPLES_TOKEN,
        "placa": placa
    }

    r = requests.post(url, json=payload, timeout=60)
    retorno = r.json()

    if "data" not in retorno or not retorno["data"]:
        await update.message.reply_text(
            f"❌ Nenhum dado encontrado no DETRAN-{estado.upper()}."
        )
        context.user_data["aguardando"] = False
        return

    dados = retorno["data"][0]
    usuarios[user_id] -= 1

    await update.message.reply_text(
        f"🚘 *RESULTADO*\n\n"
        f"Placa: {placa}\n"
        f"Estado: {estado.upper()}\n"
        f"Marca: {dados.get('marca','-')}\n"
        f"Modelo: {dados.get('modelo','-')}\n"
        f"Cor: {dados.get('cor','-')}\n"
        f"Situação: {dados.get('situacao','-')}\n\n"
        f"📊 Créditos restantes: {usuarios[user_id]}",
        parse_mode="Markdown",
        reply_markup=menu_principal()
    )

    context.user_data["aguardando"] = False


# ===== WEBHOOK MERCADO PAGO =====

@app.route("/webhook", methods=["POST"])
def webhook():
    global bot_app

    data = request.json
    if "data" not in data:
        return "OK", 200

    payment_id = data["data"]["id"]

    pagamento = sdk.payment().get(payment_id)
    status = pagamento["response"]["status"]

    if status == "approved":
        user_id = int(pagamento["response"]["external_reference"])
        usuarios[user_id] = usuarios.get(user_id, 0) + 1

        # Mensagem automática no Telegram
        try:
            bot_app.bot.send_message(
                chat_id=user_id,
                text=(
                    "✅ *Pagamento aprovado!*\n\n"
                    f"📊 Novo saldo: {usuarios[user_id]} consulta(s)\n\n"
                    "Você já pode consultar placas 👇"
                ),
                parse_mode="Markdown",
                reply_markup=menu_principal()
            )
        except:
            pass

    return "OK", 200


# ===== ROTAS DE RETORNO OPCIONAIS =====

@app.route("/sucesso")
def sucesso():
    return "Pagamento aprovado! Você pode voltar ao bot."

@app.route("/erro")
def erro():
    return "Pagamento não concluído."


# ===== INICIAR =====

def iniciar_flask():
    app.run(host="0.0.0.0", port=5000)


def main():
    global bot_app

    threading.Thread(target=iniciar_flask).start()

    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("saldo", saldo_cmd))
    bot_app.add_handler(CommandHandler("consultarplaca", consultarplaca_cmd))
    bot_app.add_handler(CallbackQueryHandler(menu_handler))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber_placa))

    bot_app.run_polling()


if __name__ == "__main__":
    main()
