"""WhatsApp via CallMeBot.

CallMeBot e um servico gratuito que envia mensagens WhatsApp pra um numero
ja autorizado. Setup do usuario (uma vez):
  1) Adiciona +34 644 51 95 23 como contato "CallMeBot"
  2) Manda "I allow callmebot to send me messages" pelo WhatsApp
  3) Recebe a API key na resposta (~2min)

Limites: 1 mensagem a cada 2s, 1000/dia. Mais que suficiente pro nosso caso.

Para grupos de WhatsApp: setup mais complexo, ver README.
"""

import logging
from typing import Optional

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


EMOJIS_CATEGORIA = {
    "corrida": "👟",
    "maquiagem": "💄",
    "cabelo": "💆",
    "infantil": "👦",
}


def _fmt_real(valor: Optional[float]) -> str:
    if valor is None:
        return "-"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_evento_text(evento) -> str:
    """Versao texto puro pro WhatsApp (sem HTML, com emojis e *bold* via asteriscos)."""
    o = evento.classificada.oferta
    marca = evento.classificada.marca
    categoria = evento.classificada.categoria
    emoji = EMOJIS_CATEGORIA.get(categoria, "🛒")
    marker = "🔥 NOVA OFERTA" if evento.tipo == "nova" else "⬇️ BAIXOU DE PRECO"

    linhas = [
        f"{emoji} *{marker}*",
        f"*{o.titulo}*",
        f"Marca: {marca}  •  Loja: {o.loja}",
    ]
    if o.preco_de and o.desconto_pct:
        linhas.append(
            f"De ~{_fmt_real(o.preco_de)}~ por *{_fmt_real(o.preco_atual)}* "
            f"({o.desconto_pct}% off)"
        )
    else:
        linhas.append(f"*{_fmt_real(o.preco_atual)}*")
    if evento.preco_anterior:
        linhas.append(f"Visto antes a {_fmt_real(evento.preco_anterior)}")
    linhas.append(o.url)
    return "\n".join(linhas)


async def send_message(text: str) -> tuple[bool, Optional[str]]:
    if not settings.whatsapp_configurado:
        return False, "whatsapp nao configurado em .env (WHATSAPP_PHONE/APIKEY vazios)"
    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": settings.whatsapp_phone,
        "text": text,
        "apikey": settings.whatsapp_apikey,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params=params)
        # CallMeBot devolve HTML com "Message queued" em sucesso
        if r.status_code == 200 and "Message queued" in r.text:
            return True, None
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        logger.warning("WhatsApp falhou: %s", e)
        return False, str(e)


async def send_test_message() -> tuple[bool, Optional[str]]:
    return await send_message(
        "✅ *PromoTracker conectado*\n"
        "Voce vai receber promocoes das marcas-alvo aqui."
    )
