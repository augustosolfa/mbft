import json
import logging
import os
from pathlib import Path
from typing import List

from mbft_core.models.indexacao import ChunkPayload

logger = logging.getLogger(__name__)


def validar_jsonl_producao(jsonl_path: Path) -> None:
    """Garante que o arquivo JSONL existe e não é um artefato de debug (--skip-embeddings)."""
    if "debug" in jsonl_path.name.lower():
        raise ValueError(
            f"Operação recusada: o arquivo '{jsonl_path}' é um artefato de debug/teste."
        )
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Arquivo JSONL não encontrado em: {jsonl_path}")


def escapar_sql(valor: str) -> str:
    """Escapa aspas simples para literais de string em SQLite / Cloudflare D1."""
    return (valor or "").replace("'", "''")


def exportar_fts_chunks_sql(
    jsonl_path: Path,
    sql_out_path: Path,
    batch_size: int = 100,
) -> int:
    """
    Lê o artefato canônico `embeddings_mbft.jsonl` (`ChunkPayload`) e gera um script SQL
    idempotente (`fts_chunks.sql`) compatível com `wrangler d1 execute` (sem BEGIN/COMMIT explícitos).
    """
    validar_jsonl_producao(jsonl_path)
    if batch_size <= 0:
        raise ValueError("batch_size deve ser maior que zero.")

    payloads: List[ChunkPayload] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for num_linha, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payloads.append(ChunkPayload.model_validate_json(stripped))
            except Exception as exc:
                raise ValueError(
                    f"Falha de contrato ChunkPayload em '{jsonl_path}:{num_linha}': {exc}"
                ) from exc

    sql_out_path.parent.mkdir(parents=True, exist_ok=True)
    temp_sql = sql_out_path.with_suffix(".sql.tmp")

    with open(temp_sql, "w", encoding="utf-8") as out:
        out.write("-- Dump gerado automaticamente por mbft-deploy (PMS-010)\n")
        out.write("DELETE FROM fts_chunks;\n\n")

        for i in range(0, len(payloads), batch_size):
            lote = payloads[i : i + batch_size]
            tuplas = []
            for p in lote:
                meta = p.metadata
                tuplas.append(
                    "('{}', '{}', '{}', '{}', '{}')".format(
                        escapar_sql(p.id),
                        escapar_sql(meta.codigo),
                        escapar_sql(meta.artigo),
                        escapar_sql(meta.secao),
                        escapar_sql(meta.texto_contextualizado),
                    )
                )
            valores_sql = ",\n  ".join(tuplas)
            out.write(
                "INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado)\n"
                f"VALUES\n  {valores_sql};\n\n"
            )

    os.replace(temp_sql, sql_out_path)
    logger.info(
        "Dump SQL FTS5 exportado com sucesso: %s (%d chunks)",
        sql_out_path,
        len(payloads),
    )
    return len(payloads)


def atualizar_config_js_site(site_dir: Path, api_base_url: str) -> Path:
    """
    Atualiza `config.js` no diretório do site estático com a URL de produção da API,
    mantendo a pipeline `mbft-ssg` desacoplada de ambientes de nuvem.
    """
    if not site_dir.exists():
        raise FileNotFoundError(f"Diretório do site estático não encontrado em: {site_dir}")

    url_limpa = (api_base_url or "").strip().rstrip("/")
    config_path = site_dir / "config.js"
    conteudo = f"window.MBFT_CONFIG = {{\n  apiBaseUrl: {json.dumps(url_limpa)}\n}};\n"
    config_path.write_text(conteudo, encoding="utf-8")
    logger.info("Arquivo %s atualizado com apiBaseUrl=%r", config_path, url_limpa)
    return config_path
