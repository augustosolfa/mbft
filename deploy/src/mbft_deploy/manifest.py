"""Controle idempotente dos artefatos publicados no D1."""

import hashlib
import json
from pathlib import Path

from .wrangler import escapar_sql, rodar_comando_wrangler

TIPOS_RECURSO = ("d1_schema", "d1_content", "vectorize")


def calcular_hash_arquivo(path: Path) -> str:
    """Calcula o SHA-256 do conteúdo físico de um artefato."""
    digest = hashlib.sha256()
    with path.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return f"sha256:{digest.hexdigest()}"


def contar_linhas_jsonl(path: Path) -> int:
    """Conta registros não vazios do JSONL canônico."""
    with path.open("r", encoding="utf-8") as arquivo:
        return sum(bool(linha.strip()) for linha in arquivo)


def _extrair_linhas(saida: str) -> list[dict[str, object]]:
    dados = json.loads(saida)
    if isinstance(dados, list):
        linhas: list[dict[str, object]] = []
        for item in dados:
            if isinstance(item, dict):
                nested = item.get("results")
                if isinstance(nested, list):
                    linhas.extend(
                        row for row in nested if isinstance(row, dict)
                    )
                else:
                    linhas.append(item)
        return linhas
    if isinstance(dados, dict):
        for chave in ("results", "result", "rows"):
            valor = dados.get(chave)
            if isinstance(valor, list):
                return [item for item in valor if isinstance(item, dict)]
    return []


def garantir_tabela_manifesto(
    migration_path: Path,
    db_name: str,
    cwd: Path,
    dry_run: bool = False,
) -> None:
    """Aplica a migração idempotente que cria a tabela de manifesto."""
    if not migration_path.exists():
        raise FileNotFoundError(f"Migração do manifesto não encontrada em {migration_path}")
    comando = [
        "wrangler",
        "d1",
        "execute",
        db_name,
        "--file",
        str(migration_path),
        "--remote",
    ]
    rodar_comando_wrangler(
        comando,
        f"Garantir tabela deploy_manifest no D1 ({db_name})",
        cwd=cwd,
        dry_run=dry_run,
    )


def consultar_manifesto(
    db_name: str,
    cwd: Path,
    dry_run: bool = False,
) -> dict[tuple[str, str], dict[str, object]]:
    """Consulta o estado dos recursos no manifesto remoto."""
    if dry_run:
        return {}
    saida = rodar_comando_wrangler(
        [
            "wrangler",
            "d1",
            "execute",
            db_name,
            "--remote",
            "--json",
            "--command",
            "SELECT resource_type, resource_name, content_hash, status, item_count "
            "FROM deploy_manifest",
        ],
        f"Consultar manifesto de deploy ({db_name})",
        cwd=cwd,
    )
    try:
        linhas = _extrair_linhas(saida)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Saída inválida ao consultar o manifesto do D1: {exc}") from exc
    return {
        (str(linha.get("resource_type")), str(linha.get("resource_name"))): linha
        for linha in linhas
        if linha.get("resource_type") and linha.get("resource_name")
    }


def atualizar_manifesto(
    db_name: str,
    cwd: Path,
    resource_type: str,
    resource_name: str,
    content_hash: str,
    status: str,
    item_count: int | None = None,
    error_message: str | None = None,
    dry_run: bool = False,
) -> None:
    """Atualiza um recurso do manifesto após iniciar ou concluir sua sincronização."""
    count_sql = "NULL" if item_count is None else str(item_count)
    error_sql = "NULL" if error_message is None else f"'{escapar_sql(error_message)}'"
    comando_sql = (
        "INSERT INTO deploy_manifest "
        "(resource_type, resource_name, content_hash, status, item_count, error_message) "
        f"VALUES ('{escapar_sql(resource_type)}', '{escapar_sql(resource_name)}', "
        f"'{escapar_sql(content_hash)}', '{escapar_sql(status)}', {count_sql}, {error_sql}) "
        "ON CONFLICT(resource_type, resource_name) DO UPDATE SET "
        "content_hash=excluded.content_hash, status=excluded.status, "
        "item_count=excluded.item_count, updated_at=CURRENT_TIMESTAMP, "
        "error_message=excluded.error_message;"
    )
    rodar_comando_wrangler(
        [
            "wrangler",
            "d1",
            "execute",
            db_name,
            "--remote",
            "--command",
            comando_sql,
        ],
        f"Atualizar manifesto ({resource_type}/{resource_name}: {status})",
        cwd=cwd,
        dry_run=dry_run,
    )


def recurso_precisa_sincronizar(
    manifesto: dict[tuple[str, str], dict[str, object]],
    resource_type: str,
    resource_name: str,
    content_hash: str,
    force: bool = False,
) -> bool:
    """Decide se um recurso ausente ou divergente deve ser publicado."""
    if force:
        return True
    registro = manifesto.get((resource_type, resource_name))
    return (
        not registro
        or registro.get("content_hash") != content_hash
        or registro.get("status") != "ready"
    )
