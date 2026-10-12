import json
import logging
import os
from pathlib import Path
from typing import List

from mbft_core.models.indexacao import ChunkPayload

logger = logging.getLogger(__name__)

LIMITE_UPLOAD_VECTORIZE_BYTES = 100 * 1024 * 1024
MAX_ID_BYTES = 64
MAX_METADATA_BYTES = 10 * 1024


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


def validar_linha_vectorize(linha: str, origem: Path, num_linha: int) -> None:
    """
    Valida os limites por vetor exigidos pelo Cloudflare Vectorize (`id` <= 64 bytes,
    metadata <= 10 KiB) antes de iniciar um upload que pode levar minutos.
    """
    try:
        payload = ChunkPayload.model_validate_json(linha)
    except Exception as exc:
        raise ValueError(f"Falha de contrato ChunkPayload em '{origem}:{num_linha}': {exc}") from exc

    bytes_id = len(payload.id.encode("utf-8"))
    if bytes_id > MAX_ID_BYTES:
        raise ValueError(
            f"id de {bytes_id} bytes excede o limite de {MAX_ID_BYTES} bytes do Vectorize "
            f"em '{origem}:{num_linha}'."
        )

    bytes_metadata = len(payload.metadata.model_dump_json().encode("utf-8"))
    if bytes_metadata > MAX_METADATA_BYTES:
        raise ValueError(
            f"metadata de {bytes_metadata} bytes excede o limite de {MAX_METADATA_BYTES} bytes "
            f"do Vectorize em '{origem}:{num_linha}'."
        )


def gravar_parte_vectorize(out_dir: Path, indice: int, lote: List[bytes]) -> Path:
    """Grava um lote de linhas NDJSON como `<out_dir>/parte_NN.jsonl` sem tradução de newline."""
    destino = out_dir / f"parte_{indice:02d}.jsonl"
    destino.write_bytes(b"".join(lote))
    return destino


def dividir_jsonl_vectorize(
    jsonl_path: Path,
    out_dir: Path,
    limite_bytes: int = LIMITE_UPLOAD_VECTORIZE_BYTES,
) -> List[Path]:
    """
    Fatia o NDJSON canônico em partes abaixo do teto de 100 MB por upload do Cloudflare Vectorize,
    sem nunca cortar uma linha ao meio e validando cada vetor contra os limites do serviço.

    A leitura e a escrita são binárias de propósito: o teto do Vectorize é medido em bytes físicos,
    então a contagem não pode sofrer tradução de newline (CRLF no Windows).
    """
    validar_jsonl_producao(jsonl_path)
    if limite_bytes <= 0:
        raise ValueError("limite_bytes deve ser maior que zero.")

    out_dir.mkdir(parents=True, exist_ok=True)

    partes: List[Path] = []
    lote: List[bytes] = []
    bytes_lote = 0

    with open(jsonl_path, "rb") as arquivo:
        for num_linha, linha in enumerate(arquivo, start=1):
            if not linha.strip():
                continue
            validar_linha_vectorize(linha.decode("utf-8"), jsonl_path, num_linha)
            if lote and bytes_lote + len(linha) > limite_bytes:
                partes.append(gravar_parte_vectorize(out_dir, len(partes) + 1, lote))
                lote, bytes_lote = [], 0
            lote.append(linha)
            bytes_lote += len(linha)

    if lote:
        partes.append(gravar_parte_vectorize(out_dir, len(partes) + 1, lote))

    logger.info("JSONL fatiado em %d parte(s) para o Vectorize em %s", len(partes), out_dir)
    return partes


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
