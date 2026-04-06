"""Gerenciador de downloads paralelos otimizado para múltiplos XMLs."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.utils.logger import log


@dataclass
class DownloadTask:
    """Representa uma tarefa de download."""
    url: str
    filename: str
    download_dir: Path
    task_id: str
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    timeout: int = 30
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "PENDENTE"
    error_message: str = ""
    file_size: int = 0


@dataclass
class DownloadResult:
    """Resultado de um download."""
    task_id: str
    success: bool
    filepath: Optional[Path] = None
    file_size: int = 0
    duration: float = 0.0
    error_message: str = ""
    retry_count: int = 0


class ParallelDownloadManager:
    """Gerencia downloads paralelos com controle de concorrência."""

    def __init__(
        self,
        max_workers: int = 5,
        timeout: int = 30,
        cache_dir: Optional[Path] = None,
        use_cache: bool = True,
    ):
        """
        Inicializa o gerenciador de downloads.

        Args:
            max_workers: Número máximo de downloads simultâneos
            timeout: Timeout em segundos para cada download
            cache_dir: Diretório para cache de downloads
            use_cache: Se deve usar cache local
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.cache_dir = cache_dir or Path.home() / ".xmdl_cache"
        self.use_cache = use_cache
        self.tasks: dict[str, DownloadTask] = {}
        self.results: dict[str, DownloadResult] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def add_task(
        self,
        url: str,
        filename: str,
        download_dir: Path,
        task_id: str,
        priority: int = 0,
    ) -> DownloadTask:
        """Adiciona uma tarefa de download à fila."""
        task = DownloadTask(
            url=url,
            filename=filename,
            download_dir=download_dir,
            task_id=task_id,
            priority=priority,
            timeout=self.timeout,
        )
        self.tasks[task_id] = task
        return task

    def execute_all(
        self,
        download_func: Callable[[DownloadTask], DownloadResult],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[DownloadResult]:
        """
        Executa todos os downloads em paralelo.

        Args:
            download_func: Função que executa o download (recebe DownloadTask)
            progress_callback: Função chamada com (completados, total)

        Returns:
            Lista de resultados dos downloads
        """
        if not self.tasks:
            return []

        total_tasks = len(self.tasks)
        completed = 0
        results_list: list[DownloadResult] = []

        sorted_tasks = sorted(
            self.tasks.values(),
            key=lambda t: (-t.priority, t.created_at),
        )

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_task = {
                    executor.submit(download_func, task): task
                    for task in sorted_tasks
                }

                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        result = future.result(timeout=self.timeout + 5)
                        self.results[task.task_id] = result
                        results_list.append(result)
                        completed += 1

                        if progress_callback:
                            progress_callback(completed, total_tasks)

                    except Exception as exc:
                        log.error(f"Erro ao executar download {task.task_id}: {exc}")
                        error_result = DownloadResult(
                            task_id=task.task_id,
                            success=False,
                            error_message=str(exc),
                        )
                        self.results[task.task_id] = error_result
                        results_list.append(error_result)
                        completed += 1

                        if progress_callback:
                            progress_callback(completed, total_tasks)

        except Exception as exc:
            log.error(f"Erro crítico no gerenciador de downloads: {exc}")

        return results_list

    def get_cache_path(self, url: str, filename: str) -> Path:
        """Retorna o caminho do arquivo em cache."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return self.cache_dir / f"{url_hash}_{filename}"

    def cache_exists(self, url: str, filename: str) -> bool:
        """Verifica se um arquivo está em cache."""
        if not self.use_cache:
            return False
        cache_path = self.get_cache_path(url, filename)
        return cache_path.exists()

    def get_cached_file(self, url: str, filename: str) -> Optional[Path]:
        """Retorna o caminho do arquivo em cache se existir."""
        cache_path = self.get_cache_path(url, filename)
        if cache_path.exists():
            return cache_path
        return None

    def get_statistics(self) -> dict[str, Any]:
        """Retorna estatísticas dos downloads."""
        if not self.results:
            return {
                "total": 0,
                "sucesso": 0,
                "erro": 0,
                "taxa_sucesso": 0.0,
                "tempo_total": 0.0,
                "tempo_medio": 0.0,
            }

        total = len(self.results)
        sucesso = sum(1 for r in self.results.values() if r.success)
        erro = total - sucesso
        tempo_total = sum(r.duration for r in self.results.values())
        tempo_medio = tempo_total / total if total > 0 else 0

        return {
            "total": total,
            "sucesso": sucesso,
            "erro": erro,
            "taxa_sucesso": (sucesso / total * 100) if total > 0 else 0,
            "tempo_total": tempo_total,
            "tempo_medio": tempo_medio,
        }

    def reset(self) -> None:
        """Reseta o gerenciador para novo lote de downloads."""
        self.tasks.clear()
        self.results.clear()

    def __del__(self):
        """Limpa recursos ao destruir o objeto."""
        try:
            self.executor.shutdown(wait=False)
        except Exception:
            pass
