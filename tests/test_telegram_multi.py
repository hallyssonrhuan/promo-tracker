"""Testa o envio multi-chat do Telegram (TELEGRAM_CHAT_ID em CSV)."""

import httpx

from app.notifier import telegram as tg


def _setup(monkeypatch, chat_id_str, transport):
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(tg.settings, "telegram_chat_id", chat_id_str)
    real = httpx.AsyncClient

    def fake(*a, **kw):
        kw["transport"] = transport
        return real(*a, **kw)

    monkeypatch.setattr(tg.httpx, "AsyncClient", fake)


def test_chat_ids_parser_csv(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "111, 222 ,333")
    assert tg.settings.telegram_chat_ids == ["111", "222", "333"]


def test_chat_ids_parser_unico(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "777")
    assert tg.settings.telegram_chat_ids == ["777"]


def test_chat_ids_vazio(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "")
    assert tg.settings.telegram_chat_ids == []


async def test_envio_multi_todos_sucesso(monkeypatch):
    enviadas_pra: list[str] = []

    def handler(req):
        body = req.read().decode()
        import json
        chat = json.loads(body)["chat_id"]
        enviadas_pra.append(chat)
        return httpx.Response(200, json={"ok": True})

    _setup(monkeypatch, "111,222,333", httpx.MockTransport(handler))
    ok, erro = await tg.send_message("oi")
    assert ok is True
    assert erro is None
    assert enviadas_pra == ["111", "222", "333"]


async def test_envio_multi_um_falha_resto_passa(monkeypatch):
    def handler(req):
        body = req.read().decode()
        import json
        chat = json.loads(body)["chat_id"]
        if chat == "222":
            return httpx.Response(400, json={"description": "chat not found"})
        return httpx.Response(200, json={"ok": True})

    _setup(monkeypatch, "111,222,333", httpx.MockTransport(handler))
    ok, erro = await tg.send_message("oi")
    assert ok is True  # 2 dos 3 deram certo
    assert "parcial" in erro
    assert "222" in erro


async def test_envio_multi_todos_falham(monkeypatch):
    def handler(req):
        return httpx.Response(401, json={"description": "unauthorized"})

    _setup(monkeypatch, "111,222", httpx.MockTransport(handler))
    ok, erro = await tg.send_message("oi")
    assert ok is False
    assert "111" in erro and "222" in erro
