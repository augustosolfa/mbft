import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from mbft_api.access_jwt import VerificadorAccess, verificar_rs256

TEAM = "meutime.cloudflareaccess.com"
ISS = f"https://{TEAM}"
AUD = "aud-do-app"


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _int_b64(valor: int) -> str:
    return _b64(valor.to_bytes((valor.bit_length() + 7) // 8, "big"))


@pytest.fixture(scope="module")
def chave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(chave, kid="k1"):
    nums = chave.public_key().public_numbers()
    return {"kid": kid, "kty": "RSA", "alg": "RS256", "n": _int_b64(nums.n), "e": _int_b64(nums.e)}


def _token(chave, *, agora=1_000_000, kid="k1", alg="RS256", **claims):
    payload = {"iss": ISS, "aud": [AUD], "exp": agora + 600, "email": "Ana@Exemplo.com", **claims}
    cab = _b64(json.dumps({"alg": alg, "kid": kid}).encode())
    pay = _b64(json.dumps(payload).encode())
    assinatura = chave.sign(f"{cab}.{pay}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{cab}.{pay}.{_b64(assinatura)}"


def _verificador(chave, agora=1_000_000, contador=None):
    async def buscar(url):
        if contador is not None:
            contador.append(url)
        return {"keys": [_jwk(chave)]}

    return VerificadorAccess(TEAM, [AUD], buscar, relogio=lambda: agora)


@pytest.mark.asyncio
async def test_token_valido_devolve_email_minusculo(chave):
    assert await _verificador(chave).email_verificado(_token(chave)) == "ana@exemplo.com"


@pytest.mark.asyncio
async def test_jwks_e_buscado_uma_vez_e_cacheado(chave):
    chamadas = []
    v = _verificador(chave, contador=chamadas)
    await v.email_verificado(_token(chave))
    await v.email_verificado(_token(chave))
    assert chamadas == [f"{ISS}/cdn-cgi/access/certs"]


@pytest.mark.asyncio
@pytest.mark.parametrize("claims", [
    {"aud": ["outro-app"]},
    {"iss": "https://outro.cloudflareaccess.com"},
    {"exp": 1_000_000 - 3600},
    {"email": "sem-arroba"},
])
async def test_claims_invalidos_viram_anonimo(chave, claims):
    assert await _verificador(chave).email_verificado(_token(chave, **claims)) is None


@pytest.mark.asyncio
async def test_assinatura_adulterada_rejeitada(chave):
    cab, pay, sig = _token(chave).split(".")
    pay_falso = _b64(json.dumps({"iss": ISS, "aud": [AUD], "exp": 9_999_999, "email": "root@x.com"}).encode())
    assert await _verificador(chave).email_verificado(f"{cab}.{pay_falso}.{sig}") is None


@pytest.mark.asyncio
async def test_alg_none_e_kid_desconhecido_rejeitados(chave):
    assert await _verificador(chave).email_verificado(_token(chave, alg="none")) is None
    assert await _verificador(chave).email_verificado(_token(chave, kid="inexistente")) is None


@pytest.mark.asyncio
async def test_lixo_e_vazio_viram_anonimo(chave):
    v = _verificador(chave)
    for entrada in (None, "", "abc", "a.b.c", "a.b"):
        assert await v.email_verificado(entrada) is None


def test_verificar_rs256_concorda_com_biblioteca_padrao(chave):
    dados = b"cabecalho.payload"
    sig = chave.sign(dados, padding.PKCS1v15(), hashes.SHA256())
    jwk = _jwk(chave)
    assert verificar_rs256(dados, sig, jwk["n"], jwk["e"]) is True
    assert verificar_rs256(dados + b"x", sig, jwk["n"], jwk["e"]) is False
