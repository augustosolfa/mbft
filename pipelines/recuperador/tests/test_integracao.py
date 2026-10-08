import pytest
from pathlib import Path
from mbft_recuperador.buscador import BuscadorHibrido
from mbft_recuperador.local_adapters import LocalSqliteDB, NumpyVectorDB, PyTorchEmbedder

@pytest.fixture(scope="module")
def jsonl_path():
    p = Path(__file__).parent.parent.parent.parent / "data" / "processed" / "indexador" / "embeddings_mbft.jsonl"
    if not p.exists():
        pytest.skip(f"Artefato JSONL {p} não encontrado. Execute o indexador antes.")
    return p

@pytest.fixture(scope="module")
def buscador(jsonl_path):
    vector_db = NumpyVectorDB(jsonl_path)
    relational_db = LocalSqliteDB(jsonl_path)
    embedder = PyTorchEmbedder()
    return BuscadorHibrido(vector_db, relational_db, embedder)

@pytest.mark.asyncio
@pytest.mark.parametrize("query,expected_code_options", [
    # Semântico "fácil" (Funcionava no Denso)
    ("iniciar obra na via que atrapalha pedestres sem permissão", ["751-01"]),
    ("exceder velocidade em mais de 50%", ["747-10"]),
    
    # Textual Exato (Falhava no Denso, deve funcionar com FTS5 Híbrido)
    ("Art. 162 I", ["501-00", "501-0"]),
    ("art 95", ["751-01", "751-02"]),
    
    # Textual misto
    ("dirigir sob influência de álcool", ["516-91"]), # O denso trazia o 516-92
])
async def test_busca_hibrida_integracao(buscador, query, expected_code_options):
    resultados = await buscador.recuperar_contexto(query, limit=5)
    
    # Validações
    assert len(resultados) > 0, "Deveria retornar chunks."
    
    # Coletar os códigos únicos das infrações no Top 5
    top_codes = []
    for r in resultados:
        code = r["metadata"].get("codigo")
        if code and code not in top_codes:
            top_codes.append(code)
            
    # Garantir que o código esperado está no Top 3 graças à fusão RRF
    # RRF somará os ranks e puxará os exatos para cima!
    top3 = top_codes[:3]
    
    # Um dos códigos esperados tem que estar no Top 3
    encontrou = any(c in expected_code_options for c in top3)
    
    assert encontrou, f"Query '{query}' não trouxe os códigos {expected_code_options} no Top 3. Trouxe: {top3}"
