"""Validação do JWT do Cloudflare Access (RS256) em Python puro, sem dependências (PMS-011).

O e-mail só é aceito depois de verificar assinatura, emissor (`iss`), audiência (`aud`) e
validade (`exp`/`nbf`). Qualquer falha devolve ``None`` (o chamador trata como anônimo).
"""

import base64
import hashlib
import hmac
import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Prefixo DER do DigestInfo para SHA-256 (RFC 8017, seção 9.2).
_DIGESTINFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")

JWKS_TTL_S = 3600
JWKS_REFETCH_MIN_S = 60
TOLERANCIA_RELOGIO_S = 30

BuscarJson = Callable[[str], Awaitable[dict]]


def _b64url_decode(valor: str) -> bytes:
    return base64.urlsafe_b64decode(valor + "=" * (-len(valor) % 4))


def verificar_rs256(signing_input: bytes, assinatura: bytes, n_b64: str, e_b64: str) -> bool:
    """Verifica uma assinatura RSASSA-PKCS1-v1_5 com SHA-256 (JWT `RS256`)."""
    n = int.from_bytes(_b64url_decode(n_b64), "big")
    e = int.from_bytes(_b64url_decode(e_b64), "big")
    if n <= 0 or e < 3:
        return False
    k = (n.bit_length() + 7) // 8
    if len(assinatura) != k:
        return False
    s = int.from_bytes(assinatura, "big")
    if s >= n:
        return False
    mensagem_codificada = pow(s, e, n).to_bytes(k, "big")
    t = _DIGESTINFO_SHA256 + hashlib.sha256(signing_input).digest()
    if k < len(t) + 11:
        return False
    esperado = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return hmac.compare_digest(mensagem_codificada, esperado)


async def buscar_json_http(url: str) -> dict:
    """GET que devolve JSON. Usa o fetch do runtime no Workers (Pyodide) e urllib localmente."""
    if sys.platform == "emscripten":
        try:
            from workers import fetch  # SDK do Python Workers
        except ImportError:
            from js import fetch  # fallback do Pyodide
        resposta = await fetch(url)
        if not resposta.ok:
            raise RuntimeError(f"HTTP {resposta.status} ao buscar {url}")
        return json.loads(str(await resposta.text()))

    import asyncio
    import urllib.request

    def _obter() -> dict:
        with urllib.request.urlopen(url, timeout=5) as resposta:  # noqa: S310
            return json.loads(resposta.read())

    return await asyncio.to_thread(_obter)


class VerificadorAccess:
    """Valida tokens do Access de um team domain e guarda as chaves públicas (JWKS) em cache."""

    def __init__(
        self,
        team_domain: str,
        audiencias: list[str],
        buscar_json: BuscarJson = buscar_json_http,
        relogio: Callable[[], float] = time.time,
    ):
        dominio = team_domain.strip().removeprefix("https://").rstrip("/")
        self.issuer = f"https://{dominio}"
        self.audiencias = [a for a in audiencias if a]
        self._buscar_json = buscar_json
        self._relogio = relogio
        self._chaves: dict[str, dict[str, Any]] = {}
        self._carregado_em = 0.0
        self._ultima_tentativa = -1e12

    async def _obter_chave(self, kid: Optional[str]) -> Optional[dict[str, Any]]:
        agora = self._relogio()
        expirou = agora - self._carregado_em > JWKS_TTL_S
        faltando = not kid or kid not in self._chaves
        if (faltando or expirou) and agora - self._ultima_tentativa >= JWKS_REFETCH_MIN_S:
            self._ultima_tentativa = agora
            try:
                dados = await self._buscar_json(f"{self.issuer}/cdn-cgi/access/certs")
                chaves = {
                    k["kid"]: k
                    for k in dados.get("keys", [])
                    if k.get("kty") == "RSA" and k.get("kid") and k.get("n") and k.get("e")
                }
                if chaves:
                    self._chaves = chaves
                    self._carregado_em = agora
            except Exception as exc:
                logger.warning("Falha ao buscar JWKS do Access: %s", exc)
        return self._chaves.get(kid) if kid else None

    async def email_verificado(self, token: Optional[str]) -> Optional[str]:
        """Devolve o e-mail (minúsculo) se o token for válido; senão ``None``."""
        if not token:
            return None
        try:
            cab_b64, pay_b64, sig_b64 = token.split(".")
            cabecalho = json.loads(_b64url_decode(cab_b64))
            payload = json.loads(_b64url_decode(pay_b64))
            if cabecalho.get("alg") != "RS256":
                return None
            chave = await self._obter_chave(cabecalho.get("kid"))
            if chave is None:
                return None
            if not verificar_rs256(
                f"{cab_b64}.{pay_b64}".encode("ascii"), _b64url_decode(sig_b64), chave["n"], chave["e"]
            ):
                return None
            agora = self._relogio()
            if payload.get("iss") != self.issuer:
                return None
            aud = payload.get("aud")
            aud = [aud] if isinstance(aud, str) else (aud or [])
            if not any(a in self.audiencias for a in aud):
                return None
            exp = payload.get("exp")
            if not isinstance(exp, (int, float)) or agora > exp + TOLERANCIA_RELOGIO_S:
                return None
            nbf = payload.get("nbf")
            if isinstance(nbf, (int, float)) and agora + TOLERANCIA_RELOGIO_S < nbf:
                return None
            email = payload.get("email")
            if not isinstance(email, str) or "@" not in email:
                return None
            return email.strip().lower()
        except Exception:
            return None
