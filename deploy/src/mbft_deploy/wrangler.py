import json
import logging
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from mbft_api.asgi_prefix import RUN_WORKER_FIRST_PATTERNS
from mbft_core.paths import RAIZ_REPO

from .exporters import (
    LIMITE_UPLOAD_VECTORIZE_BYTES,
    dividir_jsonl_vectorize,
    validar_jsonl_producao,
)

logger = logging.getLogger(__name__)

RE_UUID = re.compile(
    r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"
)

# Hostname de produção, lido do `.env` da raiz por allow-list (ver `cli.py`).
MBFT_HOSTNAME_ENV = "MBFT_HOSTNAME"
RE_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
NOT_FOUND_HANDLING_ESPERADO = "404-page"
ERRO_WORKER_INEXISTENTE = "[code: 10007]"


def escapar_sql(valor: str) -> str:
    """Escapa aspas simples para literais SQL enviados ao D1."""
    return valor.replace("'", "''")


RE_COMENTARIOS_JSONC = re.compile(
    r'("(?:\\.|[^"\\])*")|//.*?$|/\*.*?\*/',
    re.MULTILINE | re.DOTALL,
)


def _remover_comentarios_jsonc(texto: str) -> str:
    """Remove comentários // e /* */ de um texto JSONC preservando strings literais."""
    return RE_COMENTARIOS_JSONC.sub(lambda m: m.group(1) if m.group(1) else "", texto)


def _carregar_jsonc(caminho_ou_texto: str | Path) -> dict:
    """Lê arquivo ou string no formato JSONC (suportando comentários do Wrangler)."""
    texto = (
        caminho_ou_texto.read_text(encoding="utf-8")
        if isinstance(caminho_ou_texto, Path)
        else caminho_ou_texto
    )
    return json.loads(_remover_comentarios_jsonc(texto))


def _ler_json_wrangler(saida: str, descricao: str) -> object:
    try:
        return json.loads(saida)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Saída inválida do Wrangler ao consultar {descricao}: {exc}"
        ) from exc


def _itens_wrangler(dados: object) -> list[dict]:
    if isinstance(dados, list):
        return [item for item in dados if isinstance(item, dict)]
    if isinstance(dados, dict):
        for chave in (
            "result",
            "items",
            "projects",
            "indexes",
            "databases",
            "deployments",
        ):
            valor = dados.get(chave)
            if isinstance(valor, list):
                return [item for item in valor if isinstance(item, dict)]
    return []


def resolver_binario_wrangler() -> list[str]:
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
    comando: list[str],
    windows: bool | None = None,
) -> tuple[list[str] | str, bool]:
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
    comando: list[str],
    description: str,
    cwd: Path | None = None,
    dry_run: bool = False,
    erros_esperados: tuple[str, ...] = (),
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
        if any(marcador in (e.stderr or "") for marcador in erros_esperados):
            return e.stderr or ""
        logger.error("Erro ao executar wrangler: %s", e.stderr)
        logger.error(
            "Certifique-se de que o Node.js/Wrangler estão instalados e você está autenticado (wrangler login)."
        )
        raise RuntimeError(f"Falha ao executar wrangler: {e.stderr}") from e


def _consultar_deployments_worker(
    worker_name: str,
) -> list[dict]:
    """Consulta deployments, tratando um Worker ainda não publicado como ausente."""
    try:
        saida = rodar_comando_wrangler(
            [
                "wrangler",
                "deployments",
                "list",
                "--name",
                worker_name,
                "--json",
            ],
            "Consultar deployments do Worker",
            erros_esperados=(ERRO_WORKER_INEXISTENTE,),
        )
        if ERRO_WORKER_INEXISTENTE in saida:
            logger.info(
                "Worker %s ainda não existe na conta Cloudflare; status: INCOMPLETO.",
                worker_name,
            )
            return []
    except RuntimeError as exc:
        if ERRO_WORKER_INEXISTENTE not in str(exc):
            raise
        logger.info(
            "Worker %s ainda não existe na conta Cloudflare; status: INCOMPLETO.",
            worker_name,
        )
        return []

    return _itens_wrangler(
        _ler_json_wrangler(saida, "deployments do Worker")
    )


