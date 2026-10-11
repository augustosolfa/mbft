import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from mbft_core.models.enriquecimento import (
    FichaEnriquecida,
    GravidadeEnum,
    PenalidadeEnum,
    MedidaAdministrativaEnum,
    InfratorEnum,
    ConstatacaoInfracaoEnum,
    CompetenciaEnum,
    CompetenciaFonteEnum,
    NaturezaRegraEnum,
    ItemRegra,
    ReferenciaCTB,
)
from mbft_core.models.extracao import CampoNormativo
from mbft_indexador.cli import processar_indexacao, main
from mbft_indexador.embedder import FakeEmbedder

class TestIndexadorCli(unittest.TestCase):
    def setUp(self):
        self.ficha = FichaEnriquecida(
            id="751-01",
            codigo_enquadramento="751-01",
            tipificacao_resumida="Iniciar obra sem permissão",
            amparo_legal="Art. 95",
            tipificacao_enquadramento="Nenhuma obra será iniciada sem permissão...",
            gravidade_original="NÃO APLICÁVEL",
            penalidade_original="MULTA",
            medida_administrativa_original="NÃO APLICÁVEL",
            infrator_original="PESSOA FÍSICA OU JURÍDICA",
            competencia_original="MUNICIPAL",
            constatacao_infracao_original="MEDIANTE ABORDAGEM",
            pontuacao_original="NÃO COMPUTÁVEL",
            quando_autuar_original=CampoNormativo(),
            quando_nao_autuar_original=CampoNormativo(),
            definicoes_procedimentos_original=CampoNormativo(),
            exemplos_observacoes_ait_original=CampoNormativo(),
            gravidade=GravidadeEnum.NAO_APLICAVEL,
            penalidades=[PenalidadeEnum.MULTA],
            medidas_administrativas=[MedidaAdministrativaEnum.NAO_APLICAVEL],
            infratores=[InfratorEnum.PESSOA_FISICA_OU_JURIDICA],
            competencias=[CompetenciaEnum.MUNICIPAL],
            competencia_fonte=CompetenciaFonteEnum.MBFT_ORIGINAL,
            competencia_alterada_lei_14599=False,
            crime_transito=False,
            constatacao_infracao=[ConstatacaoInfracaoEnum.COM_ABORDAGEM],
            artigos_ctb=[ReferenciaCTB(artigo="95")],
            quando_autuar_itens=[
                ItemRegra(texto="Regra válida 1", natureza_regra=NaturezaRegraEnum.HIPOTESE_AUTUACAO),
            ],
            quando_nao_autuar_itens=[],
            definicoes_procedimentos_itens=[],
            exemplos_observacoes_ait_itens=[],
            informacoes_complementares_html="<p>Texto</p>",
            paginas=[32, 33],
            imagens=[],
        )

    def test_processar_indexacao_asserts_dimensao_e_contagem(self):
        embedder = FakeEmbedder(dimensoes=1024)
        payloads = processar_indexacao([self.ficha], embedder)
        self.assertTrue(len(payloads) > 0)
        self.assertEqual(len(payloads[0].values), 1024)

    def test_processar_indexacao_falha_dimensao_incorreta(self):
        embedder = FakeEmbedder(dimensoes=512)
        with self.assertRaises(AssertionError) as ctx:
            processar_indexacao([self.ficha], embedder, dimensao_esperada=1024)
        self.assertIn("Dimensão do vetor", str(ctx.exception))

    def test_processar_indexacao_falha_contagem_incorreta(self):
        class BadEmbedder:
            def gerar_embeddings_lote(self, textos, batch_size=32):
                return [[0.0] * 1024]  # Retorna apenas 1 vetor mesmo para N textos
        with self.assertRaises(AssertionError) as ctx:
            processar_indexacao([self.ficha], BadEmbedder())
        self.assertIn("Quantidade de vetores", str(ctx.exception))

    def test_main_exit_non_zero_input_inexistente(self):
        with patch.object(sys, "argv", ["cli.py", "--input", "arquivo_que_nao_existe_12345.json"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertNotEqual(cm.exception.code, 0)

    def test_main_caminhos_padrao_usam_processed_dir(self):
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_processed = Path(tmpdir)
            enriq_dir = fake_processed / "enriquecedor"
            enriq_dir.mkdir(parents=True, exist_ok=True)
            input_file = enriq_dir / "fichas_enriquecidas.json"
            input_file.write_text(
                json.dumps([self.ficha.model_dump(mode="json")]),
                encoding="utf-8",
            )
            with patch("mbft_indexador.cli.PROCESSED_DIR", fake_processed):
                with patch.object(sys, "argv", ["cli.py", "--skip-embeddings"]):
                    main()
                debug_out = fake_processed / "indexador" / "embeddings_debug.jsonl"
                self.assertTrue(debug_out.exists(), "Deveria gravar em PROCESSED_DIR/indexador/embeddings_debug.jsonl com --skip-embeddings")
                lines = debug_out.read_text(encoding="utf-8").strip().splitlines()
                self.assertTrue(len(lines) > 0)
                first_obj = json.loads(lines[0])
                self.assertTrue(len(first_obj["metadata"]["texto_contextualizado"]) > 0)

if __name__ == "__main__":
    unittest.main()
