import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _parse_chat_ids(raw: str) -> set[int]:
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    authorized_chat_ids: set[int]
    davide_chat_id: int | None
    ascanio_chat_id: int | None
    briefing_hour: int
    briefing_timezone: str
    log_level: str

    @classmethod
    def load(cls) -> "Config":
        bot_token = os.environ["BOT_TOKEN"]
        database_url = os.environ["DATABASE_URL"]
        authorized = _parse_chat_ids(os.environ.get("AUTHORIZED_CHAT_IDS", ""))
        davide = os.environ.get("DAVIDE_CHAT_ID")
        ascanio = os.environ.get("ASCANIO_CHAT_ID")
        return cls(
            bot_token=bot_token,
            database_url=database_url,
            authorized_chat_ids=authorized,
            davide_chat_id=int(davide) if davide else None,
            ascanio_chat_id=int(ascanio) if ascanio else None,
            briefing_hour=int(os.environ.get("BRIEFING_HOUR", "7")),
            briefing_timezone=os.environ.get("BRIEFING_TIMEZONE", "Europe/Rome"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )

    def socio_for(self, chat_id: int) -> str | None:
        if chat_id == self.davide_chat_id:
            return "davide"
        if chat_id == self.ascanio_chat_id:
            return "ascanio"
        return None

    def is_authorized(self, chat_id: int) -> bool:
        if not self.authorized_chat_ids:
            return False
        return chat_id in self.authorized_chat_ids
