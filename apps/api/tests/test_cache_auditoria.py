import hashlib
import json
import sqlite3
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from mbft_api.main import app
from mbft_api.database import HistoricoRepository, _to_python
from mbft_api.dependencies import get_buscador, get_gerador, get_historico_repo
from mbft_api.gerador.interfaces import ILLMClient
from mbft_api.gerador.orquestrador import OrquestradorGeracao
from mbft_api.gerador.prompts import FRASE_CANONICA_RECUSA
from mbft_api.recuperador.buscador import BuscadorHibrido, ContextoResultado


class SpyLLM(ILLMClient):
    def __init__(self, retorno: str = "Resposta do LLM sobre velocidade."):
        self.retorno = retorno
        self.chamadas = []

    async def gerar_resposta(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str:
        self.chamadas.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return self.retorno


@pytest.fixture
def repo_memoria():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    repo = HistoricoRepository(conn)
    return repo


# ==============================================================================
# 1. Teste: Cache Miss -> Hit
# ==============================================================================

@pytest.mark.asyncio
async def test_cache_miss_depois_hit(repo_memoria):
    mock_buscador = MagicMock(spec=BuscadorHibrido)
    chunks_exemplo = ContextoResultado(
        [
            {
                "id": "doc_velocidade",
                "score": 0.88,
                "metadata": {
                    "codigo": "747-10",
                    "texto_contextualizado": "[Ficha 747-10] Transitar em velocidade superior à máxima em mais de 50%.",
                },
            }
        ],
        tem_match_fts=True,
        max_similaridade_vetorial=0.88,
    )
    mock_buscador.recuperar_contexto = AsyncMock(return_value=chunks_exemplo)

    spy_llm = SpyLLM("A velocidade máxima é regulamentada pela sinalização.")
    orquestrador = OrquestradorGeracao(spy_llm)

    app.dependency_overrides[get_buscador] = lambda: mock_buscador
    app.dependency_overrides[get_gerador] = lambda: orquestrador
    app.dependency_overrides[get_historico_repo] = lambda: repo_memoria

    client = TestClient(app)
    try:
        pergunta_original = "Qual a velocidade máxima permitida?"

        # Primeira chamada: Cache MISS
        resp1 = client.post("/chat/", json={"pergunta": pergunta_original})
        assert resp1.status_code == 200
        assert resp1.json() == {"resposta": "A velocidade máxima é regulamentada pela sinalização."}
        assert resp1.headers.get("x-cache") == "MISS"
        assert resp1.headers.get("x-cache-hit") == "false"
        assert len(spy_llm.chamadas) == 1
        assert mock_buscador.recuperar_contexto.call_count == 1

        # Confirma gravação no banco
        q_hash = hashlib.sha256(pergunta_original.strip().lower().encode("utf-8")).hexdigest()
        reg_banco = await repo_memoria.buscar_cache_por_hash(q_hash)
        assert reg_banco is not None
        assert reg_banco["resposta"] == "A velocidade máxima é regulamentada pela sinalização."

        # Segunda chamada: Mesma pergunta (com variação de maiúsculas/espaços) -> Cache HIT
        pergunta_variada = "   QUAL A VELOCIDADE MÁXIMA PERMITIDA?   "
        resp2 = client.post("/chat/", json={"pergunta": pergunta_variada})
        assert resp2.status_code == 200
        assert resp2.json() == {"resposta": "A velocidade máxima é regulamentada pela sinalização."}
        assert resp2.headers.get("x-cache") == "HIT"
        assert resp2.headers.get("x-cache-hit") == "true"

        # LLM e Buscador NÃO podem ter sido chamados novamente!
        assert len(spy_llm.chamadas) == 1
        assert mock_buscador.recuperar_contexto.call_count == 1
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 2. Teste: Auditoria de Dados Completa
# ==============================================================================

@pytest.mark.asyncio
async def test_auditoria_de_dados(repo_memoria):
    mock_buscador = MagicMock(spec=BuscadorHibrido)
    chunks = ContextoResultado(
        [
            {
                "id": "518-51_EMENTA",
                "score": 0.92,
                "metadata": {
                    "codigo": "518-51",
                    "artigo": "167",
                    "secao": "EMENTA",
                    "texto_contextualizado": "[Infração 518-51] Deixar de usar o cinto de segurança.",
                },
            }
        ],
        tem_match_fts=True,
        max_similaridade_vetorial=0.92,
    )
    mock_buscador.recuperar_contexto = AsyncMock(return_value=chunks)

    spy_llm = SpyLLM("Autuar no código 518-51 por falta de cinto.")
    orquestrador = OrquestradorGeracao(spy_llm)

    app.dependency_overrides[get_buscador] = lambda: mock_buscador
    app.dependency_overrides[get_gerador] = lambda: orquestrador
    app.dependency_overrides[get_historico_repo] = lambda: repo_memoria

    client = TestClient(app)
    try:
        pergunta = "Quando autuar a falta de cinto?"
        resp = client.post("/chat/", json={"pergunta": pergunta})
        assert resp.status_code == 200

        q_hash = hashlib.sha256(pergunta.strip().lower().encode("utf-8")).hexdigest()
        registro = await repo_memoria.buscar_cache_por_hash(q_hash)
        assert registro is not None

        # Validação do ID como UUID válido
        id_uuid = uuid.UUID(registro["id"])
        assert str(id_uuid) == registro["id"]

        assert registro["query_hash"] == q_hash
        assert registro["pergunta"] == pergunta
        assert registro["resposta"] == "Autuar no código 518-51 por falta de cinto."
        assert registro["from_cache"] is False
        assert registro["created_at"] is not None

        # Validação do JSON serializado dos chunks recuperados
        chunks_salvos = json.loads(registro["busca_resultados_json"])
        assert isinstance(chunks_salvos, list)
        assert len(chunks_salvos) == 1
        assert chunks_salvos[0]["id"] == "518-51_EMENTA"
        assert chunks_salvos[0]["metadata"]["codigo"] == "518-51"

        # Validação do prompt montado
        prompt = registro["prompt_completo"]
        assert "Manual Brasileiro de Fiscalização de Trânsito" in prompt
        assert "[Infração 518-51] Deixar de usar o cinto de segurança." in prompt
        assert f"<pergunta_usuario>{pergunta}</pergunta_usuario>" in prompt
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 3. Teste: Persistência de Short-Circuit
# ==============================================================================

@pytest.mark.asyncio
async def test_persistencia_short_circuit(repo_memoria):
    mock_buscador = MagicMock(spec=BuscadorHibrido)
    # Simula busca fora do escopo do MBFT (sem match FTS e similaridade vetorial fraca)
    chunks_irrelevantes = ContextoResultado(
        [{"id": "doc_aleatorio", "score": 0.22, "metadata": {"texto_contextualizado": "outra coisa"}}],
        tem_match_fts=False,
        max_similaridade_vetorial=0.22,
    )
    mock_buscador.recuperar_contexto = AsyncMock(return_value=chunks_irrelevantes)

    spy_llm = SpyLLM("Não deveria ser gerada.")
    orquestrador = OrquestradorGeracao(spy_llm)

    app.dependency_overrides[get_buscador] = lambda: mock_buscador
    app.dependency_overrides[get_gerador] = lambda: orquestrador
    app.dependency_overrides[get_historico_repo] = lambda: repo_memoria

    client = TestClient(app)
    try:
        pergunta = "Como assar pão de queijo congelado?"
        q_hash = hashlib.sha256(pergunta.strip().lower().encode("utf-8")).hexdigest()

        # 1. Primeira chamada: cai no short-circuit
        resp1 = client.post("/chat/", json={"pergunta": pergunta})
        assert resp1.status_code == 200
        assert resp1.json() == {"resposta": FRASE_CANONICA_RECUSA}
        assert resp1.headers.get("x-cache") == "MISS"
        assert resp1.headers.get("x-cache-hit") == "false"
        assert len(spy_llm.chamadas) == 0

        # Verifica que o rastro de auditoria foi persistido
        reg = await repo_memoria.buscar_cache_por_hash(q_hash)
        assert reg is not None
        assert reg["query_hash"] == q_hash
        assert reg["pergunta"] == pergunta
        assert reg["resposta"] == FRASE_CANONICA_RECUSA
        assert reg["busca_resultados_json"] == "[]"
        assert reg["prompt_completo"] == ""
        assert reg["from_cache"] is False

        # 2. Segunda chamada com a mesma pergunta: atinge o Cache Hit da recusa
        resp2 = client.post("/chat/", json={"pergunta": pergunta})
        assert resp2.status_code == 200
        assert resp2.json() == {"resposta": FRASE_CANONICA_RECUSA}
        assert resp2.headers.get("x-cache") == "HIT"
        assert resp2.headers.get("x-cache-hit") == "true"

        # Nem buscador nem LLM foram chamados na segunda vez!
        assert mock_buscador.recuperar_contexto.call_count == 1
        assert len(spy_llm.chamadas) == 0
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 4. Testes Diretos de Adaptador: SQLite e D1
# ==============================================================================

@pytest.mark.asyncio
async def test_repositorio_retorna_registro_mais_recente_para_mesmo_hash():
    repo = HistoricoRepository()
    q_hash = "hash_teste_duplicado"

    # Salva primeira versão
    await repo.salvar_consulta(
        id="id-1",
        query_hash=q_hash,
        pergunta="Pergunta teste",
        busca_resultados_json="[]",
        prompt_completo="Prompt 1",
        resposta="Resposta 1",
    )

    # Salva versão mais recente
    await repo.salvar_consulta(
        id="id-2",
        query_hash=q_hash,
        pergunta="Pergunta teste",
        busca_resultados_json="[]",
        prompt_completo="Prompt 2",
        resposta="Resposta Mais Recente",
    )

    res = await repo.buscar_cache_por_hash(q_hash)
    assert res is not None
    assert res["id"] == "id-2"
    assert res["resposta"] == "Resposta Mais Recente"


@pytest.mark.asyncio
async def test_repositorio_consultas_inexistentes_ou_vazias_retornam_none():
    repo = HistoricoRepository()
    assert await repo.buscar_cache_por_hash("hash_nao_existente") is None
    assert await repo.buscar_cache_por_hash("") is None
    assert await repo.buscar_cache_por_hash("   ") is None


@pytest.mark.asyncio
async def test_repositorio_adaptador_cloudflare_d1():
    class FakeD1Stmt:
        def __init__(self, storage: list, sql: str, params: tuple = ()):
            self.storage = storage
            self.sql = sql
            self.params = params

        def bind(self, *params):
            return FakeD1Stmt(self.storage, self.sql, params)

        async def run(self):
            # Simula INSERT
            self.storage.append(self.params)
            return {"success": True}

        async def first(self):
            # Simula SELECT LIMIT 1
            if not self.storage:
                return None
            p = self.storage[-1]
            return {
                "id": p[0],
                "query_hash": p[1],
                "pergunta": p[2],
                "busca_resultados_json": p[3],
                "prompt_completo": p[4],
                "resposta": p[5],
                "from_cache": p[6],
                "created_at": "2026-10-11 12:00:00",
            }

    class FakeD1DB:
        def __init__(self):
            self.storage = []

        def prepare(self, sql: str):
            return FakeD1Stmt(self.storage, sql)

    fake_d1 = FakeD1DB()
    repo_d1 = HistoricoRepository(fake_d1)

    # 1. Salvar
    await repo_d1.salvar_consulta(
        id="d1-uuid",
        query_hash="hash_d1",
        pergunta="Pergunta D1",
        busca_resultados_json="[]",
        prompt_completo="Prompt D1",
        resposta="Resposta D1",
        from_cache=False,
    )
    assert len(fake_d1.storage) == 1

    # 2. Buscar
    rec = await repo_d1.buscar_cache_por_hash("hash_d1")
    assert rec is not None
    assert rec["id"] == "d1-uuid"
    assert rec["resposta"] == "Resposta D1"
    assert rec["from_cache"] is False


@pytest.mark.asyncio
async def test_repositorio_salvar_com_from_cache_true():
    repo = HistoricoRepository()
    await repo.salvar_consulta(
        id="cache-hit-id",
        query_hash="hash_hit",
        pergunta="Pergunta Hit",
        busca_resultados_json="[]",
        prompt_completo="Prompt",
        resposta="Resposta Cacheada",
        from_cache=True,
    )
    rec = await repo.buscar_cache_por_hash("hash_hit")
    assert rec is not None
    assert rec["from_cache"] is True


@pytest.mark.asyncio
async def test_repositorio_adaptador_d1_fallback_all():
    class FakeD1StmtOnlyAll:
        def __init__(self, sql: str, params: tuple = ()):
            self.sql = sql
            self.params = params

        def bind(self, *params):
            return FakeD1StmtOnlyAll(self.sql, params)

        async def all(self):
            if "INSERT" in self.sql:
                return {"success": True}
            return {
                "results": [
                    {
                        "id": "all-id",
                        "query_hash": "hash_all",
                        "pergunta": "Pergunta All",
                        "busca_resultados_json": "[]",
                        "prompt_completo": "Prompt",
                        "resposta": "Resposta All",
                        "from_cache": 0,
                        "created_at": "2026-10-11 12:00:00",
                    }
                ]
            }

    class FakeD1DBOnlyAll:
        def prepare(self, sql: str):
            return FakeD1StmtOnlyAll(sql)

    repo = HistoricoRepository(FakeD1DBOnlyAll())
    await repo.salvar_consulta(
        id="all-id",
        query_hash="hash_all",
        pergunta="Pergunta All",
        busca_resultados_json="[]",
        prompt_completo="Prompt",
        resposta="Resposta All",
        from_cache=False,
    )
    rec = await repo.buscar_cache_por_hash("hash_all")
    assert rec is not None
    assert rec["id"] == "all-id"
    assert rec["resposta"] == "Resposta All"


@pytest.mark.asyncio
async def test_chat_resiliencia_a_falha_de_banco_nao_causa_500():
    mock_buscador = MagicMock(spec=BuscadorHibrido)
    chunks = ContextoResultado(
        [
            {
                "id": "doc_1",
                "score": 0.9,
                "metadata": {
                    "codigo": "500-00",
                    "texto_contextualizado": "Regra de teste.",
                },
            }
        ],
        tem_match_fts=True,
        max_similaridade_vetorial=0.9,
    )
    mock_buscador.recuperar_contexto = AsyncMock(return_value=chunks)
    spy_llm = SpyLLM("Resposta normal apesar de erro no banco.")
    orquestrador = OrquestradorGeracao(spy_llm)

    class BrokenRepo:
        async def buscar_cache_por_hash(self, query_hash: str):
            raise RuntimeError("D1 indisponível para leitura")

        async def salvar_consulta(self, **kwargs):
            raise RuntimeError("D1 indisponível para escrita")

    app.dependency_overrides[get_buscador] = lambda: mock_buscador
    app.dependency_overrides[get_gerador] = lambda: orquestrador
    app.dependency_overrides[get_historico_repo] = lambda: BrokenRepo()

    client = TestClient(app)
    try:
        resp = client.post("/chat/", json={"pergunta": "Pergunta com banco quebrado?"})
        assert resp.status_code == 200
        assert resp.json() == {"resposta": "Resposta normal apesar de erro no banco."}
        assert resp.headers.get("x-cache") == "MISS"
    finally:
        app.dependency_overrides.clear()
