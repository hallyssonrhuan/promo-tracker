from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


BR_TZ = ZoneInfo("America/Sao_Paulo")


def now_br() -> datetime:
    return datetime.now(BR_TZ)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # WhatsApp via CallMeBot (https://www.callmebot.com/blog/free-api-whatsapp-messages/)
    # Telefone com codigo do pais SEM '+', ex: "5511999999999"
    whatsapp_phone: str = ""
    whatsapp_apikey: str = ""

    state_path: str = "data/state.json"
    http_cache_dir: str = "./data/http_cache"
    user_agent: str = "PromoTracker/0.1 (uso pessoal)"

    min_desconto_pct: int = 15
    max_notificacoes_por_job: int = 10
    throttle_segundos: int = 3

    dev_mode: bool = False

    @property
    def telegram_chat_ids(self) -> list[str]:
        """Aceita CSV: '123,456,-1001234567890' (chats individuais ou grupo/canal)."""
        return [c.strip() for c in self.telegram_chat_id.split(",") if c.strip()]

    @property
    def telegram_configurado(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_ids)

    @property
    def whatsapp_configurado(self) -> bool:
        return bool(self.whatsapp_phone and self.whatsapp_apikey)

    def ensure_data_dirs(self) -> None:
        Path("data").mkdir(exist_ok=True)
        Path(self.http_cache_dir).mkdir(parents=True, exist_ok=True)
        Path("data/last_html").mkdir(parents=True, exist_ok=True)


settings = Settings()
