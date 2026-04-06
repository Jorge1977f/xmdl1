"""Gerenciador seguro de downloads que preserva arquivos mesmo com cancelamento."""
from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.utils.logger import log


@dataclass
class SafeDownloadResult:
    """Resultado de um download seguro."""
    success: bool
    filepath: Optional[Path] = None
    file_size: int = 0
    duration: float = 0.0
    error_message: str = ""


class SafeDownloadManager:
    """Gerencia downloads com preservação automática de arquivos."""

    def __init__(
        self,
        max_workers: int = 5,
        timeout: int = 30,
        preserve_on_cancel: bool = True,
    ):
        """
        Inicializa o gerenciador.

        Args:
            max_workers: Número máximo de downloads simultâneos
            timeout: Timeout em segundos
            preserve_on_cancel: Se deve preservar arquivos ao cancelar
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.preserve_on_cancel = preserve_on_cancel
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_downloads: dict[str, Path] = {}
        self.completed_downloads: dict[str, Path] = {}
        self.lock = threading.Lock()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Solicita cancelamento."""
        self._cancel_requested = True
        log.info("Cancelamento solicitado. Preservando downloads completados...")

    def is_cancel_requested(self) -> bool:
        """Verifica se cancelamento foi solicitado."""
        return self._cancel_requested

    def register_download(self, task_id: str, filepath: Path) -> None:
        """Registra um download ativo."""
        with self.lock:
            self.active_downloads[task_id] = filepath

    def mark_completed(self, task_id: str) -> None:
        """Marca um download como completado."""
        with self.lock:
            if task_id in self.active_downloads:
                filepath = self.active_downloads.pop(task_id)
                self.completed_downloads[task_id] = filepath
                log.debug(f"Download completado e preservado: {filepath}")

    def mark_failed(self, task_id: str) -> None:
        """Marca um download como falhado."""
        with self.lock:
            self.active_downloads.pop(task_id, None)

    def get_completed_downloads(self) -> dict[str, Path]:
        """Retorna todos os downloads completados."""
        with self.lock:
            return dict(self.completed_downloads)

    def get_active_downloads(self) -> dict[str, Path]:
        """Retorna todos os downloads ativos."""
        with self.lock:
            return dict(self.active_downloads)

    def preserve_downloads(self, dest_dir: Path) -> int:
        """
        Preserva todos os downloads completados em um diretório.

        Args:
            dest_dir: Diretório de destino

        Returns:
            Número de arquivos preservados
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        preserved = 0

        with self.lock:
            for task_id, filepath in self.completed_downloads.items():
                if filepath and filepath.exists():
                    try:
                        dest_file = dest_dir / filepath.name
                        shutil.copy2(filepath, dest_file)
                        preserved += 1
                        log.info(f"Arquivo preservado: {dest_file}")
                    except Exception as exc:
                        log.error(f"Erro ao preservar {filepath}: {exc}")

        return preserved

    def cleanup_active(self) -> int:
        """
        Remove apenas downloads incompletos.

        Returns:
            Número de arquivos removidos
        """
        removed = 0

        with self.lock:
            for task_id, filepath in list(self.active_downloads.items()):
                if filepath and filepath.exists():
                    try:
                        filepath.unlink()
                        removed += 1
                        log.debug(f"Arquivo incompleto removido: {filepath}")
                    except Exception as exc:
                        log.warning(f"Erro ao remover {filepath}: {exc}")
            self.active_downloads.clear()

        return removed

    def cleanup_all(self) -> int:
        """
        Remove todos os downloads (completados e incompletos).

        Returns:
            Número de arquivos removidos
        """
        removed = 0

        with self.lock:
            # Remove ativos
            for filepath in self.active_downloads.values():
                if filepath and filepath.exists():
                    try:
                        filepath.unlink()
                        removed += 1
                    except Exception:
                        pass

            # Remove completados
            for filepath in self.completed_downloads.values():
                if filepath and filepath.exists():
                    try:
                        filepath.unlink()
                        removed += 1
                    except Exception:
                        pass

            self.active_downloads.clear()
            self.completed_downloads.clear()

        return removed

    def get_statistics(self) -> dict:
        """Retorna estatísticas dos downloads."""
        with self.lock:
            total_active = len(self.active_downloads)
            total_completed = len(self.completed_downloads)
            total_size = sum(
                p.stat().st_size for p in self.completed_downloads.values()
                if p and p.exists()
            )

        return {
            "active": total_active,
            "completed": total_completed,
            "total": total_active + total_completed,
            "total_size_mb": total_size / (1024 * 1024),
        }

    def reset(self) -> None:
        """Reseta o gerenciador."""
        with self.lock:
            self.active_downloads.clear()
            self.completed_downloads.clear()
        self._cancel_requested = False

    def __del__(self):
        """Limpa recursos."""
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
