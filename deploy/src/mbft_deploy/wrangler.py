import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from mbft_core.paths import RAIZ_REPO
from .exporters import (
    LIMITE_UPLOAD_VECTORIZE_BYTES,
    atualizar_config_js_site,
    dividir_jsonl_vectorize,
    validar_jsonl_producao,
)

logger = logging.getLogger(__name__)

RE_UUID = re.compile(
    r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)


def _ler_json_wrangler(saida: str, descricao: str) -> object:
    try:
        return json.loads(saida)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Saída inválida do Wrangler ao consultar {descricao}: {exc}") from exc


def _itens_wrangler(dados: object) -> List[dict]:
    if isinstance(dados, list):
        return [item for item in dados if isinstance(item, dict)]
    if isinstance(dados, dict):
        for chave in ("result", "items", "projects", "indexes", "databases", "deployments"):
            valor = dados.get(chave)
            if isinstance(valor, list):
                return [item for item in valor if isinstance(item, dict)]
    return []


def resolver_binario_wrangler() -> List[str]:
    """Localiza o executável `wrangler` no PATH (ou via `npx wrangler`)."""
    if shutil.which("wrangler") is not None:
        return ["wrangler"]
    if shutil.which("npx") is not None:
        return ["npx", "wrangler"]
    raise RuntimeError(
        "Executável 'wrangler' (ou 'npx') não encontrado no PATH. "
        "Instale o Wrangler CLI (`npm i -g wrangler`) e autentique com `wrangler login`."
    )


def invocacao_do_comando(
    comando: List[str],
    windows: Optional[bool] = None,
) -> Tuple[Union[List[str], str], bool]:
    """
    Prepara a invocação do comando, devolvendo `(argumentos, usar_shell)`.

    No Windows, `npx` é um script `.cmd` e o `CreateProcess` não executa esse tipo de arquivo
    diretamente (`WinError 2`). Nesse caso o comando é entregue como texto único ao `cmd.exe`
    via `shell=True`, que é o interpretador capaz de executá-lo — e onde as aspas dos caminhos
    com espaço sobrevivem à regra de parsing do `/c`.
    """
    if windows is None:
        windows = os.name == "nt"
    if not windows or not comando:
        return list(comando), False

    executavel = shutil.which(comando[0])
    if executavel is not None and executavel.lower().endswith((".cmd", ".bat")):
        return subprocess.list2cmdline([executavel, *comando[1:]]), True
    return list(comando), False


