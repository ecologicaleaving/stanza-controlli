"""Config del cervello Gaia (legge brain/.env)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


@dataclass(frozen=True)
class Config:
    vps_ssh_user: str
    vps_ssh_host: str
    vps_db_port: int
    local_db_port: int
    pg_user: str
    pg_password: str
    pg_database: str
    group_chat_id: int
    el_repo_path: str
    poll_interval_sec: int
    context_msgs: int
    model: str

    @classmethod
    def load(cls) -> "Config":
        return cls(
            vps_ssh_user=os.environ.get("VPS_SSH_USER", "root"),
            vps_ssh_host=os.environ["VPS_SSH_HOST"],
            vps_db_port=int(os.environ.get("VPS_DB_PORT", "54362")),
            local_db_port=int(os.environ.get("LOCAL_DB_PORT", "15432")),
            pg_user=os.environ.get("PGUSER", "postgres"),
            pg_password=os.environ.get("PGPASSWORD", "postgres"),
            pg_database=os.environ.get("PGDATABASE", "postgres"),
            group_chat_id=int(os.environ["GROUP_CHAT_ID"]),
            el_repo_path=os.environ["EL_REPO_PATH"],
            poll_interval_sec=int(os.environ.get("POLL_INTERVAL_SEC", "60")),
            context_msgs=int(os.environ.get("CONTEXT_MSGS", "20")),
            model=os.environ.get("MODEL", "claude-sonnet-4-6"),
        )
