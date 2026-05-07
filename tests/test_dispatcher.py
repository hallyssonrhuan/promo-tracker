"""Testa o dispatcher multicanal."""

import pytest

from app.matchers.pipeline import OfertaClassificada
from app.notifier import dispatcher as disp_mod
from app.notifier.rules import Evento
from app.notifier.whatsapp import format_evento_text
from app.sources.base import OfertaRaw


def _evento():
    raw = OfertaRaw(
        titulo="Tenis Asics Gel-Cumulus", preco_atual=400, preco_de=800,
        desconto_pct=50, url="https://x/1", loja="Centauro", fonte="promobit",
    )
    oc = OfertaClassificada(oferta=raw, marca="Asics", categoria="corrida")
    return Evento(classificada=oc, tipo="nova", oferta_id=1)


# ---------- format_evento_text (WhatsApp) ----------

def test_format_text_inclui_emojis_e_preco_brl():
    msg = format_evento_text(_evento())
    assert "👟" in msg
    assert "*Tenis Asics Gel-Cumulus*" in msg
    assert "R$ 400,00" in msg
    assert "R$ 800,00" in msg
    assert "50% off" in msg
    assert "https://x/1" in msg


def test_format_text_baixou_inclui_preco_anterior():
    e = _evento()
    e.tipo = "baixou"
    e.preco_anterior = 500
    msg = format_evento_text(e)
    assert "BAIXOU" in msg
    assert "R$ 500,00" in msg


# ---------- dispatcher: 0 canais ----------

async def test_dispatch_sem_canais_retorna_falha(monkeypatch):
    monkeypatch.setattr(disp_mod.settings, "telegram_bot_token", "")
    monkeypatch.setattr(disp_mod.settings, "telegram_chat_id", "")
    monkeypatch.setattr(disp_mod.settings, "whatsapp_phone", "")
    monkeypatch.setattr(disp_mod.settings, "whatsapp_apikey", "")
    ok, erro = await disp_mod.enviar_evento(_evento())
    assert ok is False
    assert "nenhum canal" in erro


# ---------- dispatcher: TG funciona, WA falha → ainda sucesso ----------

async def test_dispatch_sucesso_parcial(monkeypatch):
    monkeypatch.setattr(disp_mod.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(disp_mod.settings, "telegram_chat_id", "y")
    monkeypatch.setattr(disp_mod.settings, "whatsapp_phone", "5511999")
    monkeypatch.setattr(disp_mod.settings, "whatsapp_apikey", "k")

    async def tg_ok(text, parse_mode="HTML"):
        return True, None

    async def wa_falha(text):
        return False, "rate limit"

    monkeypatch.setattr(disp_mod.telegram, "send_message", tg_ok)
    monkeypatch.setattr(disp_mod.whatsapp, "send_message", wa_falha)

    ok, erro = await disp_mod.enviar_evento(_evento())
    assert ok is True  # TG entregou
    assert "whatsapp: rate limit" in erro


# ---------- dispatcher: ambos falham → falha total ----------

async def test_dispatch_ambos_falham(monkeypatch):
    monkeypatch.setattr(disp_mod.settings, "telegram_bot_token", "x")
    monkeypatch.setattr(disp_mod.settings, "telegram_chat_id", "y")
    monkeypatch.setattr(disp_mod.settings, "whatsapp_phone", "x")
    monkeypatch.setattr(disp_mod.settings, "whatsapp_apikey", "k")

    async def fail_tg(text, parse_mode="HTML"):
        return False, "tg down"

    async def fail_wa(text):
        return False, "wa down"

    monkeypatch.setattr(disp_mod.telegram, "send_message", fail_tg)
    monkeypatch.setattr(disp_mod.whatsapp, "send_message", fail_wa)

    ok, erro = await disp_mod.enviar_evento(_evento())
    assert ok is False
    assert "telegram: tg down" in erro
    assert "whatsapp: wa down" in erro
