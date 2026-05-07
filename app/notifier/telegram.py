"""Envio de mensagens pro Telegram via Bot API (HTTP direto, sem polling).

Uso HTTP cru no lugar do python-telegram-bot porque so precisamos enviar —
nao queremos rodar o Application/event loop dele em paralelo ao FastAPI.
"""

import html as htmllib
import logging
from typing import Optional

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


EMOJIS_CATEGORIA = {
    "corrida": "👟",
    "maquiagem": "💄",
    "cabelo": "💆‍♀️",
    "infantil": "👦",
}

# Banda colorida de desconto pra dar ênfase visual
def _emoji_desconto(pct: Optional[int]) -> str:
    if not pct:
        return ""
    if pct >= 60:
        return "🔥🔥🔥"
    if pct >= 40:
        return "🔥🔥"
    if pct >= 25:
        return "🔥"
    return "✨"


def _fmt_real(valor: Optional[float]) -> str:
    if valor is None:
        return "-"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_evento_html(evento) -> str:
    """Gera mensagem HTML pro Telegram. Layout em 'cartao' com hierarquia visual."""
    o = evento.classificada.oferta
    marca = evento.classificada.marca
    categoria = evento.classificada.categoria
    emoji_cat = EMOJIS_CATEGORIA.get(categoria, "🛒")
    emoji_fogo = _emoji_desconto(o.desconto_pct)

    titulo = htmllib.escape(o.titulo)
    loja = htmllib.escape(o.loja)
    marca_e = htmllib.escape(marca)
    url = htmllib.escape(o.url, quote=True)

    if evento.tipo == "nova":
        cabecalho = f"{emoji_fogo} <b>NOVA OFERTA</b> {emoji_cat}"
    else:
        cabecalho = f"📉 <b>BAIXOU DE PREÇO</b> {emoji_cat}"

    linhas = [
        cabecalho,
        "━━━━━━━━━━━━━━━━━━",
        f"<b>{titulo}</b>",
        "",  # linha em branco pra respirar
    ]

    # Bloco de preço — destaque máximo
    if o.preco_de and o.desconto_pct:
        linhas.append(
            f"💰 <b>{_fmt_real(o.preco_atual)}</b>  "
            f"<i>(antes <s>{_fmt_real(o.preco_de)}</s>)</i>"
        )
        linhas.append(f"🏷️  <b>-{o.desconto_pct}%</b> de desconto")
    else:
        linhas.append(f"💰 <b>{_fmt_real(o.preco_atual)}</b>")

    if evento.preco_anterior:
        queda = (1 - o.preco_atual / evento.preco_anterior) * 100
        linhas.append(
            f"📉 Caiu de <b>{_fmt_real(evento.preco_anterior)}</b> "
            f"(-{queda:.0f}% em relação à última checagem)"
        )

    # Metadados
    linhas.append("")
    linhas.append(f"🏪 <b>{loja}</b>  ·  🏷️ {marca_e}")
    linhas.append("━━━━━━━━━━━━━━━━━━")
    linhas.append(f'🔗 <a href="{url}"><b>Ver oferta no site</b></a>')

    return "\n".join(linhas)


async def send_message(text: str, parse_mode: str = "HTML") -> tuple[bool, Optional[str]]:
    """Envia pra cada chat_id em settings.telegram_chat_ids.
    Considera sucesso se PELO MENOS UM destino recebeu."""
    if not settings.telegram_configurado:
        return False, "telegram nao configurado em .env (TELEGRAM_BOT_TOKEN/CHAT_ID vazios)"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    sucessos: list[str] = []
    erros: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in settings.telegram_chat_ids:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": False,
            }
            try:
                r = await client.post(url, json=payload)
                r.raise_for_status()
                sucessos.append(chat_id)
            except httpx.HTTPStatusError as e:
                body = e.response.text[:200]
                logger.warning("Telegram chat=%s HTTP %s: %s", chat_id, e.response.status_code, body)
                erros.append(f"chat={chat_id}: HTTP {e.response.status_code} {body}")
            except Exception as e:
                logger.warning("Telegram chat=%s falhou: %s", chat_id, e)
                erros.append(f"chat={chat_id}: {e}")
    if not sucessos:
        return False, "; ".join(erros)
    if erros:
        return True, "parcial — " + "; ".join(erros)
    return True, None


async def send_test_message() -> tuple[bool, Optional[str]]:
    msg = (
        "✅ <b>PromoTracker conectado</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Notificações vão chegar aqui quando houver promoções das marcas-alvo:\n"
        "👟 Tênis de corrida (Asics, Mizuno, Nike, Adidas, Olympikus, Brooks, Saucony)\n"
        "💄 Maquiagem (Vizzela, Dailus)\n"
        "💆‍♀️ Cabelo (Lola Cosmetics)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<i>Coleta a cada 1 min · Revalidação a cada 1 min</i>"
    )
    return await send_message(msg)
