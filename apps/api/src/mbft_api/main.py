from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, busca, ticket, chat

app = FastAPI(
    title="MBFT API",
    description="API Gateway e Ticketizador do Manual Brasileiro de Fiscalização de Trânsito",
    version="1.0.0"
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