def fazer_deploy_vectorize(
    jsonl_path: Path,
    index_name: str = "mbft-embeddings",
    dry_run: bool = False,
    out_dir: Path | None = None,
) -> list[Path]:
    """
    Envia o artefato NDJSON de embeddings para o Cloudflare Vectorize, fatiando-o em partes
    que respeitem o teto de 100 MB por upload sempre que o arquivo não couber em uma chamada.
    """
    validar_jsonl_producao(jsonl_path)

    if jsonl_path.stat().st_size <= LIMITE_UPLOAD_VECTORIZE_BYTES:
        arquivos = [jsonl_path]
    else:
        arquivos = dividir_jsonl_vectorize(
            jsonl_path, out_dir or jsonl_path.parent / "vectorize"
        )

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
    cwd: Path | None = None,
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
    database_id: str | None = None,
) -> None:
    """Atualiza `database_id` (D1) em `apps/api/wrangler.jsonc`."""
    if not wrangler_path.exists():
        raise FileNotFoundError(
            f"Arquivo wrangler.jsonc não encontrado em {wrangler_path}"
        )

    dados = _carregar_jsonc(wrangler_path)

    if database_id:
        for db_entry in dados.get("d1_databases", []):
            db_entry["database_id"] = database_id

    wrangler_path.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("IDs atualizados em %s (D1=%s)", wrangler_path, database_id)


def provisionar_recursos_cloudflare(
    wrangler_config_path: Path | None = None,
    db_name: str = "mbft-d1",
    index_name: str = "mbft-embeddings",
    dry_run: bool = False,
) -> dict[str, str | None]:
    """
    Provisiona D1 e Vectorize (1024 dims, cosine) na Cloudflare via Wrangler
    e preenche os IDs retornados em `apps/api/wrangler.jsonc`.

    O site estático não possui recursos de provisionamento próprios: seus assets são
    publicados no mesmo Worker `mbft` durante o `wrangler deploy` (PMS-010).
    """
    if wrangler_config_path is None:
        wrangler_config_path = RAIZ_REPO / "apps" / "api" / "wrangler.jsonc"

    database_id: str | None = None
    if not dry_run:
        bancos = _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "d1", "list", "--json"],
                    "Consultar bancos D1 existentes",
                ),
                "bancos D1",
            )
        )
        banco_existente = next(
            (
                item
                for item in bancos
                if item.get("name") == db_name
                or item.get("database_name") == db_name
            ),
            None,
        )
        database_id = (
            (banco_existente or {}).get("database_id")
            or (banco_existente or {}).get("uuid")
        )
        if database_id:
            logger.info("Banco D1 %s já existe; reutilizando.", db_name)
        else:
            out_d1 = rodar_comando_wrangler(
                ["wrangler", "d1", "create", db_name],
                f"Provisionar banco D1 ({db_name})",
            )
            m_d1 = RE_UUID.search(out_d1)
            database_id = m_d1.group(1) if m_d1 else None

        indices = _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "vectorize", "list", "--json"],
                    "Consultar índices Vectorize existentes",
                ),
                "índices Vectorize",
            )
        )
        indice_existente = next(
            (
                item
                for item in indices
                if item.get("name") == index_name
                or item.get("index_name") == index_name
            ),
            None,
        )
        if indice_existente:
            config_indice = indice_existente.get("config", {})
            dimensions = indice_existente.get("dimensions") or config_indice.get(
                "dimensions"
            )
            metric = str(
                indice_existente.get("metric")
                or config_indice.get("metric", "")
            ).lower()
            if dimensions != 1024 or metric != "cosine":
                raise RuntimeError(
                    f"Índice Vectorize {index_name} já existe com configuração "
                    f"incompatível (dimensions={dimensions}, metric={metric})."
                )
            logger.info("Índice Vectorize %s já existe; reutilizando.", index_name)
        else:
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
            )
    else:
        rodar_comando_wrangler(
            ["wrangler", "d1", "create", db_name],
            f"Provisionar banco D1 ({db_name})",
            dry_run=True,
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
            dry_run=True,
        )

    if not dry_run and database_id:
        atualizar_ids_wrangler_jsonc(
            wrangler_config_path,
            database_id=database_id,
        )

    return {"database_id": database_id}


