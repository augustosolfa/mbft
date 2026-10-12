"""Rate limit por identidade (IP ou e-mail do Cloudflare Access) sobre D1/SQLite (PMS-011)."""

import hashlib
import hmac
import ipaddress
import logging
import math
import os
import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request

from .access_jwt import VerificadorAccess, buscar_json_http
from .database import _resolver_awaitable, _to_python
from .dependencies import get_env_binding

logger = logging.getLogger(__name__)

SEGUNDOS_24H = 86_400
RETENCAO_S = 90_000  # 25 h: margem sobre a janela de 24 h
INTERVALO_LIMPEZA_S = 600
SAL_DEV = "mbft-dev-salt"  # só usado fora do Workers (sem binding DB)


@dataclass(frozen=True)
class Limite:
    intervalo_s: int
    diario: int


# (tipo da identidade, recurso) -> limite. Fonte única dos números (PMS-011).
LIMITES: dict[tuple[str, str], Limite] = {
    ("ip", "busca"): Limite(intervalo_s=30, diario=15),
    ("ip", "chat"): Limite(intervalo_s=30, diario=1),
    ("email", "busca"): Limite(intervalo_s=10, diario=60),
    ("email", "chat"): Limite(intervalo_s=30, diario=5),
}


@dataclass(frozen=True)
class Identidade:
    tipo: str  # "ip" | "email"
    chave: str  # "<tipo>:<hmac hex>"


@dataclass(frozen=True)
class Resultado:
    permitido: bool
    motivo: Optional[str] = None  # "intervalo" | "diario"
    retry_after_s: int = 0


_SQL_CRIAR_TABELA = """
CREATE TABLE IF NOT EXISTS rate_limit_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identidade TEXT NOT NULL,
    recurso TEXT NOT NULL,
    criado_em INTEGER NOT NULL,
    conta_cota INTEGER NOT NULL DEFAULT 1
)
"""

# Atômico: só insere se (a) nenhum evento no intervalo e (b) cota diária não esgotada
# (a cota só é checada quando conta_cota = 1). Ordem dos 12 parâmetros:
# identidade, recurso, agora, conta | identidade, recurso, agora-intervalo | conta |
# identidade, recurso, agora-86400, limite_diario
_SQL_INSERIR = """
INSERT INTO rate_limit_eventos (identidade, recurso, criado_em, conta_cota)
SELECT ?, ?, ?, ?
WHERE NOT EXISTS (
    SELECT 1 FROM rate_limit_eventos
    WHERE identidade = ? AND recurso = ? AND criado_em > ?
)
AND (? = 0 OR (
    SELECT COALESCE(SUM(conta_cota), 0) FROM rate_limit_eventos
    WHERE identidade = ? AND recurso = ? AND criado_em > ?
) < ?)
"""

_SQL_ULTIMO_NO_INTERVALO = """
SELECT MAX(criado_em) AS valor FROM rate_limit_eventos
WHERE identidade = ? AND recurso = ? AND criado_em > ?
"""

_SQL_MAIS_ANTIGO_DA_COTA = """
SELECT MIN(criado_em) AS valor FROM (
    SELECT criado_em FROM rate_limit_eventos
    WHERE identidade = ? AND recurso = ? AND conta_cota = 1 AND criado_em > ?
    ORDER BY criado_em DESC LIMIT ?
)
"""

_SQL_LIMPAR = "DELETE FROM rate_limit_eventos WHERE criado_em < ?"


def _extrair_changes(res: Any) -> int:
    meta = res.get("meta") if isinstance(res, Mapping) else getattr(res, "meta", None)
    meta = _to_python(meta)
    changes = meta.get("changes") if isinstance(meta, Mapping) else getattr(meta, "changes", 0)
    try:
        return int(_to_python(changes) or 0)
    except (TypeError, ValueError):
        return 0


def _extrair_primeira_linha(res: Any) -> Optional[dict]:
    linhas = res.get("results") if isinstance(res, Mapping) else getattr(res, "results", None)
    linhas = _to_python(linhas) or []
    if linhas:
        primeira = _to_python(linhas[0])
        if isinstance(primeira, Mapping):
            return dict(primeira)
    return None


def _valor_int(linha: Optional[dict]) -> Optional[int]:
    if not linha:
        return None
    valor = _to_python(linha.get("valor"))
    return int(valor) if valor is not None else None


