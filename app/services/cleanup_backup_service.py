"""
Serviço de Limpeza, Backup e Restauração de dados (XMLs, PDFs, JSONs).

Funcionalidades:
- Limpeza de XMLs, PDFs e JSONs por período
- Backup automático antes de limpeza
- Restauração de dados a partir de backup
- Log de operações
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass, asdict

from app.utils.logger import log


@dataclass
class OperacaoLimpeza:
    """Registro de uma operação de limpeza."""
    id: str
    tipo: str  # 'LIMPEZA', 'BACKUP', 'RESTAURACAO'
    data_operacao: datetime
    periodo_inicio: Optional[date]
    periodo_fim: Optional[date]
    tipos_arquivo: List[str]  # ['XML', 'PDF', 'JSON']
    empresa_id: Optional[int]
    quantidade_arquivos: int
    tamanho_bytes: int
    backup_path: Optional[str]
    status: str  # 'SUCESSO', 'ERRO', 'PARCIAL'
    mensagem: str
    usuario: Optional[str]


class CleanupBackupService:
    """Serviço de gerenciamento de limpeza, backup e restauração de dados."""

    DOC_EXTENSIONS = {
        'XML': {'.xml'},
        'PDF': {'.pdf'},
        'JSON': {'.json'},
    }
    INTERNAL_EXTENSIONS = {
        '.db', '.sqlite', '.sqlite3', '.json', '.pem', '.pfx', '.p12', '.cer', '.crt', '.key', '.lic', '.txt'
    }

    def __init__(self, base_data_dir: Path | str = None):
        """
        Inicializa o serviço.

        Args:
            base_data_dir: Diretório base onde os dados estão armazenados
        """
        from config.settings import (
            DATA_DIR,
            PROJECT_ROOT,
            DOWNLOADS_DIR,
            DB_DIR,
            CACHE_DIR,
            CERTIFICATES_DIR,
            LOGS_DIR,
            XML_DIR,
        )

        self.base_data_dir = Path(base_data_dir) if base_data_dir else DATA_DIR
        self.project_root = PROJECT_ROOT
        self.downloads_dir = Path(DOWNLOADS_DIR)
        self.db_dir = Path(DB_DIR)
        self.cache_dir = Path(CACHE_DIR)
        self.certificates_dir = Path(CERTIFICATES_DIR)
        self.logs_dir = Path(LOGS_DIR)
        self.xml_dir = Path(XML_DIR)

        self.backup_dir = self.base_data_dir / 'backups'
        self.log_dir = self.base_data_dir / 'logs_limpeza'

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.operacoes: List[OperacaoLimpeza] = []
        self._progress: Dict[str, Any] = {
            "active": False,
            "phase": "",
            "current": 0,
            "total": 0,
            "percent": 0,
            "detail": "",
        }
        self._carregar_log_operacoes()


    def _set_progress(self, *, active: Optional[bool] = None, phase: Optional[str] = None, current: Optional[int] = None, total: Optional[int] = None, detail: Optional[str] = None) -> None:
        if active is not None:
            self._progress['active'] = active
        if phase is not None:
            self._progress['phase'] = phase
        if current is not None:
            self._progress['current'] = current
        if total is not None:
            self._progress['total'] = total
        if detail is not None:
            self._progress['detail'] = detail
        total_value = int(self._progress.get('total') or 0)
        current_value = int(self._progress.get('current') or 0)
        self._progress['percent'] = int((current_value / total_value) * 100) if total_value > 0 else 0

    def _clear_progress(self) -> None:
        self._progress = {
            'active': False,
            'phase': '',
            'current': 0,
            'total': 0,
            'percent': 0,
            'detail': '',
        }

    def get_progress(self) -> Dict[str, Any]:
        return dict(self._progress)

    def _carregar_log_operacoes(self) -> None:
        """Carrega o log de operações anteriores."""
        log_file = self.log_dir / 'operacoes.json'
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    for item in dados:
                        item['data_operacao'] = datetime.fromisoformat(item['data_operacao'])
                        if item.get('periodo_inicio'):
                            item['periodo_inicio'] = datetime.fromisoformat(item['periodo_inicio']).date()
                        if item.get('periodo_fim'):
                            item['periodo_fim'] = datetime.fromisoformat(item['periodo_fim']).date()
                        self.operacoes.append(OperacaoLimpeza(**item))
            except Exception as e:
                log.warning(f"Erro ao carregar log de operações: {e}")

    def _salvar_log_operacoes(self) -> None:
        """Salva o log de operações."""
        log_file = self.log_dir / 'operacoes.json'
        try:
            dados = []
            for op in self.operacoes:
                item = asdict(op)
                item['data_operacao'] = item['data_operacao'].isoformat()
                if item.get('periodo_inicio'):
                    item['periodo_inicio'] = item['periodo_inicio'].isoformat()
                if item.get('periodo_fim'):
                    item['periodo_fim'] = item['periodo_fim'].isoformat()
                dados.append(item)

            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Erro ao salvar log de operações: {e}")

    def _is_relative_to(self, child: Path, parent: Path) -> bool:
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except Exception:
            return False

    def _exclude_dirs(self) -> List[Path]:
        return [self.backup_dir, self.log_dir, self.logs_dir]

    def _iter_roots(self) -> List[Path]:
        roots: List[Path] = []
        for candidate in [self.base_data_dir, self.downloads_dir]:
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
            if all(resolved != existing.resolve() for existing in roots):
                roots.append(candidate)
        return roots

    def _matches_period(self, arquivo: Path, periodo_inicio: Optional[date], periodo_fim: Optional[date]) -> bool:
        if not periodo_inicio and not periodo_fim:
            return True
        try:
            mtime = datetime.fromtimestamp(arquivo.stat().st_mtime).date()
        except Exception:
            return False
        if periodo_inicio and mtime < periodo_inicio:
            return False
        if periodo_fim and mtime > periodo_fim:
            return False
        return True

    def _should_skip(self, arquivo: Path, destino_backup: Optional[Path] = None) -> bool:
        try:
            resolved = arquivo.resolve()
        except Exception:
            resolved = arquivo

        if destino_backup:
            try:
                if resolved == destino_backup.resolve():
                    return True
            except Exception:
                pass

        for excluded in self._exclude_dirs():
            if excluded.exists() and self._is_relative_to(resolved, excluded):
                return True

        return '__pycache__' in resolved.parts

    def _is_internal_file(self, arquivo: Path) -> bool:
        ext = arquivo.suffix.lower()
        if ext in self.INTERNAL_EXTENSIONS and (
            self._is_relative_to(arquivo, self.db_dir)
            or self._is_relative_to(arquivo, self.cache_dir)
            or self._is_relative_to(arquivo, self.certificates_dir)
        ):
            return True

        if ext == '.json' and self._is_relative_to(arquivo, self.base_data_dir):
            return True

        return False

    def _is_cleanable_document(self, arquivo: Path, tipo: str) -> bool:
        tipo_upper = (tipo or '').upper()
        if tipo_upper != 'JSON':
            return True

        # Não apagar cadastros, banco, cache, licença, certificados ou configurações do sistema.
        protected_paths = [self.db_dir, self.cache_dir, self.certificates_dir, self.backup_dir, self.log_dir, self.logs_dir]
        for protected in protected_paths:
            if protected.exists() and self._is_relative_to(arquivo, protected):
                return False

        protected_names = {
            'empresas.json', 'operacoes.json', 'municipios_ibge.json',
            'config.json', 'configuracoes.json', 'license_state.json',
        }
        if arquivo.name.lower() in protected_names:
            return False

        # JSON de limpeza fica restrito aos diretórios de documentos.
        return self._is_relative_to(arquivo, self.downloads_dir) or self._is_relative_to(arquivo, self.xml_dir)


    def _empresa_folder_name(self, empresa_id: Optional[int]) -> Optional[str]:
        if not empresa_id:
            return None
        return f"empresa_{int(empresa_id)}"

    def _matches_empresa_scope(self, arquivo: Path, empresa_id: Optional[int]) -> bool:
        folder_name = self._empresa_folder_name(empresa_id)
        if not folder_name:
            return True
        try:
            resolved = arquivo.resolve()
        except Exception:
            resolved = arquivo

        # Arquivos gerais do sistema continuam elegíveis. Arquivos documentais precisam respeitar a pasta da empresa.
        if self._is_relative_to(resolved, self.downloads_dir) or self._is_relative_to(resolved, self.xml_dir):
            return folder_name in resolved.parts
        return True

    def _safe_zip_write_path(self, backup_path: Path) -> Path:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        return backup_path.with_name(f".{backup_path.name}.partial")

    def _validate_zip_file(self, zip_path: Path, deep: bool = False) -> None:
        """Valida um ZIP.

        deep=False faz uma validação rápida da estrutura/central directory.
        deep=True também testa os membros compactados, o que pode ser bem mais lento.
        """
        if not zipfile.is_zipfile(zip_path):
            raise zipfile.BadZipFile("Arquivo ZIP inválido ou incompleto")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.infolist()
            if deep:
                bad_member = zf.testzip()
                if bad_member:
                    raise zipfile.BadZipFile(f"Arquivo corrompido dentro do ZIP: {bad_member}")

    def _encontrar_arquivos(
        self,
        periodo_inicio: Optional[date] = None,
        periodo_fim: Optional[date] = None,
        tipos: Optional[List[str]] = None,
        empresa_id: Optional[int] = None,
        incluir_dados_internos: bool = False,
        destino_backup: Optional[Path] = None,
    ) -> Tuple[List[Path], int]:
        """
        Encontra arquivos que correspondem aos critérios.
        """
        if not tipos:
            tipos = ['XML', 'PDF', 'JSON']

        selected_exts = set()
        for tipo in tipos:
            selected_exts.update(self.DOC_EXTENSIONS.get(tipo.upper(), set()))

        arquivos: List[Path] = []
        tamanho_total = 0
        seen: set[Path] = set()
        inspected = 0

        for root in self._iter_roots():
            for arquivo in root.rglob('*'):
                inspected += 1
                if inspected % 250 == 0:
                    time.sleep(0.001)
                if not arquivo.is_file():
                    continue
                if self._should_skip(arquivo, destino_backup=destino_backup):
                    continue
                if not self._matches_empresa_scope(arquivo, empresa_id):
                    continue

                try:
                    resolved = arquivo.resolve()
                except Exception:
                    resolved = arquivo
                if resolved in seen:
                    continue
                seen.add(resolved)

                ext = arquivo.suffix.lower()
                internal = incluir_dados_internos and self._is_internal_file(arquivo)
                doc_selected = ext in selected_exts
                if not internal and not doc_selected:
                    continue

                if not internal and not self._matches_period(arquivo, periodo_inicio, periodo_fim):
                    continue

                if not internal and ext == '.json' and 'JSON' in [t.upper() for t in tipos or []] and not self._is_cleanable_document(arquivo, 'JSON'):
                    continue

                arquivos.append(arquivo)
                try:
                    tamanho_total += arquivo.stat().st_size
                except Exception:
                    pass

        return arquivos, tamanho_total

    def _compression_for_file(self, arquivo: Path) -> int:
        if arquivo.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.zip', '.rar', '.7z'}:
            return zipfile.ZIP_STORED
        return zipfile.ZIP_DEFLATED

    def _arcname_for_backup(self, arquivo: Path) -> str:
        try:
            return str(PurePosixPath('downloads') / arquivo.resolve().relative_to(self.downloads_dir.resolve()))
        except Exception:
            pass
        try:
            return str(PurePosixPath('data') / arquivo.resolve().relative_to(self.base_data_dir.resolve()))
        except Exception:
            pass
        try:
            return str(PurePosixPath('root') / arquivo.resolve().relative_to(self.project_root.resolve()))
        except Exception:
            pass
        return str(PurePosixPath('misc') / arquivo.name)

    def criar_backup(
        self,
        periodo_inicio: Optional[date] = None,
        periodo_fim: Optional[date] = None,
        tipos: Optional[List[str]] = None,
        empresa_id: Optional[int] = None,
        descricao: str = "",
        destino_path: Optional[Path | str] = None,
    ) -> Tuple[bool, str, Optional[Path]]:
        """
        Cria backup de arquivos.
        """
        try:
            self._set_progress(active=True, phase='Localizando arquivos do backup...', current=0, total=0, detail='Preparando arquivos')
            if not tipos:
                tipos = ['XML', 'PDF', 'JSON']

            if destino_path:
                backup_path = Path(destino_path)
                if backup_path.suffix.lower() != '.zip':
                    backup_path = backup_path.with_suffix('.zip')
                backup_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = self.backup_dir / f"backup_{timestamp}.zip"

            tmp_backup_path = self._safe_zip_write_path(backup_path)
            if tmp_backup_path.exists():
                try:
                    tmp_backup_path.unlink()
                except Exception:
                    pass

            arquivos, tamanho_total = self._encontrar_arquivos(
                periodo_inicio=periodo_inicio,
                periodo_fim=periodo_fim,
                tipos=tipos,
                empresa_id=empresa_id,
                incluir_dados_internos='JSON' in [t.upper() for t in tipos],
                destino_backup=tmp_backup_path,
            )

            if not arquivos:
                msg = "Nenhum arquivo encontrado para backup"
                log.warning(msg)
                self._clear_progress()
                return False, msg, None

            self._set_progress(phase='Compactando backup...', current=0, total=len(arquivos), detail=f'0/{len(arquivos)} arquivos')
            with zipfile.ZipFile(tmp_backup_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as zipf:
                for idx, arquivo in enumerate(arquivos, start=1):
                    try:
                        zipf.write(arquivo, arcname=self._arcname_for_backup(arquivo), compress_type=self._compression_for_file(arquivo))
                        if idx % 25 == 0:
                            time.sleep(0.001)
                    except Exception as e:
                        log.warning(f"Erro ao adicionar {arquivo} ao backup: {e}")
                    finally:
                        self._set_progress(phase='Compactando backup...', current=idx, total=len(arquivos), detail=f'{idx}/{len(arquivos)} arquivos')

            self._set_progress(phase='Validando backup...', current=len(arquivos), total=len(arquivos), detail=str(tmp_backup_path))
            self._validate_zip_file(tmp_backup_path, deep=False)
            os.replace(tmp_backup_path, backup_path)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            operacao = OperacaoLimpeza(
                id=timestamp,
                tipo='BACKUP',
                data_operacao=datetime.now(),
                periodo_inicio=periodo_inicio,
                periodo_fim=periodo_fim,
                tipos_arquivo=tipos or ['XML', 'PDF', 'JSON'],
                empresa_id=empresa_id,
                quantidade_arquivos=len(arquivos),
                tamanho_bytes=tamanho_total,
                backup_path=str(backup_path),
                status='SUCESSO',
                mensagem=f"Backup criado com {len(arquivos)} arquivos",
                usuario=None,
            )
            self.operacoes.append(operacao)
            self._salvar_log_operacoes()

            self._set_progress(phase='Backup concluído', current=len(arquivos), total=len(arquivos), detail=str(backup_path), active=False)
            log.info(f"Backup criado: {backup_path}")
            return True, f"Backup criado com sucesso ({len(arquivos)} arquivos)", backup_path

        except Exception as e:
            try:
                if 'tmp_backup_path' in locals() and Path(tmp_backup_path).exists():
                    Path(tmp_backup_path).unlink()
            except Exception:
                pass
            self._clear_progress()
            msg = f"Erro ao criar backup: {str(e)}"
            log.error(msg)
            return False, msg, None

    def limpar_arquivos(
        self,
        periodo_inicio: Optional[date] = None,
        periodo_fim: Optional[date] = None,
        tipos: Optional[List[str]] = None,
        empresa_id: Optional[int] = None,
        criar_backup_antes: bool = True,
    ) -> Tuple[bool, str, int]:
        """Limpa arquivos (com backup automático)."""
        try:
            self._set_progress(active=True, phase='Preparando limpeza...', current=0, total=0, detail='')
            backup_path = None
            if criar_backup_antes:
                sucesso, msg_backup, backup_path = self.criar_backup(
                    periodo_inicio, periodo_fim, tipos, empresa_id, descricao="antes_limpeza"
                )
                if not sucesso:
                    self._clear_progress()
                    return False, f"Não foi possível criar backup: {msg_backup}", 0

            self._set_progress(active=True, phase='Localizando arquivos para limpeza...', current=0, total=0, detail='')
            arquivos, tamanho_total = self._encontrar_arquivos(
                periodo_inicio=periodo_inicio,
                periodo_fim=periodo_fim,
                tipos=tipos,
                empresa_id=empresa_id,
                incluir_dados_internos=False,
            )

            if not arquivos:
                msg = "Nenhum arquivo encontrado para limpeza"
                log.warning(msg)
                self._clear_progress()
                return True, msg, 0

            quantidade_deletada = 0
            erros = []
            self._set_progress(active=True, phase='Excluindo arquivos...', current=0, total=len(arquivos), detail=f'0/{len(arquivos)} arquivos')
            for idx, arquivo in enumerate(arquivos, start=1):
                try:
                    arquivo.unlink()
                    quantidade_deletada += 1
                    if idx % 50 == 0:
                        time.sleep(0.001)
                except Exception as e:
                    erros.append(f"{arquivo.name}: {str(e)}")
                finally:
                    self._set_progress(active=True, phase='Excluindo arquivos...', current=idx, total=len(arquivos), detail=f'{idx}/{len(arquivos)} arquivos')

            status = 'SUCESSO' if not erros else 'PARCIAL'
            mensagem = f"Limpeza concluída: {quantidade_deletada} arquivos deletados"
            if erros:
                mensagem += f" ({len(erros)} erros)"

            op = OperacaoLimpeza(
                id=f"limpeza_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tipo='LIMPEZA',
                data_operacao=datetime.now(),
                periodo_inicio=periodo_inicio,
                periodo_fim=periodo_fim,
                tipos_arquivo=tipos or ['XML', 'PDF', 'JSON'],
                empresa_id=empresa_id,
                quantidade_arquivos=quantidade_deletada,
                tamanho_bytes=tamanho_total,
                backup_path=str(backup_path) if backup_path else None,
                status=status,
                mensagem=mensagem,
                usuario=None,
            )
            self.operacoes.append(op)
            self._salvar_log_operacoes()

            self._set_progress(active=False, phase='Limpeza concluída', current=quantidade_deletada, total=len(arquivos), detail=mensagem)
            log.info(mensagem)
            return True, mensagem, quantidade_deletada

        except Exception as e:
            self._clear_progress()
            msg = f"Erro ao limpar arquivos: {str(e)}"
            log.error(msg)
            return False, msg, 0

    def _remap_company_parts(self, parts: tuple[str, ...], empresa_id: Optional[int]) -> tuple[str, ...]:
        folder_name = self._empresa_folder_name(empresa_id)
        if not folder_name:
            return parts
        updated = list(parts)
        for idx, part in enumerate(updated):
            if re.fullmatch(r'empresa_\d+', part or ''):
                updated[idx] = folder_name
                break
        return tuple(updated)

    def _resolve_restore_destination(self, member_name: str, empresa_id: Optional[int] = None) -> Optional[Path]:
        path = PurePosixPath(member_name)
        if not path.parts:
            return None

        if any(part == '..' for part in path.parts):
            return None

        parts = self._remap_company_parts(tuple(path.parts), empresa_id)
        prefix = parts[0]
        remainder = parts[1:]

        if prefix == 'root':
            destino = self.project_root.joinpath(*remainder)
            base = self.project_root.resolve()
        elif prefix == 'downloads':
            destino = self.downloads_dir.joinpath(*remainder)
            base = self.downloads_dir.resolve()
        elif prefix == 'data':
            destino = self.base_data_dir.joinpath(*remainder)
            base = self.base_data_dir.resolve()
        else:
            destino = self.base_data_dir / PurePosixPath(*parts)
            base = self.base_data_dir.resolve()

        try:
            resolved = destino.resolve()
        except Exception:
            resolved = destino
        try:
            resolved.relative_to(base)
        except Exception:
            return None
        return destino

    def restaurar_backup(self, backup_path: Path | str, empresa_id: Optional[int] = None) -> Tuple[bool, str, int]:
        """Restaura arquivos a partir de um backup."""
        try:
            self._set_progress(active=True, phase='Abrindo backup para restauração...', current=0, total=0, detail='')
            backup_path = Path(backup_path)
            if not backup_path.exists():
                return False, f"Arquivo de backup não encontrado: {backup_path}", 0
            if backup_path.suffix.lower() != '.zip':
                return False, "Arquivo deve ser um ZIP", 0
            self._validate_zip_file(backup_path, deep=False)

            quantidade_restaurada = 0
            with zipfile.ZipFile(backup_path, 'r') as zf:
                members = [info for info in zf.infolist() if not info.is_dir()]
                self._set_progress(active=True, phase='Restaurando arquivos...', current=0, total=len(members), detail=f'0/{len(members)} arquivos')
                for idx, info in enumerate(members, start=1):
                    if info.is_dir():
                        continue
                    destino = self._resolve_restore_destination(info.filename, empresa_id=empresa_id)
                    if not destino:
                        log.warning(f"Entrada ignorada no backup por caminho inválido: {info.filename}")
                        continue

                    destino.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as source, open(destino, 'wb') as target:
                        shutil.copyfileobj(source, target)
                    quantidade_restaurada += 1
                    self._set_progress(active=True, phase='Restaurando arquivos...', current=idx, total=len(members), detail=f'{idx}/{len(members)} arquivos')

            op = OperacaoLimpeza(
                id=f"restauracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                tipo='RESTAURACAO',
                data_operacao=datetime.now(),
                periodo_inicio=None,
                periodo_fim=None,
                tipos_arquivo=['XML', 'PDF', 'JSON'],
                empresa_id=None,
                quantidade_arquivos=quantidade_restaurada,
                tamanho_bytes=backup_path.stat().st_size,
                backup_path=str(backup_path),
                status='SUCESSO',
                mensagem=f"Restauração concluída: {quantidade_restaurada} arquivos restaurados",
                usuario=None,
            )
            self.operacoes.append(op)
            self._salvar_log_operacoes()

            msg = f"Restauração concluída: {quantidade_restaurada} arquivos restaurados"
            self._set_progress(active=False, phase='Restauração concluída', current=quantidade_restaurada, total=max(quantidade_restaurada, 1), detail=msg)
            log.info(msg)
            return True, msg, quantidade_restaurada

        except Exception as e:
            self._clear_progress()
            msg = f"Erro ao restaurar backup: {str(e)}"
            log.error(msg)
            return False, msg, 0

    def listar_backups(self) -> List[Dict[str, Any]]:
        """Lista todos os backups disponíveis na pasta padrão."""
        backups = []
        if self.backup_dir.exists():
            for arquivo in sorted(self.backup_dir.glob('*.zip'), reverse=True):
                try:
                    self._validate_zip_file(arquivo)
                except Exception as e:
                    log.warning(f"Backup ignorado na listagem por estar inválido: {arquivo} ({e})")
                    continue
                backups.append({
                    'nome': arquivo.name,
                    'caminho': str(arquivo),
                    'tamanho_mb': arquivo.stat().st_size / 1024 / 1024,
                    'data_criacao': datetime.fromtimestamp(arquivo.stat().st_ctime),
                })
        return backups

    def obter_historico_operacoes(self, limite: int = 50) -> List[Dict[str, Any]]:
        """Obtém histórico de operações."""
        resultado = []
        for op in sorted(self.operacoes, key=lambda x: x.data_operacao, reverse=True)[:limite]:
            resultado.append({
                'id': op.id,
                'tipo': op.tipo,
                'data': op.data_operacao.strftime('%d/%m/%Y %H:%M:%S'),
                'periodo': f"{op.periodo_inicio} a {op.periodo_fim}" if op.periodo_inicio and op.periodo_fim else "N/A",
                'quantidade': op.quantidade_arquivos,
                'tamanho_mb': op.tamanho_bytes / 1024 / 1024,
                'status': op.status,
                'mensagem': op.mensagem,
            })
        return resultado
