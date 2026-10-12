"""Normalização do prefixo externo ``/api`` para as rotas internas do FastAPI.

O Worker ``mbft`` publica o site estático e a API na mesma origem. O frontend chama
``/api/busca/``, ``/api/chat/`` e ``/api/health/`` enquanto os routers internos do
FastAPI permanecem declarados sem prefixo (``/busca/``, ``/chat/`` e ``/health/``).

Este adapter ASGI remove *somente* o prefixo externo do ``scope`` antes de entregá-lo
ao FastAPI, preservando também os caminhos sem prefixo. ``API_PREFIX`` é a fonte única
do prefixo: alimenta tanto este adapter quanto a regra ``assets.run_worker_first`` do
``wrangler.jsonc`` (via ``RUN_WORKER_FIRST_PATTERNS``), impedindo divergência entre o
roteamento do edge e a normalização da aplicação.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

# Prefixo externo canônico aceito pelo Worker (e pela regra assets.run_worker_first).
API_PREFIX = "/api"

# Padrões que o Wrangler deve rotear para o Worker antes de servir assets estáticos.
RUN_WORKER_FIRST_PATTERNS: tuple[str, ...] = (f"{API_PREFIX}/*",)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def normalizar_prefixo_asgi(app: ASGIApp, prefix: str = API_PREFIX) -> ASGIApp:
    """Envolve um app ASGI removendo ``prefix`` de ``path``/``raw_path`` quando presente.

    A remoção só ocorre quando o caminho é exatamente o prefixo ou começa por
    ``<prefix>/``; portanto ``/apixyz`` e ``/busca/`` passam incólumes.
    """
    if not prefix or not prefix.startswith("/") or prefix.endswith("/"):
        raise ValueError(f"prefixo externo inválido: {prefix!r}")

    tamanho = len(prefix)

    async def wrapper(scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") in ("http", "websocket"):
            caminho = scope.get("path") or ""
            novo_caminho: str | None = None
            if caminho == prefix:
                novo_caminho = "/"
            elif caminho.startswith(f"{prefix}/"):
                novo_caminho = caminho[tamanho:]

            if novo_caminho is not None:
                scope = dict(scope)
                scope["path"] = novo_caminho
                raw_path = scope.get("raw_path")
                if isinstance(raw_path, (bytes, bytearray)) and bytes(
                    raw_path
                ).startswith(prefix.encode()):
                    restante = bytes(raw_path)[tamanho:] or b"/"
                    scope["raw_path"] = restante
        await app(scope, receive, send)

    return wrapper