class RateLimitRepository:
    """Persistência dos eventos. Suporta Cloudflare D1 (binding) e SQLite local/em memória."""

    def __init__(self, db: Any = None):
        if db is None:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute(_SQL_CRIAR_TABELA)
            conn.commit()
            self.db = conn
        else:
            self.db = db
            if isinstance(db, sqlite3.Connection):
                db.execute(_SQL_CRIAR_TABELA)
                db.commit()

    async def _executar(self, sql: str, params: tuple) -> tuple[int, Optional[dict]]:
        """Executa e devolve (linhas_afetadas, primeira_linha_ou_None)."""
        if hasattr(self.db, "prepare") and callable(getattr(self.db, "prepare")):
            stmt = self.db.prepare(sql).bind(*params)  # D1
            res = _to_python(await _resolver_awaitable(stmt.run()))
            return _extrair_changes(res), _extrair_primeira_linha(res)
        cur = self.db.execute(sql, params)  # SQLite local
        if sql.lstrip().upper().startswith("SELECT"):
            linha = cur.fetchone()
            return 0, (dict(linha) if linha is not None else None)
        changes = cur.rowcount
        self.db.commit()
        return changes, None

    async def tentar_registrar(
        self, identidade: str, recurso: str, limite: Limite, agora: int, conta_cota: bool
    ) -> Resultado:
        conta = 1 if conta_cota else 0
        params = (
            identidade, recurso, agora, conta,
            identidade, recurso, agora - limite.intervalo_s,
            conta,
            identidade, recurso, agora - SEGUNDOS_24H, limite.diario,
        )
        changes, _ = await self._executar(_SQL_INSERIR, params)
        if changes > 0:
            return Resultado(permitido=True)

        # Bloqueado: descobre o motivo e quanto falta (apenas para a mensagem).
        _, linha = await self._executar(
            _SQL_ULTIMO_NO_INTERVALO, (identidade, recurso, agora - limite.intervalo_s)
        )
        ultimo = _valor_int(linha)
        if ultimo is not None:
            return Resultado(False, "intervalo", max(1, ultimo + limite.intervalo_s - agora))
        _, linha = await self._executar(
            _SQL_MAIS_ANTIGO_DA_COTA, (identidade, recurso, agora - SEGUNDOS_24H, limite.diario)
        )
        antigo = _valor_int(linha)
        if antigo is not None:
            return Resultado(False, "diario", max(1, antigo + SEGUNDOS_24H - agora))
        return Resultado(False, "intervalo", 1)

    async def limpar_antigos(self, agora: int) -> None:
        await self._executar(_SQL_LIMPAR, (agora - RETENCAO_S,))


def _formatar_espera(segundos: int) -> str:
    if segundos < 90:
        return f"{segundos} s"
    if segundos < 5400:
        return f"{math.ceil(segundos / 60)} min"
    return f"{math.ceil(segundos / 3600)} h"


def _mensagem(recurso: str, resultado: Resultado) -> str:
    espera = _formatar_espera(resultado.retry_after_s)
    alvo = "buscas" if recurso == "busca" else "consultas ao Oráculo"
    if resultado.motivo == "diario":
        return f"Limite diário de {alvo} atingido. Tente novamente em {espera}."
    return f"Muitas requisições em sequência. Aguarde {espera} para tentar novamente."


_ultima_limpeza = 0  # por isolate; os testes redefinem via monkeypatch


