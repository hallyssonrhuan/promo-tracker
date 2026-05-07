"""Entry point: roda 1 ciclo completo coleta + revalidacao.

Chamado pelo GitHub Actions cron a cada 5 min:
  python -m scripts.run_check

Carrega state.json, executa pipeline, persiste state.json. Se rodando local
sem TELEGRAM_BOT_TOKEN configurado, envio sera simplesmente um no-op com
log de aviso (Store atualiza normalmente).
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# garantir que `import app...` funcione quando script roda direto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.coleta import executar_coleta  # noqa: E402
from app.config import settings  # noqa: E402
from app.revalidator import revalidar_ofertas_ativas  # noqa: E402
from app.store import Store  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_check")


STATE_PATH = Path(os.environ.get("STATE_PATH", "data/state.json"))


async def main() -> int:
    if not settings.telegram_configurado:
        logger.warning(
            "Telegram nao configurado (TELEGRAM_BOT_TOKEN/CHAT_ID). "
            "Pipeline vai rodar mas sem notificar."
        )

    store = Store(STATE_PATH)
    logger.info("[run_check] state.json: %s (ofertas existentes: %d)",
                STATE_PATH, len(store.raw().get("ofertas", {})))

    coleta = await executar_coleta(store)
    logger.info("[run_check] resumo coleta: %s", coleta)

    revalid = await revalidar_ofertas_ativas(store)
    logger.info("[run_check] resumo revalidacao: %s", revalid)

    store.flush()
    logger.info("[run_check] state.json salvo (ofertas: %d, notificacoes: %d)",
                len(store.raw().get("ofertas", {})),
                len(store.raw().get("notificacoes", [])))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
