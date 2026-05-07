"""Dispatcher: dispara um evento pra todos os canais configurados.

Considera sucesso se PELO MENOS UM canal entregou.
Os erros parciais ficam concatenados em `erro` pra registro.
"""

import logging
from typing import Optional

from app.config import settings
from app.notifier import telegram, whatsapp


logger = logging.getLogger(__name__)


async def enviar_evento(evento) -> tuple[bool, Optional[str]]:
    erros: list[str] = []
    enviados: list[str] = []

    if settings.telegram_configurado:
        msg_html = telegram.format_evento_html(evento)
        ok, err = await telegram.send_message(msg_html)
        if ok:
            enviados.append("telegram")
        else:
            erros.append(f"telegram: {err}")

    if settings.whatsapp_configurado:
        msg_text = whatsapp.format_evento_text(evento)
        ok, err = await whatsapp.send_message(msg_text)
        if ok:
            enviados.append("whatsapp")
        else:
            erros.append(f"whatsapp: {err}")

    if not enviados and not erros:
        return False, "nenhum canal configurado (telegram/whatsapp)"

    sucesso_algum = bool(enviados)
    erro_combo = "; ".join(erros) if erros else None
    return sucesso_algum, erro_combo
