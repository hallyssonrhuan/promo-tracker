import asyncio
import hashlib
import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import hishel

from app.config import settings


logger = logging.getLogger(__name__)


@dataclass
class OfertaRaw:
    titulo: str
    preco_atual: float
    url: str
    loja: str
    fonte: str
    preco_de: Optional[float] = None
    desconto_pct: Optional[int] = None
    imagem_url: Optional[str] = None

    @property
    def hash_unico(self) -> str:
        key = f"{self.fonte}|{self.loja}|{self.url}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def normalizar_titulo(s: str) -> str:
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Remove pontuacao que polui o match (",", ".", ";", ":", "!", "?", '"', "'")
    # mas preserva "-" e "/" porque sao significativos em modelos/tamanhos
    s = re.sub(r"[,.;:!?\"']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_preco_br(texto: str) -> Optional[float]:
    if not texto:
        return None
    m = re.search(r"[\d][\d\.\,]*", texto)
    if not m:
        return None
    s = m.group(0)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class Source(ABC):
    nome: str = ""

    def __init__(self) -> None:
        self._semaforo = asyncio.Semaphore(1)

    @abstractmethod
    async def fetch(self) -> list[OfertaRaw]: ...

    def _http_client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": settings.user_agent}
        common = dict(headers=headers, timeout=20.0, follow_redirects=True)
        if settings.dev_mode:
            storage = hishel.AsyncFileStorage(base_path=Path(settings.http_cache_dir))
            controller = hishel.Controller(force_cache=True, allow_stale=True)
            return hishel.AsyncCacheClient(storage=storage, controller=controller, **common)
        return httpx.AsyncClient(**common)

    async def _get(self, client: httpx.AsyncClient, url: str) -> str:
        async with self._semaforo:
            try:
                resp = await client.get(url)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
                raise RuntimeError(f"rede: {type(e).__name__}: {e}") from e
            await asyncio.sleep(settings.throttle_segundos)
        if resp.status_code in (403, 429):
            raise RuntimeError(f"rate-limit (HTTP {resp.status_code}) — IP bloqueado ou quota excedida")
        if resp.status_code >= 500:
            raise RuntimeError(f"upstream HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.text

    def _save_last_html(self, slug: str, html: str) -> None:
        path = Path("data/last_html") / f"{self.nome}_{slug}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