def rodar_comando_wrangler(
    comando: List[str],
    description: str,
    cwd: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Executa um comando Wrangler (ou simula em modo `--dry-run`)."""
    if comando and comando[0] == "wrangler" and not dry_run:
        prefixo = resolver_binario_wrangler()
        cmd_final = prefixo + comando[1:]
    else:
        cmd_final = list(comando)

    logger.info("Executando deploy: %s", description)
    logger.info("Comando: %s (cwd=%s)", " ".join(cmd_final), cwd or Path.cwd())

    if dry_run:
        logger.info("[DRY-RUN] Comando simulado sem execução real.")
        return ""

    invocacao, usar_shell = invocacao_do_comando(cmd_final)
    try:
        resultado = subprocess.run(
            invocacao,
            cwd=str(cwd) if cwd else None,
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            shell=usar_shell,
        )
        if resultado.stdout:
            logger.info("Sucesso: %s", resultado.stdout.strip())
        return resultado.stdout or ""
    except subprocess.CalledProcessError as e:
        logger.error("Erro ao executar wrangler: %s", e.stderr)
        logger.error(
            "Certifique-se de que o Node.js/Wrangler estão instalados e você está autenticado (wrangler login)."
        )
        raise RuntimeError(f"Falha ao executar wrangler: {e.stderr}") from e


def fazer_deploy_vectorize(
    jsonl_path: Path,
    index_name: str = "mbft-embeddings",
    dry_run: bool = False,
    out_dir: Optional[Path] = None,
) -> List[Path]:
    """
    Envia o artefato NDJSON de embeddings para o Cloudflare Vectorize, fatiando-o em partes
    que respeitem o teto de 100 MB por upload sempre que o arquivo não couber em uma chamada.
    """
    validar_jsonl_producao(jsonl_path)

    if jsonl_path.stat().st_size <= LIMITE_UPLOAD_VECTORIZE_BYTES:
        arquivos = [jsonl_path]
    else:
        arquivos = dividir_jsonl_vectorize(jsonl_path, out_dir or jsonl_path.parent / "vectorize")

    for arquivo in arquivos:
        rodar_comando_wrangler(
            [
                "wrangler",
                "vectorize",
                "insert",
                index_name,
                "--file",
                str(arquivo),
            ],
            f"Upload JSONL para Vectorize ({index_name}): {arquivo.name}",
            dry_run=dry_run,
        )
    return arquivos


def fazer_deploy_d1(
    sql_script_path: Path,
    db_name: str = "mbft-d1",
    remote: bool = True,
    cwd: Optional[Path] = None,
    dry_run: bool = False,
) -> None:
    """Executa um script SQL no Cloudflare D1 (`--remote` ou `--local`)."""
    if not sql_script_path.exists():
        raise FileNotFoundError(f"Script SQL não encontrado em {sql_script_path}")

    flag_alvo = "--remote" if remote else "--local"
    comando = [
        "wrangler",
        "d1",
        "execute",
        db_name,
        "--file",
        str(sql_script_path),
        flag_alvo,
    ]
    rodar_comando_wrangler(
        comando,
        f"Executar script SQL no D1 ({db_name}, {flag_alvo})",
        cwd=cwd,
        dry_run=dry_run,
    )


def atualizar_ids_wrangler_jsonc(
    wrangler_path: Path,
    database_id: Optional[str] = None,
) -> None:
    """Atualiza `database_id` (D1) em `apps/api/wrangler.jsonc`."""
    if not wrangler_path.exists():
        raise FileNotFoundError(f"Arquivo wrangler.jsonc não encontrado em {wrangler_path}")

    conteudo = wrangler_path.read_text(encoding="utf-8")
    dados = json.loads(conteudo)

    if database_id:
        for db_entry in dados.get("d1_databases", []):
            db_entry["database_id"] = database_id

    wrangler_path.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("IDs atualizados em %s (D1=%s)", wrangler_path, database_id)


def provisionar_recursos_cloudflare(
    wrangler_config_path: Optional[Path] = None,
    db_name: str = "mbft-d1",
    index_name: str = "mbft-embeddings",
    project_name: str = "mbft-site",
    dry_run: bool = False,
) -> Dict[str, Optional[str]]:
    """
    Provisiona D1 e Vectorize (1024 dims, cosine) na Cloudflare via Wrangler
    e preenche os IDs retornados em `apps/api/wrangler.jsonc`.
    """
    if wrangler_config_path is None:
        wrangler_config_path = RAIZ_REPO / "apps" / "api" / "wrangler.jsonc"

    out_d1 = rodar_comando_wrangler(
        ["wrangler", "d1", "create", db_name],
        f"Provisionar banco D1 ({db_name})",
        dry_run=dry_run,
    )
    rodar_comando_wrangler(
        [
            "wrangler",
            "vectorize",
            "create",
            index_name,
            "--dimensions=1024",
            "--metric=cosine",
        ],
        f"Provisionar índice Vectorize ({index_name})",
        dry_run=dry_run,
    )
    garantir_projeto_pages(project_name, dry_run=dry_run)

    m_d1 = RE_UUID.search(out_d1)
    database_id = m_d1.group(1) if m_d1 else None

    if not dry_run and database_id:
        atualizar_ids_wrangler_jsonc(
            wrangler_config_path,
            database_id=database_id,
        )

    return {"database_id": database_id}


def verificar_status_recursos_cloudflare(
    wrangler_config_path: Optional[Path] = None,
    db_name: str = "mbft-d1",
    index_name: str = "mbft-embeddings",
    worker_name: Optional[str] = None,
    project_name: str = "mbft-site",
) -> Dict[str, object]:
    """Consulta a infraestrutura Cloudflare sem criar, alterar ou publicar recursos."""
    if wrangler_config_path is None:
        wrangler_config_path = RAIZ_REPO / "apps" / "api" / "wrangler.jsonc"
    if not wrangler_config_path.exists():
        raise FileNotFoundError(f"Arquivo wrangler.jsonc não encontrado em {wrangler_config_path}")

    config = json.loads(wrangler_config_path.read_text(encoding="utf-8"))
    worker_name = worker_name or config.get("name", "mbft-api")
    saidas = {
        "d1": _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(["wrangler", "d1", "list", "--json"], "Consultar bancos D1"),
                "bancos D1",
            )
        ),
        "vectorize": _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "vectorize", "list", "--json"], "Consultar índices Vectorize"
                ),
                "índices Vectorize",
            )
        ),
        "pages": _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "pages", "project", "list", "--json"], "Consultar projetos Pages"
                ),
                "projetos Pages",
            )
        ),
        "worker": _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "deployments", "list", "--name", worker_name, "--json"],
                    "Consultar deployments do Worker",
                ),
                "deployments do Worker",
            )
        ),
    }

    d1 = next(
        (
            item
            for item in saidas["d1"]
            if item.get("name") == db_name or item.get("database_name") == db_name
        ),
        None,
    )
    d1_config = next((item for item in config.get("d1_databases", []) if item.get("database_name") == db_name), {})
    vectorize = next(
        (
            item
            for item in saidas["vectorize"]
            if item.get("name") == index_name or item.get("index_name") == index_name
        ),
        None,
    )
    pages = next(
        (
            item
            for item in saidas["pages"]
            if item.get("name") == project_name or item.get("Project Name") == project_name
        ),
        None,
    )
    worker = bool(saidas["worker"])
    vectorize_config = vectorize.get("config", {}) if vectorize else {}
    d1_id = d1.get("database_id") or d1.get("uuid") if d1 else None

    checks = {
        "d1": bool(d1) and d1_id == d1_config.get("database_id"),
        "vectorize": bool(vectorize)
        and (vectorize.get("dimensions") or vectorize_config.get("dimensions")) == 1024
        and str(vectorize.get("metric") or vectorize_config.get("metric", "")).lower() == "cosine",
        "pages": bool(pages),
        "worker": worker,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "d1": d1,
        "vectorize": vectorize,
        "pages": pages,
        "worker": worker,
    }


def fazer_deploy_api(
    api_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> None:
    """Publica o Worker da API (`apps/api`) no Cloudflare Workers."""
    if api_dir is None:
        api_dir = RAIZ_REPO / "apps" / "api"
    if not (api_dir / "wrangler.jsonc").exists():
        raise FileNotFoundError(f"wrangler.jsonc não encontrado em {api_dir}")

    rodar_comando_wrangler(
        ["wrangler", "deploy"],
        "Publicar Worker mbft-api no Cloudflare Workers",
        cwd=api_dir,
        dry_run=dry_run,
    )


ERRO_PROJETO_PAGES_EXISTENTE = "already exists"


def garantir_projeto_pages(project_name: str, dry_run: bool = False) -> None:
    """
    Garante a existência do projeto Cloudflare Pages, que é pré-requisito de `pages deploy`.
    O projeto é criado quando ausente e o erro de duplicidade é tratado como sucesso.
    """
    try:
        rodar_comando_wrangler(
            [
                "wrangler",
                "pages",
                "project",
                "create",
                project_name,
                "--production-branch=main",
            ],
            f"Garantir projeto Pages ({project_name})",
            dry_run=dry_run,
        )
    except RuntimeError as exc:
        if ERRO_PROJETO_PAGES_EXISTENTE not in str(exc).lower():
            raise
        logger.info("Projeto Pages '%s' já existe; reutilizando.", project_name)


def fazer_deploy_site(
    site_dir: Optional[Path] = None,
    project_name: str = "mbft-site",
    api_url: Optional[str] = None,
    dry_run: bool = False,
) -> None:
    """
    Atualiza `config.js` (se `api_url` ou `MBFT_API_URL` for informado) e publica
    o diretório `data/processed/site` no Cloudflare Pages.
    """
    if site_dir is None:
        site_dir = RAIZ_REPO / "data" / "processed" / "site"
    if not site_dir.exists():
        raise FileNotFoundError(
            f"Diretório do site estático não encontrado em {site_dir}. Execute `uv run mbft-ssg` primeiro."
        )

    url_efetiva = api_url if api_url is not None else os.environ.get("MBFT_API_URL")
    if url_efetiva is not None and not dry_run:
        atualizar_config_js_site(site_dir, url_efetiva)

    garantir_projeto_pages(project_name, dry_run=dry_run)

    rodar_comando_wrangler(
        [
            "wrangler",
            "pages",
            "deploy",
            str(site_dir),
            f"--project-name={project_name}",
        ],
        f"Publicar site estático no Cloudflare Pages ({project_name})",
        dry_run=dry_run,
    )
