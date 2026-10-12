"""Entrypoint do Python Worker: adapta o app ASGI (FastAPI) ao runtime do Cloudflare Workers.

O app é envolvido por :func:`mbft_api.asgi_prefix.normalizar_prefixo_asgi`, que remove o
prefixo externo ``/api`` antes de entregar o ``scope`` ao FastAPI — assim ``/api/busca/``
chega ao router interno como ``/busca/``, e ``/busca/`` sem prefixo continua funcionando.
"""

from mbft_api.asgi_prefix import normalizar_prefixo_asgi
from mbft_api.main import app
from workers import asgi

Default = asgi.entrypoint(normalizar_prefixo_asgi(app))
