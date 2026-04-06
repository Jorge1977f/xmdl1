"""Sistema de downloads paralelos com threading real."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Callable, Optional

from app.utils.logger import log


@dataclass
class DownloadTask:
    """Representa uma tarefa de download."""
    url: str
    filename: str
    priority: int = 0
    retries: int = 3

    def __lt__(self, other):
        """Para ordenação por prioridade."""
        return self.priority > other.priority


class ParallelDownloadManager:
    """Gerencia downloads paralelos com múltiplas threads."""

    def __init__(self, max_workers: int = 5, timeout: int = 300):
        """Inicializa o gerenciador."""
        self.max_workers = max_workers
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks = {}
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._completed = 0
        self._failed = 0
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Define callback para progresso (completed, total, message)."""
        self._progress_callback = callback

    def submit_task(
        self,
        url: str,
        filename: str,
        download_func: Callable,
        priority: int = 0,
        retries: int = 3,
    ) -> None:
        """Submete uma tarefa de download."""
        task = DownloadTask(url=url, filename=filename, priority=priority, retries=retries)
        future = self._executor.submit(
            self._execute_download,
            task,
            download_func,
        )
        with self._lock:
            self._tasks[filename] = future

    def _execute_download(self, task: DownloadTask, download_func: Callable) -> bool:
        """Executa o download com retry."""
        for attempt in range(task.retries):
            if self._cancel_event.is_set():
                log.info(f"Download de {task.filename} cancelado")
                return False

            try:
                log.debug(f"Iniciando download: {task.filename} (tentativa {attempt + 1}/{task.retries})")
                result = download_func(task.url, task.filename)
                
                with self._lock:
                    self._completed += 1
                
                if self._progress_callback:
                    self._progress_callback(
                        self._completed,
                        len(self._tasks),
                        f"✅ {task.filename} baixado"
                    )
                
                log.info(f"✅ Download concluído: {task.filename}")
                return result

            except Exception as exc:
                log.warning(f"Erro no download de {task.filename} (tentativa {attempt + 1}): {exc}")
                if attempt < task.retries - 1:
                    time.sleep(2 ** attempt)  # Backoff exponencial
                else:
                    with self._lock:
                        self._failed += 1
                    if self._progress_callback:
                        self._progress_callback(
                            self._completed,
                            len(self._tasks),
                            f"❌ Falha em {task.filename}"
                        )
                    log.error(f"❌ Falha final em {task.filename}: {exc}")
                    return False

        return False

    def wait_all(self, timeout: Optional[int] = None) -> dict:
        """Aguarda conclusão de todos os downloads."""
        timeout = timeout or self.timeout
        results = {}
        
        try:
            for filename, future in self._tasks.items():
                try:
                    result = future.result(timeout=timeout)
                    results[filename] = result
                except Exception as exc:
                    log.error(f"Erro ao aguardar {filename}: {exc}")
                    results[filename] = False

        finally:
            self._executor.shutdown(wait=True)

        return results

    def request_cancel(self) -> None:
        """Solicita cancelamento de todos os downloads."""
        log.info("Cancelamento de downloads solicitado")
        self._cancel_event.set()

    def get_stats(self) -> dict:
        """Retorna estatísticas dos downloads."""
        with self._lock:
            return {
                "total": len(self._tasks),
                "completed": self._completed,
                "failed": self._failed,
                "pending": len(self._tasks) - self._completed - self._failed,
            }

    def reset(self) -> None:
        """Reseta o gerenciador."""
        self._cancel_event.clear()
        self._completed = 0
        self._failed = 0
        self._tasks = {}
        log.info("Gerenciador de downloads resetado")
