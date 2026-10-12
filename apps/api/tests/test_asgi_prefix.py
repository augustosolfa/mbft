"""Testes do adapter ASGI que normaliza o prefixo externo ``/api`` (PMS-008 / PMS-010)."""

import pytest
from mbft_api.asgi_prefix import (
    API_PREFIX,
    RUN_WORKER_FIRST_PATTERNS,
    normalizar_prefixo_asgi,
)


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(_message):
    return None


def _coletor():
    recebidos: list[dict] = []

    async def app_interna(scope, receive, send):
        recebidos.append(scope)

    return recebidos, normalizar_prefixo_asgi(app_interna)


def test_prefixo_canonico_e_o_esperado_pelo_edge():
    assert API_PREFIX == "/api"
    assert RUN_WORKER_FIRST_PATTERNS == ("/api/*",)


@pytest.mark.asyncio
async def test_prefixo_api_e_removido_antes_de_entregar_o_scope_ao_fastapi():
    recebidos, wrapper = _coletor()

    await wrapper(
        {"type": "http", "path": "/api/busca/", "raw_path": b"/api/busca/"},
        _receive,
        _send,
    )

    assert recebidos[-1]["path"] == "/busca/"
    assert recebidos[-1]["raw_path"] == b"/busca/"


@pytest.mark.asyncio
async def test_rotas_sem_prefixo_continuam_funcionando():
    recebidos, wrapper = _coletor()

    await wrapper({"type": "http", "path": "/chat/"}, _receive, _send)
    await wrapper({"type": "http", "path": "/health/"}, _receive, _send)

    assert recebidos[0]["path"] == "/chat/"
    assert recebidos[1]["path"] == "/health/"


@pytest.mark.asyncio
async def test_prefixo_isolado_e_convertido_para_raiz():
    recebidos, wrapper = _coletor()

    await wrapper({"type": "http", "path": "/api"}, _receive, _send)

    assert recebidos[-1]["path"] == "/"


@pytest.mark.asyncio
async def test_caminhos_com_prefixo_parcial_nao_sao_reescritos():
    recebidos, wrapper = _coletor()

    await wrapper({"type": "http", "path": "/apixyz/busca/"}, _receive, _send)
    await wrapper({"type": "http", "path": "/busca/"}, _receive, _send)

    assert recebidos[0]["path"] == "/apixyz/busca/"
    assert recebidos[1]["path"] == "/busca/"


@pytest.mark.asyncio
async def test_requisicoes_nao_http_nao_sao_alteradas():
    recebidos, wrapper = _coletor()

    await wrapper({"type": "lifespan", "path": "/api/"}, _receive, _send)

    assert recebidos[-1]["path"] == "/api/"


def test_prefixo_invalido_e_rejeitado():
    async def app_interna(scope, receive, send):  # pragma: no cover - nunca invocado
        raise AssertionError("não deveria ser chamado")

    with pytest.raises(ValueError):
        normalizar_prefixo_asgi(app_interna, prefix="/api/")