class LimitadorTaxa:
    """Fachada usada pelos routers: `await limitador.consumir("busca")`."""

    def __init__(
        self,
        repo: RateLimitRepository,
        identidade: Identidade,
        relogio: Callable[[], float] = time.time,
    ):
        self.repo = repo
        self.identidade = identidade
        self._relogio = relogio

    async def consumir(self, recurso: str, *, conta_cota: bool = True) -> None:
        """Registra a chamada ou levanta 429 (limite) / 503 (falha do D1: bloqueia)."""
        limite = LIMITES[(self.identidade.tipo, recurso)]
        agora = int(self._relogio())
        try:
            resultado = await self.repo.tentar_registrar(
                self.identidade.chave, recurso, limite, agora, conta_cota
            )
        except Exception as exc:
            logger.error("Falha no rate limit (recurso=%s): %s", recurso, exc)
            raise HTTPException(
                status_code=503,
                detail="Serviço temporariamente indisponível. Tente novamente em instantes.",
            ) from exc

        # Log sem dados pessoais: serve para conferir se o login do Access é reconhecido (tipo=email).
        logger.info(
            "rate_limit tipo=%s recurso=%s permitido=%s motivo=%s",
            self.identidade.tipo, recurso, resultado.permitido, resultado.motivo,
        )
        if not resultado.permitido:
            raise HTTPException(
                status_code=429,
                detail=_mensagem(recurso, resultado),
                headers={"Retry-After": str(resultado.retry_after_s)},
            )
        await self._limpeza_oportunista(agora)

    async def _limpeza_oportunista(self, agora: int) -> None:
        global _ultima_limpeza
        if agora - _ultima_limpeza < INTERVALO_LIMPEZA_S:
            return
        _ultima_limpeza = agora
        try:
            await self.repo.limpar_antigos(agora)
        except Exception as exc:
            logger.warning("Falha na limpeza do rate limit: %s", exc)


# --------------------------------------------------------------------------------------
# Identidade (quem está chamando)
# --------------------------------------------------------------------------------------

_verificadores: dict[tuple[str, tuple[str, ...]], VerificadorAccess] = {}


def _ler_config(env: Any, nome: str) -> str:
    valor = get_env_binding(env, nome) or os.environ.get(nome) or ""
    return str(valor).strip()


def _obter_verificador(env: Any) -> Optional[VerificadorAccess]:
    team = _ler_config(env, "ACCESS_TEAM_DOMAIN")
    auds = tuple(a.strip() for a in _ler_config(env, "ACCESS_AUD").split(",") if a.strip())
    if not team or not auds:
        return None  # sem configuração: ninguém é reconhecido como logado (todos por IP)
    chave = (team, auds)
    if chave not in _verificadores:
        _verificadores[chave] = VerificadorAccess(team, list(auds), buscar_json_http)
    return _verificadores[chave]


def _obter_sal(env: Any) -> str:
    sal = _ler_config(env, "RATE_LIMIT_SALT")
    if sal:
        return sal
    if get_env_binding(env, "DB") is not None:  # produção sem sal configurado: não opera
        raise HTTPException(status_code=503, detail="Serviço temporariamente indisponível.")
    return SAL_DEV


def normalizar_ip(bruto: str) -> str:
    """IPv4 inalterado; IPv6 reduzido ao prefixo /64 (um usuário domina um /64 inteiro)."""
    texto = (bruto or "").strip()
    try:
        ip = ipaddress.ip_address(texto)
    except ValueError:
        return texto or "desconhecido"
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)
    return str(ip)


def _ip_do_cliente(request: Request) -> str:
    bruto = request.headers.get("cf-connecting-ip")
    if not bruto and request.client:
        bruto = request.client.host
    return normalizar_ip(bruto or "desconhecido")


def hash_identidade(sal: str, tipo: str, valor: str) -> str:
    digest = hmac.new(sal.encode(), f"{tipo}:{valor}".encode(), hashlib.sha256).hexdigest()
    return f"{tipo}:{digest[:32]}"


async def resolver_identidade(request: Request) -> Identidade:
    env = request.scope.get("env")
    sal = _obter_sal(env)
    token = request.headers.get("cf-access-jwt-assertion") or request.cookies.get("CF_Authorization")
    if token:
        verificador = _obter_verificador(env)
        if verificador is not None:
            email = await verificador.email_verificado(token)
            if email:
                return Identidade("email", hash_identidade(sal, "email", email))
    return Identidade("ip", hash_identidade(sal, "ip", _ip_do_cliente(request)))


def get_rate_limit_repo(request: Request) -> RateLimitRepository:
    env = request.scope.get("env")
    db_binding = get_env_binding(env, "DB")
    if db_binding is not None:
        return RateLimitRepository(db_binding)
    state = getattr(getattr(request, "app", None), "state", None)
    if state is not None:
        repo = getattr(state, "rate_limit_repo", None)
        if repo is None:
            repo = RateLimitRepository()
            setattr(state, "rate_limit_repo", repo)
        return repo
    return RateLimitRepository()


async def get_limitador(
    identidade: Identidade = Depends(resolver_identidade),
    repo: RateLimitRepository = Depends(get_rate_limit_repo),
) -> LimitadorTaxa:
    return LimitadorTaxa(repo, identidade)
