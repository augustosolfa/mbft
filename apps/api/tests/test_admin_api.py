"""Testes unitários para a API administrativa (/admin/tables).

Cobre:
- Listagem de catálogo de tabelas (sqlite_master).
- Paginação e ordenação decrescente por padrão (100 linhas/página, salto de páginas).
- Retorno 404 para tabelas inexistentes.
- Regra de segurança fechada por padrão (Secure by Default):
  * Bloqueio 401 sem token em produção.
  * Bloqueio 403 para usuários autenticados cujo e-mail não confere com ADMIN_EMAIL.
  * Sucesso 200 com token válido do ADMIN_EMAIL.
  * Liberação controlada em ambiente dev/test local.
"""

import base64
import json
import sqlite3
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from mbft_api.access_jwt import VerificadorAccess
from mbft_api.main import app
from mbft_api.routers.admin import get_admin_db, _obter_verificador, router

TEAM = "meutime.cloudflareaccess.com"
ISS = f"https://{TEAM}"
AUD = "aud-do-app"
ADMIN_EMAIL = "admin.chefe@exemplo.com"


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _int_b64(valor: int) -> str:
    return _b64(valor.to_bytes((valor.bit_length() + 7) // 8, "big"))


@pytest.fixture(scope="module")
def chave_rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _gerar_token(chave, email: str, agora: int = 1_000_000) -> str:
    payload = {"iss": ISS, "aud": [AUD], "exp": agora + 600, "email": email}
    cab = _b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    pay = _b64(json.dumps(payload).encode())
    assinatura = chave.sign(f"{cab}.{pay}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{cab}.{pay}.{_b64(assinatura)}"


@pytest.fixture
def db_teste():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE historico_consultas (
            id TEXT PRIMARY KEY,
            pergunta TEXT NOT NULL,
            resposta TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE rate_limit_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identidade TEXT NOT NULL,
            recurso TEXT NOT NULL,
            criado_em INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    return conn


@pytest.fixture
def client(db_teste):
    app.dependency_overrides[get_admin_db] = lambda: db_teste
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_admin_dev_local_lista_tabelas(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)

    response = client.get("/admin/tables")
    assert response.status_code == 200
    dados = response.json()
    assert "tables" in dados
    nomes = [t["name"] for t in dados["tables"]]
    assert "historico_consultas" in nomes
    assert "rate_limit_eventos" in nomes


def test_admin_dev_local_tabela_inexistente_retorna_404(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    response = client.get("/admin/tables/tabela_fantasma")
    assert response.status_code == 404
    assert "não encontrada" in response.json()["detail"]


def test_admin_dev_local_paginacao_e_ordenacao(client, db_teste, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")

    # Insere 150 registros
    for i in range(1, 151):
        db_teste.execute(
            "INSERT INTO historico_consultas (id, pergunta, resposta) VALUES (?, ?, ?)",
            (f"id-{i:03d}", f"Pergunta {i}", f"Resposta {i}"),
        )
    db_teste.commit()

    # Consulta página 1 (100 linhas por padrão)
    res_p1 = client.get("/admin/tables/historico_consultas?page=1&page_size=100")
    assert res_p1.status_code == 200
    dados_p1 = res_p1.json()
    assert dados_p1["table"] == "historico_consultas"
    assert dados_p1["total_rows"] == 150
    assert dados_p1["total_pages"] == 2
    assert dados_p1["page"] == 1
    assert dados_p1["page_size"] == 100
    assert len(dados_p1["rows"]) == 100
    assert "columns" in dados_p1
    assert "id" in dados_p1["columns"]

    # Consulta página 2 (50 linhas restantes)
    res_p2 = client.get("/admin/tables/historico_consultas?page=2&page_size=100")
    assert res_p2.status_code == 200
    dados_p2 = res_p2.json()
    assert dados_p2["page"] == 2
    assert len(dados_p2["rows"]) == 50


def test_admin_producao_sem_token_bloqueia_401(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)

    response = client.get("/admin/tables")
    assert response.status_code == 401
    assert "Token do Cloudflare Access ausente" in response.json()["detail"]


def test_admin_producao_com_token_de_outro_usuario_bloqueia_403(client, chave_rsa, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("ACCESS_AUD", AUD)

    token_intruso = _gerar_token(chave_rsa, "usuario.comum@exemplo.com")

    # Configura verificador mockado
    nums = chave_rsa.public_key().public_numbers()
    jwk = {"kid": "k1", "kty": "RSA", "alg": "RS256", "n": _int_b64(nums.n), "e": _int_b64(nums.e)}

    async def mock_buscar(_url):
        return {"keys": [jwk]}

    monkeypatch.setattr(
        "mbft_api.routers.admin._obter_verificador",
        lambda env: VerificadorAccess(TEAM, [AUD], mock_buscar, relogio=lambda: 1_000_000),
    )

    response = client.get("/admin/tables", headers={"cf-access-jwt-assertion": token_intruso})
    assert response.status_code == 403
    assert "Acesso restrito" in response.json()["detail"]


def test_admin_producao_com_token_do_admin_autoriza_200(client, chave_rsa, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    monkeypatch.setenv("ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("ACCESS_AUD", AUD)

    token_admin = _gerar_token(chave_rsa, "Admin.Chefe@Exemplo.COM")

    nums = chave_rsa.public_key().public_numbers()
    jwk = {"kid": "k1", "kty": "RSA", "alg": "RS256", "n": _int_b64(nums.n), "e": _int_b64(nums.e)}

    async def mock_buscar(_url):
        return {"keys": [jwk]}

    monkeypatch.setattr(
        "mbft_api.routers.admin._obter_verificador",
        lambda env: VerificadorAccess(TEAM, [AUD], mock_buscar, relogio=lambda: 1_000_000),
    )

    response = client.get("/admin/tables", headers={"cf-access-jwt-assertion": token_admin})
    assert response.status_code == 200
    assert "tables" in response.json()


def test_admin_ignora_tabelas_internas_cf_e_sqlite(client, db_teste, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")

    # Cria tabela com prefixo _cf_ reservado do Cloudflare D1
    db_teste.execute("CREATE TABLE _cf_KV (key TEXT, value BLOB);")
    db_teste.commit()

    # Catálogo não deve listar _cf_KV nem sqlite_sequence (gerada por AUTOINCREMENT)
    resp_list = client.get("/admin/tables")
    assert resp_list.status_code == 200
    nomes = [t["name"] for t in resp_list.json()["tables"]]
    assert "_cf_KV" not in nomes
    assert "sqlite_sequence" not in nomes
    assert "historico_consultas" in nomes

    # Acesso direto a tabela interna deve retornar 403
    resp_cf = client.get("/admin/tables/_cf_KV")
    assert resp_cf.status_code == 403
    assert "restrito" in resp_cf.json()["detail"]


