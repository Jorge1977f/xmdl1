"""Sistema de checkpoint para preservar downloads já importados."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

from app.utils.logger import log


class DownloadCheckpoint:
    """Gerencia checkpoint de downloads para preservação em caso de cancelamento."""

    def __init__(self, checkpoint_dir: Path):
        """Inicializa o checkpoint."""
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.checkpoint_dir / ".download_checkpoint.json"
        self._lock = Lock()
        self._data = self._load_checkpoint()

    def _load_checkpoint(self) -> dict:
        """Carrega checkpoint do arquivo."""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as exc:
                log.warning(f"Erro ao carregar checkpoint: {exc}")
                return {}
        return {}

    def _save_checkpoint(self) -> None:
        """Salva checkpoint no arquivo."""
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as exc:
            log.error(f"Erro ao salvar checkpoint: {exc}")

    def mark_downloaded(self, filename: str, size: int = 0) -> None:
        """Marca um arquivo como baixado."""
        with self._lock:
            self._data[filename] = {
                "status": "downloaded",
                "timestamp": datetime.utcnow().isoformat(),
                "size": size,
            }
            self._save_checkpoint()
            log.debug(f"Checkpoint: {filename} marcado como baixado")

    def mark_imported(self, filename: str) -> None:
        """Marca um arquivo como importado."""
        with self._lock:
            if filename in self._data:
                self._data[filename]["status"] = "imported"
                self._save_checkpoint()
                log.debug(f"Checkpoint: {filename} marcado como importado")

    def mark_failed(self, filename: str, error: str = "") -> None:
        """Marca um arquivo como falhado."""
        with self._lock:
            self._data[filename] = {
                "status": "failed",
                "timestamp": datetime.utcnow().isoformat(),
                "error": error,
            }
            self._save_checkpoint()
            log.debug(f"Checkpoint: {filename} marcado como falhado")

    def get_status(self, filename: str) -> Optional[str]:
        """Retorna o status de um arquivo."""
        return self._data.get(filename, {}).get("status")

    def get_downloaded_files(self) -> list[str]:
        """Retorna lista de arquivos baixados."""
        return [
            f for f, data in self._data.items()
            if data.get("status") in ("downloaded", "imported")
        ]

    def get_imported_files(self) -> list[str]:
        """Retorna lista de arquivos importados."""
        return [
            f for f, data in self._data.items()
            if data.get("status") == "imported"
        ]

    def get_failed_files(self) -> list[str]:
        """Retorna lista de arquivos falhados."""
        return [
            f for f, data in self._data.items()
            if data.get("status") == "failed"
        ]

    def get_summary(self) -> dict:
        """Retorna resumo do checkpoint."""
        return {
            "total": len(self._data),
            "downloaded": len(self.get_downloaded_files()),
            "imported": len(self.get_imported_files()),
            "failed": len(self.get_failed_files()),
        }

    def clear(self) -> None:
        """Limpa o checkpoint."""
        with self._lock:
            self._data = {}
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
            log.info("Checkpoint limpo")

    def should_skip_file(self, filename: str) -> bool:
        """Verifica se um arquivo já foi importado e deve ser pulado."""
        status = self.get_status(filename)
        return status == "imported"
