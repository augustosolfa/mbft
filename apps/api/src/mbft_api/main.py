from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, busca, ticket, chat

from contextlib import asynccontextmanager
from pathlib import Path
from mbft_recuperador.buscador import BuscadorHibrido

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Inicializando modelos pesados do Recuperador (Modo Local)...")
    try:
        from mbft_recuperador.local_adapters import LocalSqliteDB, NumpyVectorDB, PyTorchEmbedder
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
    except ImportError:
        print("Aviso: Adaptadores locais (PyTorch) não instalados. Pulando...")
        app.state.buscador = None
        
    yield
    print("Encerrando recursos...")

app = FastAPI(
    title="MBFT API",
    description="API Gateway e Ticketizador do Manual Brasileiro de Fiscalização de Trânsito",
    version="1.0.0",
    lifespan=lifespan
)

# Configuração de CORS (Essencial para SPA no Pages consumindo a API no Workers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Substituir em prod pelo domínio do Cloudflare Pages
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(busca.router)
app.include_router(ticket.router)
app.include_router(chat.router)
