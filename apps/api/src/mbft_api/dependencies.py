from collections.abc import Mapping
import os
from typing import Any

from fastapi import HTTPException, Request

from .database import HistoricoRepository
from .gerador.cloudflare_adapters import DEFAULT_CF_LLM_MODEL, WorkersAILLMClient
from .gerador.orquestrador import OrquestradorGeracao
from .recuperador.buscador import BuscadorHibrido
from .recuperador.cloudflare_adapters import (
    D1RelationalDB,
    VectorizeDB,
    WorkersAIEmbedder,
    is_js_null_or_undefined,
)


def _get_app_state_attr(request: Request, attr: str) -> Any:
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    return getattr(state, attr, None)


def get_env_binding(env: Any, key: str, default: Any = None) -> Any:
    """
    Extrai um binding ou variável de `request.scope["env"]` de forma compatível
    tanto com dicionários Python (`dict`/`os.environ`) quanto com objetos `JsProxy`
    do Cloudflare Workers (Pyodide).
    """
    if is_js_null_or_undefined(env):
        return default

    if isinstance(env, Mapping):
        val = env.get(key, default)
        return default if is_js_null_or_undefined(val) else val

    try:
        val = getattr(env, key)
        if not is_js_null_or_undefined(val):
            return val
    except AttributeError:
        pass

    try:
        val = env[key]
        if not is_js_null_or_undefined(val):
            return val
    except (KeyError, TypeError, IndexError):
        pass

    return default


def get_buscador(request: Request) -> BuscadorHibrido:
    """
    Dependência FastAPI por requisição para o motor de Busca Híbrida (`BuscadorHibrido`):
    1. Detecta automaticamente os bindings `DB`, `VECTORIZE` e `AI` em `request.scope["env"]` (Cloudflare Workers);
    2. Faz fallback para `request.app.state.buscador` no modo de desenvolvimento local.
    """
    env = request.scope.get("env")
    db_binding = get_env_binding(env, "DB")
    vectorize_binding = get_env_binding(env, "VECTORIZE")
    ai_binding = get_env_binding(env, "AI")

    if db_binding is not None and vectorize_binding is not None and ai_binding is not None:
        return BuscadorHibrido(
            vector_db=VectorizeDB(vectorize_binding),
            relational_db=D1RelationalDB(db_binding),
            ai_client=WorkersAIEmbedder(ai_binding),
        )

    buscador = _get_app_state_attr(request, "buscador")
    if buscador is not None:
        return buscador

    raise HTTPException(status_code=503, detail="Mecanismo de busca indisponível.")


def _obter_ou_criar_gerador_gemini(request: Request) -> OrquestradorGeracao:
    gerador = _get_app_state_attr(request, "gerador")
    if gerador is not None:
        return gerador
    try:
        from .gerador.local_adapters import GeminiLLMClient

        novo_gerador = OrquestradorGeracao(GeminiLLMClient())
        app = getattr(request, "app", None)
        state = getattr(app, "state", None)
        if state is not None:
            setattr(state, "gerador", novo_gerador)
        return novo_gerador
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Motor de Inteligência Indisponível.",
        ) from exc


def get_gerador(request: Request) -> OrquestradorGeracao:
    """
    Dependência FastAPI por requisição para o orquestrador LLM (`OrquestradorGeracao`):
    - Permite override explícito via `LLM_PROVIDER` (`workers_ai`/`cloudflare` ou `gemini`);
    - Sem override, detecta automaticamente o binding `AI` em `request.scope["env"]` (parametrizado por `CF_LLM_MODEL`)
      e faz fallback para `request.app.state.gerador` no modo local.
    """
    env = request.scope.get("env")
    raw_provider = get_env_binding(env, "LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or ""
    provider = str(raw_provider).strip().lower()

    cf_model_raw = get_env_binding(env, "CF_LLM_MODEL") or os.environ.get("CF_LLM_MODEL")
    cf_model = str(cf_model_raw).strip() if cf_model_raw else DEFAULT_CF_LLM_MODEL

    ai_binding = get_env_binding(env, "AI")

    if provider:
        if provider in ("workers_ai", "workers-ai", "cloudflare", "cf"):
            if ai_binding is None:
                raise HTTPException(
                    status_code=503,
                    detail="Motor de Inteligência Indisponível (binding AI ausente).",
                )
            return OrquestradorGeracao(WorkersAILLMClient(ai_binding, model=cf_model))

        if provider in ("gemini", "google"):
            return _obter_ou_criar_gerador_gemini(request)

        raise HTTPException(
            status_code=503,
            detail=f"Provedor LLM '{provider}' não suportado ou indisponível.",
        )

    if ai_binding is not None:
        return OrquestradorGeracao(WorkersAILLMClient(ai_binding, model=cf_model))

    gerador = _get_app_state_attr(request, "gerador")
    if gerador is not None:
        return gerador

    raise HTTPException(status_code=503, detail="Motor de Inteligência Indisponível.")


def get_historico_repo(request: Request) -> HistoricoRepository:
    """
    Dependência FastAPI por requisição para o repositório de histórico e cache:
    1. Se houver binding 'DB' em request.scope['env'] (Cloudflare Workers / Miniflare),
       utiliza D1.
    2. Se houver 'historico_repo' em request.app.state, utiliza-o.
    3. Caso contrário, inicializa um repositório SQLite em memória local e armazena
       em request.app.state para persistência durante o ciclo da aplicação.
    """
    env = request.scope.get("env")
    db_binding = get_env_binding(env, "DB")
    if db_binding is not None:
        return HistoricoRepository(db_binding)

    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    if state is not None:
        repo = getattr(state, "historico_repo", None)
        if repo is not None:
            return repo

        novo_repo = HistoricoRepository()
        setattr(state, "historico_repo", novo_repo)
        return novo_repo

    return HistoricoRepository()
