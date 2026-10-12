import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mbft_api import rate_limit
from mbft_api.dependencies import get_buscador
from mbft_api.main import app
from mbft_api.rate_limit import (
    Identidade, LimitadorTaxa, RateLimitRepository, get_rate_limit_repo, normalizar_ip,
)

ANON = Identidade("ip", "ip:aaa")
LOGADO = Identidade("email", "email:bbb")


class Relogio:
    def __init__(self, t=1_000_000):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def _zerar_limpeza(monkeypatch):
    monkeypatch.setattr(rate_limit, "_ultima_limpeza", 0)


def _limitador(identidade=ANON, relogio=None, repo=None):
    relogio = relogio or Relogio()
    return LimitadorTaxa(repo or RateLimitRepository(), identidade, relogio), relogio


async def _bloqueado(limitador, recurso, **kw):
    with pytest.raises(HTTPException) as exc:
        await limitador.consumir(recurso, **kw)
    return exc.value


@pytest.mark.asyncio
async def test_intervalo_anonimo_30s_e_retry_after():
    lim, rel = _limitador()
    await lim.consumir("busca")
    rel.t += 10
    erro = await _bloqueado(lim, "busca")
    assert erro.status_code == 429 and erro.headers["Retry-After"] == "20"
    rel.t += 21
    await lim.consumir("busca")


@pytest.mark.asyncio
async def test_logado_busca_intervalo_10s():
    lim, rel = _limitador(LOGADO)
    await lim.consumir("busca")
    rel.t += 11
    await lim.consumir("busca")


@pytest.mark.asyncio
async def test_cota_diaria_chat_anonimo_1_por_dia():
    lim, rel = _limitador()
    await lim.consumir("chat")
    rel.t += 31
    erro = await _bloqueado(lim, "chat")
    assert erro.status_code == 429 and "diário" in erro.detail
    assert int(erro.headers["Retry-After"]) == 86_400 - 31
    rel.t += 86_400
    await lim.consumir("chat")


@pytest.mark.asyncio
async def test_cota_diaria_busca_anonimo_15():
    lim, rel = _limitador()
    for _ in range(15):
        await lim.consumir("busca")
        rel.t += 31
    erro = await _bloqueado(lim, "busca")
    assert "diário" in erro.detail


@pytest.mark.asyncio
async def test_cache_hit_nao_consome_cota_diaria():
    lim, rel = _limitador()
    await lim.consumir("chat", conta_cota=False)
    rel.t += 31
    await lim.consumir("chat", conta_cota=True)  # a cota (1) continua livre
    rel.t += 31
    await lim.consumir("chat", conta_cota=False)  # cota esgotada, mas HIT ainda passa
    erro = await _bloqueado(lim, "chat", conta_cota=False)  # intervalo vale também no HIT
    assert "Aguarde" in erro.detail


@pytest.mark.asyncio
async def test_busca_e_chat_sao_independentes_e_identidades_tambem():
    repo, rel = RateLimitRepository(), Relogio()
    anon, _ = _limitador(ANON, rel, repo)
    logado, _ = _limitador(LOGADO, rel, repo)
    await anon.consumir("busca")
    await anon.consumir("chat")
    await logado.consumir("busca")


@pytest.mark.asyncio
async def test_falha_do_repositorio_bloqueia_com_503():
    class Quebrado:
        async def tentar_registrar(self, *a, **k):
            raise RuntimeError("D1 fora")

    lim = LimitadorTaxa(Quebrado(), ANON, Relogio())
    erro = await _bloqueado(lim, "busca")
    assert erro.status_code == 503


@pytest.mark.asyncio
async def test_limpeza_remove_eventos_antigos():
    repo, rel = RateLimitRepository(), Relogio()
    lim, _ = _limitador(ANON, rel, repo)
    await lim.consumir("busca")  # dispara a limpeza (nada a apagar ainda)
    await repo.limpar_antigos(rel.t + 90_001)
    n = repo.db.execute("SELECT COUNT(*) FROM rate_limit_eventos").fetchone()[0]
    assert n == 0


def test_normalizar_ip():
    assert normalizar_ip("203.0.113.9") == "203.0.113.9"
    assert normalizar_ip("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == normalizar_ip("2001:db8:1:2::1")
    assert normalizar_ip("2001:db8:1:3::1") != normalizar_ip("2001:db8:1:2::1")


class _BuscadorVazio:
    async def recuperar_contexto(self, q, limit=5):
        return []


@pytest.mark.limite_real
def test_http_busca_429_com_retry_after_e_buckets_por_ip():
    repo = RateLimitRepository()
    app.dependency_overrides[get_buscador] = lambda: _BuscadorVazio()
    app.dependency_overrides[get_rate_limit_repo] = lambda: repo
    try:
        client = TestClient(app)
        a = {"cf-connecting-ip": "198.51.100.1"}
        b = {"cf-connecting-ip": "198.51.100.2"}
        assert client.get("/busca/", params={"q": "cinto"}, headers=a).status_code == 200
        r = client.get("/busca/", params={"q": "cinto"}, headers=a)
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        assert client.get("/busca/", params={"q": "cinto"}, headers=b).status_code == 200
        assert client.get("/busca/", params={"q": "x"}, headers=a).status_code in (422, 429)
    finally:
        app.dependency_overrides.clear()