def verificar_status_recursos_cloudflare(
    wrangler_config_path: Path | None = None,
    db_name: str = "mbft-d1",
    index_name: str = "mbft-embeddings",
    worker_name: str | None = None,
) -> dict[str, object]:
    """Consulta a infraestrutura Cloudflare sem criar, alterar ou publicar recursos."""
    if wrangler_config_path is None:
        wrangler_config_path = RAIZ_REPO / "apps" / "api" / "wrangler.jsonc"
    if not wrangler_config_path.exists():
        raise FileNotFoundError(
            f"Arquivo wrangler.jsonc não encontrado em {wrangler_config_path}"
        )

    config = _carregar_jsonc(wrangler_config_path)
    worker_name = worker_name or config.get("name", "mbft")
    saidas = {
        "d1": _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "d1", "list", "--json"], "Consultar bancos D1"
                ),
                "bancos D1",
            )
        ),
        "vectorize": _itens_wrangler(
            _ler_json_wrangler(
                rodar_comando_wrangler(
                    ["wrangler", "vectorize", "list", "--json"],
                    "Consultar índices Vectorize",
                ),
                "índices Vectorize",
            )
        ),
        "worker": _consultar_deployments_worker(worker_name),
    }

    d1 = next(
        (
            item
            for item in saidas["d1"]
            if item.get("name") == db_name or item.get("database_name") == db_name
        ),
        None,
    )
    d1_config = next(
        (
            item
            for item in config.get("d1_databases", [])
            if item.get("database_name") == db_name
        ),
        {},
    )
    vectorize = next(
        (
            item
            for item in saidas["vectorize"]
            if item.get("name") == index_name or item.get("index_name") == index_name
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
        and str(vectorize.get("metric") or vectorize_config.get("metric", "")).lower()
        == "cosine",
        "worker": worker,
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "d1": d1,
        "vectorize": vectorize,
        "worker": worker,
    }


def normalizar_hostname(valor: str) -> str:
    """Valida e normaliza um hostname informado por `--hostname` ou `MBFT_HOSTNAME`."""
    host = (valor or "").strip()
    if not host:
        raise ValueError(
            "hostname vazio: informe um domínio (ex.: 'mbft.exemplo.com')."
        )
    if "://" in host or "/" in host or any(caractere.isspace() for caractere in host):
        raise ValueError(
            f"hostname malformado: {valor!r}. Informe apenas o domínio (ex.: 'mbft.exemplo.com'), "
            "sem esquema, caminho ou espaços."
        )
    if not RE_HOSTNAME.match(host):
        raise ValueError(f"hostname malformado: {valor!r}.")
    return host


def resolver_hostname_deploy(hostname: str | None = None) -> str | None:
    """
    Resolve o hostname de produção pela precedência `--hostname` > `MBFT_HOSTNAME` > nenhum.
    Sem hostname, o Worker permanece acessível apenas em `workers.dev`.
    """
    candidato = hostname if hostname is not None else os.environ.get(MBFT_HOSTNAME_ENV)
    if candidato is None or not str(candidato).strip():
        return None
    return normalizar_hostname(str(candidato))


def validar_assets_do_worker(wrangler_path: Path) -> None:
    """
    Garante que a configuração de `assets` do Worker espelha `RUN_WORKER_FIRST_PATTERNS`
    (fonte única declarada pelo adapter ASGI), evitando divergência entre o roteamento do
    edge e a normalização de `/api` aplicada pelo FastAPI.
    """
    dados = _carregar_jsonc(wrangler_path)
    assets = dados.get("assets") or {}
    esperado = list(RUN_WORKER_FIRST_PATTERNS)
    if assets.get("run_worker_first") != esperado:
        raise ValueError(
            f"'assets.run_worker_first' em {wrangler_path} deve ser {esperado} "
            f"(valor atual: {assets.get('run_worker_first')!r})."
        )
    if assets.get("not_found_handling") != NOT_FOUND_HANDLING_ESPERADO:
        raise ValueError(
            f"'assets.not_found_handling' em {wrangler_path} deve ser "
            f"{NOT_FOUND_HANDLING_ESPERADO!r} (valor atual: {assets.get('not_found_handling')!r})."
        )


# Manifesto efêmero gerado por deploy ao lado de `wrangler.jsonc` (não versionado).
NOME_CONFIG_DEPLOY = ".wrangler.deploy.jsonc"


def montar_manifest_deploy(config: dict, hostname: str | None) -> dict:
    """
    Devolve uma cópia do manifesto com `workers_dev` coerente com o alvo do deploy:
    desabilitado quando há hostname (para não expor o Worker em `workers.dev`) e habilitado
    quando não há (único endereço disponível). Quando há hostname, também declara um
    Custom Domain no formato aceito pelo Wrangler. Injeta automaticamente um sal seguro
    em `vars.RATE_LIMIT_SALT` para rate limit (PMS-011) quando ausente. A origem nunca é mutada.
    """
    dados = dict(config)
    dados["workers_dev"] = hostname is None
    if hostname:
        rotas = list(dados.get("routes") or [])
        rotas = [
            rota
            for rota in rotas
            if not (isinstance(rota, dict) and rota.get("pattern") == hostname)
        ]
        rotas.append({"pattern": hostname, "custom_domain": True})
        dados["routes"] = rotas

    vars_atuais = dict(dados.get("vars") or {})
    if not vars_atuais.get("RATE_LIMIT_SALT"):
        sal_env = os.environ.get("RATE_LIMIT_SALT") or os.environ.get("MBFT_RATE_LIMIT_SALT")
        vars_atuais["RATE_LIMIT_SALT"] = sal_env or secrets.token_hex(32)

    for chave_access in ("ACCESS_TEAM_DOMAIN", "ACCESS_AUD"):
        if not vars_atuais.get(chave_access):
            val = os.environ.get(chave_access)
            if val:
                vars_atuais[chave_access] = str(val).strip()

    admin_email_env = os.environ.get("ADMIN_EMAIL")
    if admin_email_env:
        vars_atuais["ADMIN_EMAIL"] = str(admin_email_env).strip().lower()

    dados["vars"] = vars_atuais
    return dados


def _escrever_manifest_deploy(wrangler_path: Path, hostname: str | None) -> Path:
    """
    Grava o manifesto efêmero ao lado do original (mesmo diretório, para preservar o
    `assets.directory` relativo) com `workers_dev` ajustado ao alvo resolvido.
    """
    dados = _carregar_jsonc(wrangler_path)
    destino = wrangler_path.parent / NOME_CONFIG_DEPLOY
    destino.write_text(
        json.dumps(
            montar_manifest_deploy(dados, hostname), indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    return destino


def fazer_deploy_api(
    api_dir: Path | None = None,
    hostname: str | None = None,
    dry_run: bool = False,
) -> str | None:
    """
    Publica o Worker único `mbft` (API + assets estáticos) no Cloudflare Workers.

    Um Custom Domain para `<hostname>` é declarado quando um hostname é resolvido pela
    precedência `--hostname` > `MBFT_HOSTNAME`. Havendo hostname, o `workers_dev` é
    desativado; sem hostname, ele permanece habilitado como único endereço. Como o Wrangler
    não expõe flag de CLI para alternar `workers_dev`, um manifesto efêmero com o valor
    correto é gravado ao lado de `wrangler.jsonc` e passado via `--config`.
    Retorna o hostname usado (ou `None`).
    """
    if api_dir is None:
        api_dir = RAIZ_REPO / "apps" / "api"
    wrangler_path = api_dir / "wrangler.jsonc"
    if not wrangler_path.exists():
        raise FileNotFoundError(f"wrangler.jsonc não encontrado em {api_dir}")

    validar_assets_do_worker(wrangler_path)
    hostname = resolver_hostname_deploy(hostname)

    manifest_deploy = _escrever_manifest_deploy(wrangler_path, hostname)
    comando = ["wrangler", "deploy", "--config", str(manifest_deploy)]
    if hostname:
        descricao = (
            f"Publicar Worker mbft no Cloudflare Workers "
            f"(Custom Domain: {hostname}; workers.dev desativado)"
        )
    else:
        descricao = "Publicar Worker mbft no Cloudflare Workers (workers.dev)"

    try:
        rodar_comando_wrangler(comando, descricao, cwd=api_dir, dry_run=dry_run)
    finally:
        manifest_deploy.unlink(missing_ok=True)
    return hostname
