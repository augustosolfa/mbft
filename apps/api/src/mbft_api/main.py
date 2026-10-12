import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, busca, chat

from contextlib import asynccontextmanager
from pathlib import Path
from .recuperador.buscador import BuscadorHibrido

@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    if sys.platform == "emscripten":
        print("Ambiente Pyodide (Cloudflare Workers) detectado. Pulando adaptadores locais pesados (PyTorch/SQLite).")
        app.state.buscador = None
        app.state.gerador = None
        app.state.historico_repo = None
        yield
        return
        
    print("Inicializando modelos pesados do Recuperador (Modo Local)...")
    try:
        from .recuperador.local_adapters import LocalSqliteDB, NumpyVectorDB, PyTorchEmbedder
        project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        jsonl_path = project_root / "data" / "processed" / "indexador" / "embeddings_mbft.jsonl"
        
        if jsonl_path.exists():
            vector_db = NumpyVectorDB(jsonl_path)
            relational_db = LocalSqliteDB(jsonl_path)
            ai_client = PyTorchEmbedder("BAAI/bge-m3")
            
            app.state.buscador = BuscadorHibrido(vector_db, relational_db, ai_client)
            print("Modelos carregados com sucesso!")
        else:
            print("Aviso: embeddings_mbft.jsonl não encontrado. Busca local indisponível.")
            app.state.buscador = None
            
        # Tenta carregar o Gerador LLM local (salvo se LLM_PROVIDER apontar para outro provedor)
        llm_provider = os.environ.get("LLM_PROVIDER", "gemini").strip().lower()
        if llm_provider in ("gemini", "google", ""):
            try:
                from .gerador.local_adapters import GeminiLLMClient
                from .gerador.orquestrador import OrquestradorGeracao
                app.state.gerador = OrquestradorGeracao(GeminiLLMClient())
                print("Gerador LLM (Gemini) engatilhado.")
            except Exception as e:
                print(f"Aviso: Não foi possível carregar o Gerador LLM: {e}")
                app.state.gerador = None
        else:
            app.state.gerador = None

        from .database import HistoricoRepository
        app.state.historico_repo = HistoricoRepository()
            
    except ImportError:
        print("Aviso: Adaptadores locais (PyTorch) não instalados. Pulando...")
        app.state.buscador = None
        app.state.gerador = None
        app.state.historico_repo = None
        
    yield
    print("Encerrando recursos...")

DEFAULT_LOCAL_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
)


def obter_cors_origins(cors_csv: str | None = None) -> list[str]:
    """
    Resolve a lista de origens permitidas no CORS combinando as portas locais de desenvolvimento
    com as origens declaradas em `CORS_ORIGINS` (separadas por vírgula), rejeitando curingas (`*`).
    """
    raw = cors_csv if cors_csv is not None else os.environ.get("CORS_ORIGINS", "")
    origens = list(DEFAULT_LOCAL_CORS_ORIGINS)
    for item in str(raw or "").split(","):
        origem = item.strip().rstrip("/")
        if origem and origem != "*" and origem not in origens:
            origens.append(origem)
    return origens


class EnvAwareCORSMiddleware(CORSMiddleware):
    """Atualiza dinamicamente `allow_origins` a partir de `scope['env'].CORS_ORIGINS` ou `os.environ`."""

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http":
            env_obj = scope.get("env")
            cors_env = None
            if env_obj is not None:
                cors_env = (
                    env_obj.get("CORS_ORIGINS")
                    if isinstance(env_obj, dict)
                    else getattr(env_obj, "CORS_ORIGINS", None)
                )
            if not cors_env or type(cors_env).__name__ in ("JsNull", "JsUndefined"):
                cors_env = os.environ.get("CORS_ORIGINS", "")
            self.allow_origins = obter_cors_origins(str(cors_env))
        await super().__call__(scope, receive, send)


app = FastAPI(
    title="MBFT API",
    description="API Gateway e RAG do Manual Brasileiro de Fiscalização de Trânsito",
    version="1.0.0",
    lifespan=lifespan
)

# Configuração de CORS (Bloqueia sites de terceiros de sugar nossa IA)
app.add_middleware(
    EnvAwareCORSMiddleware,
    allow_origins=obter_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(busca.router)
app.include_router(chat.router)


