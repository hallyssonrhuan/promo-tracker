"""JSON-backed state store. Substitui SQLModel/SQLite.

O `state.json` e versionado no proprio repo: cada run do GitHub Actions le,
processa, escreve, commita. Sem banco, sem servidor sempre ligado.

Estrutura:
{
  "produtos":         {"1": {...}, "2": {...}},
  "ofertas":          {"1": {...}},  # keyed por id; hash_unico dentro
  "historico_preco":  [{...}],
  "notificacoes":     [{...}],
  "fontes":           {"promobit": {...}},
  "_next_id":         {"produto": N, "oferta": N}
}
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _ser(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s)


def _empty_state() -> dict:
    return {
        "produtos": {},
        "ofertas": {},
        "historico_preco": [],
        "notificacoes": [],
        "fontes": {},
        "_next_id": {"produto": 1, "oferta": 1},
    }


class Store:
    """Wrapper sobre state.json com API tipo repository.

    Toda mudanca acontece em memoria; chame `flush()` no fim do run pra
    persistir atomicamente no disco (write tmp + rename).
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return _empty_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return _empty_state()
        # Backfill chaves novas em state.json antigo
        base = _empty_state()
        for k, v in base.items():
            data.setdefault(k, v)
        for k in base["_next_id"]:
            data["_next_id"].setdefault(k, 1)
        return data

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def raw(self) -> dict:
        return self._data

    def _next(self, kind: str) -> int:
        n = self._data["_next_id"][kind]
        self._data["_next_id"][kind] = n + 1
        return n

    # ----- produtos -----

    def get_produto(self, titulo_normalizado: str, marca: str) -> Optional[dict]:
        for p in self._data["produtos"].values():
            if p["titulo_normalizado"] == titulo_normalizado and p["marca"] == marca:
                return p
        return None

    def get_produto_by_id(self, id: int) -> Optional[dict]:
        return self._data["produtos"].get(str(id))

    def add_produto(self, *, titulo_normalizado: str, titulo_original: str,
                    marca: str, categoria: str, imagem_url: Optional[str],
                    criado_em: datetime) -> dict:
        id = self._next("produto")
        p = {
            "id": id,
            "titulo_normalizado": titulo_normalizado,
            "titulo_original": titulo_original,
            "marca": marca,
            "categoria": categoria,
            "imagem_url": imagem_url,
            "criado_em": _ser(criado_em),
        }
        self._data["produtos"][str(id)] = p
        return p

    def update_produto(self, id: int, **kwargs) -> None:
        p = self._data["produtos"][str(id)]
        for k, v in kwargs.items():
            p[k] = _ser(v)

    # ----- ofertas -----

    def get_oferta_by_hash(self, hash_unico: str) -> Optional[dict]:
        for o in self._data["ofertas"].values():
            if o["hash_unico"] == hash_unico:
                return o
        return None

    def get_oferta_by_id(self, id: int) -> Optional[dict]:
        return self._data["ofertas"].get(str(id))

    def add_oferta(self, *, produto_id: int, fonte: str, loja: str,
                   preco_atual: float, preco_de: Optional[float],
                   desconto_pct: Optional[int], url: str, hash_unico: str,
                   ativa: bool, coletada_em: datetime) -> dict:
        id = self._next("oferta")
        o = {
            "id": id,
            "produto_id": produto_id,
            "fonte": fonte,
            "loja": loja,
            "preco_atual": preco_atual,
            "preco_de": preco_de,
            "desconto_pct": desconto_pct,
            "url": url,
            "hash_unico": hash_unico,
            "ativa": ativa,
            "coletada_em": _ser(coletada_em),
            "atualizada_em": _ser(coletada_em),
        }
        self._data["ofertas"][str(id)] = o
        return o

    def update_oferta(self, id: int, **kwargs) -> None:
        o = self._data["ofertas"][str(id)]
        for k, v in kwargs.items():
            o[k] = _ser(v)

    def list_ofertas_ativas(self) -> list[dict]:
        return [o for o in self._data["ofertas"].values() if o.get("ativa")]

    def list_ofertas_por_produto_loja(self, produto_id: int, loja: str,
                                      only_ativas: bool = True) -> list[dict]:
        out = []
        for o in self._data["ofertas"].values():
            if o["produto_id"] != produto_id:
                continue
            if o["loja"] != loja:
                continue
            if only_ativas and not o.get("ativa"):
                continue
            out.append(o)
        return out

    # ----- historico -----

    def add_historico(self, oferta_id: int, preco: float, em: datetime) -> None:
        self._data["historico_preco"].append({
            "oferta_id": oferta_id,
            "preco": preco,
            "registrado_em": _ser(em),
        })

    # ----- notificacoes -----

    def add_notificacao(self, oferta_id: int, tipo: str, sucesso: bool,
                        erro: Optional[str], em: datetime) -> None:
        self._data["notificacoes"].append({
            "oferta_id": oferta_id,
            "tipo": tipo,
            "enviada_em": _ser(em),
            "sucesso": sucesso,
            "erro": erro,
        })

    def foi_notificada_recente(self, oferta_id: int, tipo: str,
                               desde: datetime) -> bool:
        for n in self._data["notificacoes"]:
            if n["oferta_id"] != oferta_id or n["tipo"] != tipo:
                continue
            if not n.get("sucesso"):
                continue
            enviada = _parse_dt(n["enviada_em"])
            if enviada and enviada >= desde:
                return True
        return False

    # ----- fontes -----

    def get_fonte(self, nome: str) -> dict:
        f = self._data["fontes"].get(nome)
        if f is None:
            f = {
                "nome": nome,
                "ativa": True,
                "ultima_coleta_em": None,
                "ultima_coleta_status": None,
                "ultima_coleta_erro": None,
                "ultima_coleta_qtd": 0,
            }
            self._data["fontes"][nome] = f
        return f

    def update_fonte(self, nome: str, **kwargs) -> None:
        f = self.get_fonte(nome)
        for k, v in kwargs.items():
            f[k] = _ser(v)
