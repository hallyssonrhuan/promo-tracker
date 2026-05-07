"""Regras de eventos: persiste oferta no Store e decide o que vira notificacao."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from app.config import now_br, settings
from app.matchers.pipeline import OfertaClassificada
from app.sources.base import normalizar_titulo
from app.store import Store


# Queda minima (%) entre ultima coleta e atual pra disparar evento "baixou"
QUEDA_MIN_PCT = 5.0


@dataclass
class Evento:
    classificada: OfertaClassificada
    tipo: str  # "nova" | "baixou"
    oferta_id: int
    preco_anterior: Optional[float] = None


def _get_or_create_produto(store: Store, oc: OfertaClassificada) -> dict:
    norm = normalizar_titulo(oc.oferta.titulo)
    existente = store.get_produto(norm, oc.marca)
    if existente:
        if not existente.get("imagem_url") and oc.oferta.imagem_url:
            store.update_produto(existente["id"], imagem_url=oc.oferta.imagem_url)
        return existente
    return store.add_produto(
        titulo_normalizado=norm,
        titulo_original=oc.oferta.titulo,
        marca=oc.marca,
        categoria=oc.categoria,
        imagem_url=oc.oferta.imagem_url,
        criado_em=now_br(),
    )


def desativar_duplicatas(store: Store, produto_id: int, loja: str) -> int:
    """Pra um (produto, loja), mantem so a Oferta ATIVA de menor preco_atual.
    Desativa as outras. Retorna quantas foram desativadas.
    """
    ofertas = store.list_ofertas_por_produto_loja(produto_id, loja, only_ativas=True)
    if len(ofertas) <= 1:
        return 0
    melhor = min(ofertas, key=lambda o: o["preco_atual"])
    desativadas = 0
    for o in ofertas:
        if o["id"] != melhor["id"]:
            store.update_oferta(o["id"], ativa=False)
            desativadas += 1
    return desativadas


def gerar_eventos(
    classificadas: list[OfertaClassificada],
    store: Store,
) -> list[Evento]:
    """Persiste produto/oferta/historico e devolve eventos pra notificar.

    Side effects no Store:
    - Cria/atualiza Produto, Oferta
    - Sempre adiciona HistoricoPreco
    Devolve eventos ordenados por desconto desc, ja filtrados pra evitar
    re-notificar a mesma oferta+tipo nas ultimas 24h, e capados em
    settings.max_notificacoes_por_job.
    """
    eventos: list[Evento] = []
    agora = now_br()

    for oc in classificadas:
        produto = _get_or_create_produto(store, oc)

        existente = store.get_oferta_by_hash(oc.oferta.hash_unico)

        if existente is None:
            nova = store.add_oferta(
                produto_id=produto["id"],
                fonte=oc.oferta.fonte,
                loja=oc.oferta.loja,
                preco_atual=oc.oferta.preco_atual,
                preco_de=oc.oferta.preco_de,
                desconto_pct=oc.oferta.desconto_pct,
                url=oc.oferta.url,
                hash_unico=oc.oferta.hash_unico,
                ativa=True,
                coletada_em=agora,
            )
            store.add_historico(nova["id"], oc.oferta.preco_atual, agora)

            # DEDUPE: se ja existe outra oferta ativa pro mesmo (produto, loja),
            # mantem so a mais barata. Resolve duplicatas tipo Promobit cria
            # 2 URLs pra mesma oferta da Amazon.
            desativar_duplicatas(store, produto["id"], oc.oferta.loja)

            # So notifica se essa oferta ainda esta ativa apos dedupe
            atual = store.get_oferta_by_id(nova["id"])
            if atual and atual.get("ativa"):
                desc = oc.oferta.desconto_pct or 0
                if desc >= settings.min_desconto_pct:
                    eventos.append(Evento(classificada=oc, tipo="nova", oferta_id=nova["id"]))
        else:
            preco_anterior = existente["preco_atual"]
            store.update_oferta(
                existente["id"],
                preco_atual=oc.oferta.preco_atual,
                preco_de=oc.oferta.preco_de or existente.get("preco_de"),
                desconto_pct=oc.oferta.desconto_pct or existente.get("desconto_pct"),
                atualizada_em=agora,
                ativa=True,
            )
            store.add_historico(existente["id"], oc.oferta.preco_atual, agora)

            if preco_anterior and oc.oferta.preco_atual < preco_anterior:
                queda_pct = (1 - oc.oferta.preco_atual / preco_anterior) * 100
                if queda_pct >= QUEDA_MIN_PCT:
                    eventos.append(Evento(
                        classificada=oc,
                        tipo="baixou",
                        oferta_id=existente["id"],
                        preco_anterior=preco_anterior,
                    ))

            # Re-dedupe apos atualizar preco (talvez agora seja a mais barata)
            desativar_duplicatas(store, produto["id"], oc.oferta.loja)

    eventos = _filtrar_ja_notificados(store, eventos)
    eventos.sort(key=lambda e: -(e.classificada.oferta.desconto_pct or 0))
    return eventos[: settings.max_notificacoes_por_job]


def _filtrar_ja_notificados(store: Store, eventos: list[Evento]) -> list[Evento]:
    desde = now_br() - timedelta(hours=24)
    return [e for e in eventos
            if not store.foi_notificada_recente(e.oferta_id, e.tipo, desde)]


def registrar_envio(store: Store, evento: Evento, sucesso: bool, erro: Optional[str]) -> None:
    store.add_notificacao(
        oferta_id=evento.oferta_id,
        tipo=evento.tipo,
        sucesso=sucesso,
        erro=erro,
        em=now_br(),
    )
