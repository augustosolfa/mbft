import os
from unittest.mock import patch

import pytest

from mbft_api.gerador.local_adapters import GeminiLLMClient


def _sem_chaves_gemini():
    return patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""},
    )


def test_sem_chave_falha_com_erro_claro_antes_de_construir_o_sdk():
    with _sem_chaves_gemini():
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            GeminiLLMClient()


def test_com_chave_constroi_o_cliente_sem_chamada_de_rede():
    with patch.dict(os.environ, {"GEMINI_API_KEY": "chave-fake-de-teste", "GOOGLE_API_KEY": ""}):
        cliente = GeminiLLMClient()
        assert cliente.model == "gemini-3.1-flash-lite"
