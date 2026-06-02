"""Tunnel SSH verso il Postgres del VPS.

Apre `ssh -L LOCAL:127.0.0.1:VPS_DB_PORT user@host -N` come subprocess e lo
mantiene vivo. Il Postgres NON è raggiungibile direttamente dal PC: l'unico
canale è questo tunnel cifrato.
"""

import logging
import socket
import subprocess
import time

from config import Config

log = logging.getLogger("gaia.tunnel")


class SSHTunnel:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None

    def _port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.5)
            return s.connect_ex(("127.0.0.1", self.cfg.local_db_port)) == 0

    def ensure(self) -> None:
        """Garantisce che il tunnel sia attivo; lo (ri)apre se necessario."""
        if self._port_open():
            return
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None

        forward = f"{self.cfg.local_db_port}:127.0.0.1:{self.cfg.vps_db_port}"
        target = f"{self.cfg.vps_ssh_user}@{self.cfg.vps_ssh_host}"
        cmd = [
            "ssh", "-N",
            "-L", forward,
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            target,
        ]
        log.info("apro tunnel SSH: %s -> %s:%s", self.cfg.local_db_port, target, self.cfg.vps_db_port)
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(20):
            if self._port_open():
                log.info("tunnel attivo su 127.0.0.1:%s", self.cfg.local_db_port)
                return
            time.sleep(0.5)
        raise RuntimeError("tunnel SSH non attivo entro il timeout")

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            log.info("tunnel SSH chiuso")
