"""Entrypoint do Python Worker: adapta o app ASGI (FastAPI) ao runtime do Cloudflare Workers."""

from workers import asgi

from mbft_api.main import app

Default = asgi.entrypoint(app)
