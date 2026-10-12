import pytest
from typing import List, Dict, Any
from mbft_api.recuperador.buscador import BuscadorHibrido

class MockEmbedder:
    async def embed_query(self, query: str) -> List[float]:
        return [0.1, 0.2, 0.3]

class MockVectorDB:
    def __init__(self, resultados: List[Dict[str, Any]]):
        self.resultados = resultados
        
    async def buscar_similares(self, vetor: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        return self.resultados[:limit]

class MockRelationalDB:
    def __init__(self, resultados: List[Dict[str, Any]]):
        self.resultados = resultados
        
    async def buscar_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.resultados[:limit]

@pytest.mark.asyncio
async def test_reciprocal_rank_fusion_prioriza_intersecao():
    # Arrange: Simula resultados do banco vetorial e de texto exato
    dense_docs = [
        {"id": "doc_A", "metadata": {"codigo": "123"}}, # rank 1
        {"id": "doc_B", "metadata": {"codigo": "456"}}, # rank 2
        {"id": "doc_C", "metadata": {"codigo": "789"}}, # rank 3
    ]
    
    sparse_docs = [
        {"id": "doc_C", "metadata": {"codigo": "789"}}, # rank 1
        {"id": "doc_D", "metadata": {"codigo": "000"}}, # rank 2
        {"id": "doc_A", "metadata": {"codigo": "123"}}, # rank 3
    ]
    
    vector_db = MockVectorDB(dense_docs)
    relational_db = MockRelationalDB(sparse_docs)
    embedder = MockEmbedder()
    
    buscador = BuscadorHibrido(vector_db, relational_db, embedder)
    
    # Act
    resultados = await buscador.recuperar_contexto("qualquer_pergunta", limit=5)
    
    # Assert
    assert len(resultados) == 4
    
    ids = [r["id"] for r in resultados]
    
    # doc_A e doc_C aparecem nas duas listas, logo o RRF deles será maior
    # doc_C: rank 3 (denso) e rank 1 (esparso)
    # doc_A: rank 1 (denso) e rank 3 (esparso)
    # Como a matemática RRF é 1/(k+rank), eles empatam e devem dominar o topo.
    assert set(ids[:2]) == {"doc_A", "doc_C"}
    
    # doc_B e doc_D aparecem apenas em uma das listas, com rank 2
    assert set(ids[2:]) == {"doc_B", "doc_D"}
    
    for r in resultados:
        assert "rrf_score" in r
        assert r["rrf_score"] > 0.0

@pytest.mark.asyncio
async def test_reciprocal_rank_fusion_limite():
    # Arrange: Apenas para garantir que o limit é respeitado
    dense_docs = [{"id": f"doc_dense_{i}"} for i in range(10)]
    sparse_docs = [{"id": f"doc_sparse_{i}"} for i in range(10)]
    
    buscador = BuscadorHibrido(MockVectorDB(dense_docs), MockRelationalDB(sparse_docs), MockEmbedder())
    
    # Act
    resultados = await buscador.recuperar_contexto("limite", limit=3)
    
    # Assert
    assert len(resultados) == 3

@pytest.mark.asyncio
async def test_diversificacao_por_ficha_evita_monopolio_e_faz_backfill():
    dense_docs = [
        {"id": "752-81_1", "metadata": {"codigo": "752-81"}},
        {"id": "752-81_2", "metadata": {"codigo": "752-81"}},
        {"id": "752-81_3", "metadata": {"codigo": "752-81"}},
        {"id": "752-82_1", "metadata": {"codigo": "752-82"}},
        {"id": "751-01_1", "metadata": {"codigo": "751-01"}},
    ]
    sparse_docs = [
        {"id": "752-81_1", "metadata": {"codigo": "752-81"}},
        {"id": "752-81_2", "metadata": {"codigo": "752-81"}},
        {"id": "752-82_1", "metadata": {"codigo": "752-82"}},
        {"id": "751-01_1", "metadata": {"codigo": "751-01"}},
    ]

    buscador = BuscadorHibrido(MockVectorDB(dense_docs), MockRelationalDB(sparse_docs), MockEmbedder())

    # Com limit=3, deve trazer 1 chunk de cada código único (752-81, 752-82, 751-01)
    top3 = await buscador.recuperar_contexto("art 95", limit=3)
    assert [r["metadata"]["codigo"] for r in top3] == ["752-81", "752-82", "751-01"]
    assert [r["id"] for r in top3] == ["752-81_1", "752-82_1", "751-01_1"]

    # Com limit=5, após esgotar os 3 códigos únicos, preenche (backfill) com os chunks restantes de maior RRF
    top5 = await buscador.recuperar_contexto("art 95", limit=5)
    assert len(top5) == 5
    assert [r["id"] for r in top5] == ["752-81_1", "752-82_1", "751-01_1", "752-81_2", "752-81_3"]

def test_formatar_token_fts_preserva_exatos_curtos_numericos_e_romanos():
    from mbft_api.recuperador.local_adapters import LocalSqliteDB

    assert LocalSqliteDB._formatar_token_fts("") == ""
    assert LocalSqliteDB._formatar_token_fts("Art") == "Art"
    assert LocalSqliteDB._formatar_token_fts("162") == "162"
    assert LocalSqliteDB._formatar_token_fts("I") == "I"
    assert LocalSqliteDB._formatar_token_fts("II") == "II"
    assert LocalSqliteDB._formatar_token_fts("VIII") == "VIII"
    assert LocalSqliteDB._formatar_token_fts("XVIII") == "XVIII"
    assert LocalSqliteDB._formatar_token_fts("XLII") == "XLII"
    assert LocalSqliteDB._formatar_token_fts("14599") == "14599"
    assert LocalSqliteDB._formatar_token_fts("dirigir") == "dirigir*"
    assert LocalSqliteDB._formatar_token_fts("álcool") == "álcool*"
    assert LocalSqliteDB._formatar_token_fts("civil") == "civil*"
    assert LocalSqliteDB._formatar_token_fts("NOT") == '"NOT"'


@pytest.mark.asyncio
async def test_local_sqlite_db_normaliza_grau_para_ordinal_e_ignora_underscores(tmp_path):
    import json
    from mbft_api.recuperador.local_adapters import LocalSqliteDB

    jsonl = tmp_path / "test_emb.jsonl"
    chunk = {
        "id": "712-92_EMENTA",
        "values": [0.1, 0.2],
        "metadata": {
            "codigo": "712-92",
            "artigo": "244",
            "secao": "EMENTA",
            "texto_contextualizado": "[Infração 712-92 | Art. 244 | Amparo: Art. 244, § 2º.] Conduzir ciclomotor.",
        },
    }
    jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")

    db = LocalSqliteDB(jsonl)
    res_grau = await db.buscar_fts("Art. 244, § 2°", limit=5)
    assert [r["id"] for r in res_grau] == ["712-92_EMENTA"]

    res_underscore = await db.buscar_fts("____ Art_244", limit=5)
    assert [r["id"] for r in res_underscore] == ["712-92_EMENTA"]


class _FakeJsProxy:
    """Simula um objeto JsProxy retornado pelo FFI do Pyodide (com método .to_py())."""

    def __init__(self, payload: Any):
        self._payload = payload

    def to_py(self) -> Any:
        return self._payload


class _SqliteBackedD1PreparedStatement:
    """Emula D1PreparedStatement sobre uma conexão sqlite3 em memória."""

    def __init__(self, conn, sql: str, params: tuple = ()):
        self._conn = conn
        self._sql = sql
        self._params = params

    def bind(self, *params):
        return _SqliteBackedD1PreparedStatement(self._conn, self._sql, params)

    async def all(self):
        cur = self._conn.cursor()
        cur.execute(self._sql, self._params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return _FakeJsProxy({"success": True, "results": rows})

    async def first(self):
        cur = self._conn.cursor()
        cur.execute(self._sql, self._params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description] if cur.description else []
        return _FakeJsProxy(dict(zip(cols, row)))

    async def run(self):
        cur = self._conn.cursor()
        cur.execute(self._sql, self._params)
        self._conn.commit()
        return _FakeJsProxy({"success": True, "results": []})


class _SqliteBackedD1Database:
    """Emula o binding env.DB (D1Database) sobre sqlite3 em memória."""

    def __init__(self, conn):
        self.conn = conn
        self.prepared_queries: list[str] = []

    def prepare(self, sql: str):
        self.prepared_queries.append(sql)
        return _SqliteBackedD1PreparedStatement(self.conn, sql)


@pytest.mark.asyncio
async def test_schema_sql_e_d1_adapters_compartilham_contrato_fts5():
    import sqlite3
    from pathlib import Path
    from mbft_api.recuperador.cloudflare_adapters import D1RelationalDB
    from mbft_api.recuperador.local_adapters import LocalSqliteDB

    # Garante que o formatador FTS5 é compartilhado entre LocalSqliteDB e D1RelationalDB
    assert D1RelationalDB._formatar_token_fts is LocalSqliteDB._formatar_token_fts
    assert D1RelationalDB._formatar_query_fts("Art. 244, § 2° ___ NOT") == 'Art 244 2º "NOT"'

    schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    assert schema_path.is_file(), "Arquivo apps/api/schema.sql deve existir."

    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    conn.execute(
        """
        INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "712-92_EMENTA",
            "712-92",
            "244",
            "EMENTA",
            "[Infração 712-92 | Art. 244 | Amparo: Art. 244, § 2º.] Conduzir ciclomotor.",
        ),
    )
    conn.commit()

    fake_d1 = _SqliteBackedD1Database(conn)

    # Testa D1RelationalDB sobre a tabela virtual fts_chunks criada pelo schema.sql
    d1_rel = D1RelationalDB(fake_d1)
    res = await d1_rel.buscar_fts("Art. 244, § 2°", limit=5)
    assert len(res) == 1
    assert res[0]["id"] == "712-92_EMENTA"
    assert res[0]["metadata"]["codigo"] == "712-92"
    assert res[0]["score"] >= 0.0

    # 3. Edge cases: query vazia, apenas pontuação/underscores ou limit <= 0 não disparam SQL
    q_count = len(fake_d1.prepared_queries)
    assert await d1_rel.buscar_fts("", limit=5) == []
    assert await d1_rel.buscar_fts("___ ??? ...", limit=5) == []
    assert await d1_rel.buscar_fts("Art 244", limit=0) == []
    assert len(fake_d1.prepared_queries) == q_count


@pytest.mark.asyncio
async def test_vectorize_db_respeita_limite_topk_50_e_converte_jsproxy():
    from mbft_api.recuperador.cloudflare_adapters import VectorizeDB

    chamadas: list[tuple] = []

    class FakeVectorizeIndex:
        async def query(self, vetor, options):
            chamadas.append((vetor, options))
            return _FakeJsProxy(
                {
                    "matches": [
                        {
                            "id": "518-51_QUANDO_AUTUAR",
                            "score": 0.91,
                            "metadata": {
                                "codigo": "518-51",
                                "artigo": "167",
                                "texto_contextualizado": "Deixar o condutor de usar o cinto.",
                            },
                        }
                    ]
                }
            )

    vec_db = VectorizeDB(FakeVectorizeIndex())

    # Quando BuscadorHibrido pede pool_size=60, VectorizeDB deve limitar topK a 50 (limite do Vectorize V2 com returnMetadata="all")
    res = await vec_db.buscar_similares([0.1, 0.2, 0.3], limit=60)
    assert len(res) == 1
    assert res[0]["id"] == "518-51_QUANDO_AUTUAR"
    assert res[0]["score"] == pytest.approx(0.91)
    assert chamadas[0][1] == {"topK": 50, "returnMetadata": "all"}

    # Edge cases: vetor vazio ou limit <= 0
    assert await vec_db.buscar_similares([], limit=5) == []
    assert await vec_db.buscar_similares([0.1], limit=0) == []


@pytest.mark.asyncio
async def test_workers_ai_embedder_e_workers_ai_llm_client_com_limpeza_think():
    from mbft_api.gerador.cloudflare_adapters import (
        DEFAULT_CF_LLM_MODEL,
        WorkersAILLMClient,
        limpar_bloco_think,
    )
    from mbft_api.recuperador.cloudflare_adapters import (
        DEFAULT_CF_EMBEDDING_MODEL,
        WorkersAIEmbedder,
    )

    chamadas_ai: list[tuple[str, dict]] = []

    class FakeWorkersAI:
        def __init__(self, llm_output):
            self.llm_output = llm_output

        async def run(self, model: str, payload: dict):
            chamadas_ai.append((model, payload))
            if model == DEFAULT_CF_EMBEDDING_MODEL:
                return _FakeJsProxy({"shape": [1, 3], "data": [[0.25, 0.5, 0.75]]})
            return _FakeJsProxy(self.llm_output)

    fake_ai = FakeWorkersAI(
        {
            "response": "<think>\nAnalisando ficha 518-51 e Art. 167 do CTB...\n</think>\n\nA infração 518-51 é grave e prevê retenção do veículo."
        }
    )

    embedder = WorkersAIEmbedder(fake_ai)
    vetor = await embedder.embed_query("cinto de segurança")
    assert vetor == [0.25, 0.5, 0.75]
    assert await embedder.embed_query("   ") == []
    assert chamadas_ai[0] == (DEFAULT_CF_EMBEDDING_MODEL, {"text": ["cinto de segurança"]})

    llm = WorkersAILLMClient(fake_ai)
    assert llm.model == DEFAULT_CF_LLM_MODEL
    resposta = await llm.gerar_resposta("SYS", "USER", temperature=0.0, max_tokens=512)
    assert resposta == "A infração 518-51 é grave e prevê retenção do veículo."
    assert chamadas_ai[1][0] == DEFAULT_CF_LLM_MODEL
    assert chamadas_ai[1][1]["max_tokens"] == 512

    # Testa formato OpenAI-compatible choices + casos de borda de <think>
    fake_ai_choices = FakeWorkersAI(
        {
            "choices": [
                {
                    "message": {
                        "content": "Raciocínio sem tag inicial\n</think>\nResposta limpa final.<think>truncado no fim"
                    }
                }
            ]
        }
    )
    llm_deepseek = WorkersAILLMClient(
        fake_ai_choices, model="@cf/deepseek-ai/deepseek-r1-distill-qwen-32b"
    )
    assert (
        await llm_deepseek.gerar_resposta("SYS", "USER")
        == "Resposta limpa final."
    )
    assert limpar_bloco_think("<THINK>bloco 1</THINK> Meio <think>bloco 2</think> Fim") == "Meio  Fim"


@pytest.mark.asyncio
async def test_injecao_dependencia_por_requisicao_workers_fallback_local_e_override_llm(monkeypatch):
    import sqlite3
    from pathlib import Path
    from types import SimpleNamespace
    from fastapi import HTTPException
    from mbft_api.dependencies import get_buscador, get_gerador
    from mbft_api.gerador.orquestrador import OrquestradorGeracao
    from mbft_api.routers.busca import buscar
    from mbft_api.routers.chat import PerguntaPayload, fazer_pergunta

    schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado) VALUES (?, ?, ?, ?, ?)",
        ("518-51_EMENTA", "518-51", "167", "EMENTA", "[Infração 518-51] Sem cinto."),
    )
    conn.commit()

    fake_d1 = _SqliteBackedD1Database(conn)

    class FakeVectorize:
        async def query(self, vetor, options):
            return {
                "matches": [
                    {
                        "id": "518-51_EMENTA",
                        "score": 0.95,
                        "metadata": {
                            "codigo": "518-51",
                            "artigo": "167",
                            "texto_contextualizado": "[Infração 518-51] Sem cinto.",
                        },
                    }
                ]
            }

    modelos_chamados: list[str] = []

    class FakeAI:
        async def run(self, model: str, payload: dict):
            modelos_chamados.append(model)
            if "bge-m3" in model:
                return {"data": [[0.1, 0.2, 0.3]]}
            return {"response": "<think>pensando</think>Resposta via Workers AI."}

    class FakeLocalLLM:
        async def gerar_resposta(self, system_prompt, user_prompt, temperature=0.0, max_tokens=None):
            return "Resposta via Gemini Local."

    buscador_local_mock = BuscadorHibrido(
        MockVectorDB([{"id": "501-00_1", "metadata": {"codigo": "501-00", "texto_contextualizado": "Sem CNH"}}]),
        MockRelationalDB([]),
        MockEmbedder(),
    )
    gerador_local_mock = OrquestradorGeracao(FakeLocalLLM())

    fake_app = SimpleNamespace(
        state=SimpleNamespace(buscador=buscador_local_mock, gerador=gerador_local_mock)
    )

    # 1. Modo Workers (bindings em request.scope["env"] como objeto com atributos, simulando self.env do Pyodide)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CF_LLM_MODEL", raising=False)
    env_workers = SimpleNamespace(
        DB=fake_d1,
        VECTORIZE=FakeVectorize(),
        AI=FakeAI(),
        CF_LLM_MODEL="@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
    )
    req_workers = SimpleNamespace(scope={"env": env_workers}, app=fake_app)

    buscador_w = get_buscador(req_workers)
    gerador_w = get_gerador(req_workers)

    res_busca_w = await buscar(q="cinto", limit=5, buscador=buscador_w)
    assert res_busca_w["resultados"][0]["codigo"] == "518-51"
    assert res_busca_w["resultados"][0]["url"] == "/fichas/518-51.html"

    res_chat_w = await fazer_pergunta(
        payload=PerguntaPayload(pergunta="Qual a penalidade para falta de cinto?"),
        buscador=buscador_w,
        gerador=gerador_w,
    )
    assert res_chat_w == {"resposta": "Resposta via Workers AI."}
    assert "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b" in modelos_chamados

    # 2. Override explícito LLM_PROVIDER=gemini mesmo com binding AI presente
    env_override_gemini = SimpleNamespace(
        DB=fake_d1,
        VECTORIZE=FakeVectorize(),
        AI=FakeAI(),
        LLM_PROVIDER="gemini",
    )
    req_override = SimpleNamespace(scope={"env": env_override_gemini}, app=fake_app)
    gerador_override = get_gerador(req_override)
    assert gerador_override is gerador_local_mock

    # 3. Modo Local (sem bindings em request.scope["env"] -> fallback para app.state)
    req_local = SimpleNamespace(scope={}, app=fake_app)
    assert get_buscador(req_local) is buscador_local_mock
    assert get_gerador(req_local) is gerador_local_mock

    # 4. Provedor inválido em LLM_PROVIDER -> HTTP 503
    req_invalido = SimpleNamespace(
        scope={"env": {"LLM_PROVIDER": "provedor_inexistente"}}, app=fake_app
    )
    with pytest.raises(HTTPException) as exc_info:
        get_gerador(req_invalido)
    assert exc_info.value.status_code == 503

    # 5. Sem bindings e sem app.state -> HTTP 503
    empty_app = SimpleNamespace(state=SimpleNamespace(buscador=None, gerador=None))
    req_empty = SimpleNamespace(scope={}, app=empty_app)
    with pytest.raises(HTTPException) as exc_b:
        get_buscador(req_empty)
    assert exc_b.value.status_code == 503
    with pytest.raises(HTTPException) as exc_g:
        get_gerador(req_empty)
    assert exc_g.value.status_code == 503


@pytest.mark.asyncio
async def test_workers_ai_embedder_resiliencia_memoryview_jsnull_e_excecao_fallback_fts5():
    from array import array
    import sqlite3
    from pathlib import Path
    from mbft_api.recuperador.cloudflare_adapters import D1RelationalDB, VectorizeDB, WorkersAIEmbedder

    class JsNull:
        pass

    # 1. Float32Array do Pyodide (.to_py() -> memoryview) deve ser convertido sem TypeError
    class FakeAIMemoryView:
        async def run(self, model: str, payload: dict):
            mv = memoryview(array("f", [0.25, 0.5, 0.75]))
            return _FakeJsProxy({"data": [mv]})

    emb_mv = WorkersAIEmbedder(FakeAIMemoryView())
    vec_mv = await emb_mv.embed_query("teste memoryview")
    assert len(vec_mv) == 3
    assert vec_mv[0] == pytest.approx(0.25)
    assert vec_mv[1] == pytest.approx(0.5)
    assert vec_mv[2] == pytest.approx(0.75)

    # 2. Payloads inesperados (None, JsNull, dict vazio, data=[[]]) retornam []
    for bad_payload in (None, JsNull(), {}, {"data": None}, {"data": []}, {"data": [[]]}, {"data": [JsNull()]}):
        class FakeAIBad:
            async def run(self, model: str, payload: dict):
                return _FakeJsProxy(bad_payload)

        assert await WorkersAIEmbedder(FakeAIBad()).embed_query("consulta") == []

    # 3. Exceção em env.AI.run no embedder degrada graciosamente para [] e permite fallback FTS5 no D1
    class FakeAIFailingEmbedder:
        async def run(self, model: str, payload: dict):
            raise RuntimeError("Workers AI indisponível temporariamente")

    schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado) VALUES (?, ?, ?, ?, ?)",
        ("518-51_EMENTA", "518-51", "167", "EMENTA", "[Infração 518-51] Sem cinto de segurança."),
    )
    conn.commit()

    class FakeVectorizeShouldNotBeCalled:
        async def query(self, vetor, options):
            raise AssertionError("Vectorize.query não deve ser chamado quando vetor é vazio")

    buscador = BuscadorHibrido(
        vector_db=VectorizeDB(FakeVectorizeShouldNotBeCalled()),
        relational_db=D1RelationalDB(_SqliteBackedD1Database(conn)),
        ai_client=WorkersAIEmbedder(FakeAIFailingEmbedder()),
    )
    res_fallback = await buscador.recuperar_contexto("cinto segurança", limit=5)
    assert len(res_fallback) == 1
    assert res_fallback[0]["id"] == "518-51_EMENTA"


@pytest.mark.asyncio
async def test_fluxo_asgi_completo_busca_chat_e_cors():
    import sqlite3
    from pathlib import Path
    from types import SimpleNamespace
    import httpx
    from mbft_api.main import app

    schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado) VALUES (?, ?, ?, ?, ?)",
        ("518-51_EMENTA", "518-51", "167", "EMENTA", "[Infração 518-51] Deixar de usar cinto."),
    )
    conn.commit()

    fake_d1 = _SqliteBackedD1Database(conn)

    class FakeVectorize:
        async def query(self, vetor, options):
            return _FakeJsProxy(
                {
                    "matches": [
                        {
                            "id": "518-51_EMENTA",
                            "score": 0.93,
                            "metadata": {
                                "codigo": "518-51",
                                "artigo": "167",
                                "secao": "EMENTA",
                                "texto_contextualizado": "[Infração 518-51] Deixar de usar cinto.",
                            },
                        }
                    ]
                }
            )

    class FakeAI:
        async def run(self, model: str, payload: dict):
            if "bge-m3" in model:
                return _FakeJsProxy({"data": [[0.1, 0.2, 0.3]]})
            return _FakeJsProxy({"response": "<think>raciocínio</think>Autuar no código 518-51."})

    env_state = {
        "DB": fake_d1,
        "VECTORIZE": FakeVectorize(),
        "AI": FakeAI(),
        "CF_LLM_MODEL": "@cf/meta/llama-3.1-8b-instruct-fp8-fast",
    }

    class EnvAsgiWrapper:
        def __init__(self, inner_app):
            self.inner_app = inner_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                scope = dict(scope)
                scope["env"] = SimpleNamespace(**env_state)
            await self.inner_app(scope, receive, send)

    transport = httpx.ASGITransport(app=EnvAsgiWrapper(app))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Se LLM_PROVIDER estiver inválido, rota /chat/ deve retornar 503
        env_state["LLM_PROVIDER"] = "provedor_invalido"
        resp_503 = await client.post(
            "/chat/",
            json={"pergunta": "Quando autuar falta de cinto de segurança?"},
        )
        assert resp_503.status_code == 503

        # 2. Corrige LLM_PROVIDER e envia pergunta direta para /chat/ -> deve funcionar (200)
        env_state["LLM_PROVIDER"] = "workers_ai"
        resp_ok = await client.post(
            "/chat/",
            json={"pergunta": "Quando autuar falta de cinto de segurança?"},
        )
        assert resp_ok.status_code == 200
        assert resp_ok.json() == {"resposta": "Autuar no código 518-51."}

        # 6. Rota GET /busca/ via ASGI com bindings Cloudflare
        resp_busca = await client.get("/busca/", params={"q": "cinto", "limit": 3})
        assert resp_busca.status_code == 200
        dados_busca = resp_busca.json()
        assert dados_busca["resultados"][0]["codigo"] == "518-51"
        assert dados_busca["resultados"][0]["url"] == "/fichas/518-51.html"

        # 7. CORS_ORIGINS dinâmico via scope["env"] e bloqueio de curinga "*"
        env_state["CORS_ORIGINS"] = "https://mbft-site.pages.dev/, *"
        resp_cors_ok = await client.get("/health/", headers={"Origin": "https://mbft-site.pages.dev"})
        assert resp_cors_ok.headers.get("access-control-allow-origin") == "https://mbft-site.pages.dev"
        resp_cors_bloqueado = await client.get("/health/", headers={"Origin": "https://site-malicioso.evil"})
        assert resp_cors_bloqueado.headers.get("access-control-allow-origin") is None

        # 8. Rota GET /busca/ mapeia chunks da Parte Geral (PG_*) para /parte-geral/<slug>.html
        conn.execute(
            "INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado) VALUES (?, ?, ?, ?, ?)",
            ("PG_8_1", "PG_8_1", "270", "PARTE_GERAL", "[Parte Geral do MBFT - 8.1. Retenção do Veículo] Imobilização no local."),
        )
        conn.commit()
        resp_busca_pg = await client.get("/busca/", params={"q": "Imobilização", "limit": 5})
        assert resp_busca_pg.status_code == 200
        urls_pg = [r["url"] for r in resp_busca_pg.json()["resultados"] if r["codigo"] == "PG_8_1"]
        assert urls_pg == ["/parte-geral/pg_8_1.html"]

