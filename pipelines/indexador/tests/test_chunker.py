import unittest
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
from mbft_indexador.chunker import gerar_chunks_ficha

class TestChunker(unittest.TestCase):
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
                ItemRegra(texto="   ", natureza_regra=NaturezaRegraEnum.HIPOTESE_AUTUACAO), # Vazio
                ItemRegra(texto="", natureza_regra=NaturezaRegraEnum.HIPOTESE_AUTUACAO),    # Vazio
                ItemRegra(texto="Regra válida 2", natureza_regra=NaturezaRegraEnum.HIPOTESE_AUTUACAO),
            ],
            quando_nao_autuar_itens=[
                ItemRegra(texto="Não autuar se autorizado", natureza_regra=NaturezaRegraEnum.EXCECAO_DESVIO),
            ],
            definicoes_procedimentos_itens=[],
            exemplos_observacoes_ait_itens=[],
            informacoes_complementares_html="<p>Texto</p>",
            paginas=[32, 33],
            imagens=[],
        )

    def test_pula_itens_com_texto_vazio(self):
        chunks = gerar_chunks_ficha(self.ficha)
        # 2 regras validas em quando_autuar + 1 em quando_nao_autuar + 1 EMENTA = 4 chunks
        chunks_autuar = [c for c in chunks if c.metadata.secao == "QUANDO_AUTUAR"]
        self.assertEqual(len(chunks_autuar), 2)
        self.assertIn("Regra válida 1", chunks_autuar[0].texto_para_embedding)
        self.assertIn("Regra válida 2", chunks_autuar[1].texto_para_embedding)

    def test_preenchimento_de_texto_contextualizado_nos_metadados_sem_duplicacao(self):
        chunks = gerar_chunks_ficha(self.ficha)
        for chunk in chunks:
            # O texto completo contextualizado deve estar preenchido nos metadados
            self.assertIsNotNone(chunk.metadata.texto_contextualizado)
            self.assertTrue(len(chunk.metadata.texto_contextualizado) > 0)
            # E texto_para_embedding deve refletir o mesmo valor via property sem duplicar no dump do modelo
            self.assertEqual(chunk.texto_para_embedding, chunk.metadata.texto_contextualizado)
            self.assertNotIn("texto_para_embedding", chunk.model_dump())
            # Metadados devem conter os filtros essenciais para o Vectorize
            self.assertEqual(chunk.metadata.codigo, "751-01")
            self.assertEqual(chunk.metadata.artigo, "95")
            
        # Validar que ChunkMetadados exige texto_contextualizado não vazio
        from pydantic import ValidationError
        from mbft_core.models.indexacao import ChunkMetadados
        with self.assertRaises(ValidationError):
            ChunkMetadados(
                origem_id="751-01",
                secao="QUANDO_AUTUAR",
                codigo="751-01",
                artigo="95",
                gravidade="NAO_APLICAVEL",
            )
        for valor_invalido in ("", "   "):
            with self.assertRaises(ValidationError):
                ChunkMetadados(
                    origem_id="751-01",
                    secao="QUANDO_AUTUAR",
                    codigo="751-01",
                    artigo="95",
                    gravidade="NAO_APLICAVEL",
                    texto_contextualizado=valor_invalido,
                )

    def test_ementa_gerada_corretamente(self):
        chunks = gerar_chunks_ficha(self.ficha)
        ementa_chunks = [c for c in chunks if c.metadata.secao == "EMENTA"]
        self.assertEqual(len(ementa_chunks), 1)
        self.assertEqual(ementa_chunks[0].id, "751-01_EMENTA")

    def test_gerar_chunks_parte_geral_contextualizados(self):
        from mbft_core.models.enriquecimento import (
            ParteGeralEnriquecida,
            SecaoParteGeral,
            TipoSecaoParteGeralEnum,
        )
        from mbft_indexador.chunker import gerar_chunks_parte_geral

        pg = ParteGeralEnriquecida(
            secoes=[
                SecaoParteGeral(
                    id="PG_8_1",
                    slug="pg_8_1",
                    numero="8.1",
                    titulo="8.1. Retenção do Veículo",
                    tipo=TipoSecaoParteGeralEnum.TEMATICO,
                    texto="Consiste na imobilização do veículo.",
                    paragrafos=["Consiste na imobilização do veículo."],
                    medidas_associadas=[MedidaAdministrativaEnum.RETENCAO_VEICULO],
                    artigos_ctb=[ReferenciaCTB(artigo="270")],
                    enquadramentos_alvo=["518-51"],
                )
            ]
        )

        chunks_pg = gerar_chunks_parte_geral(pg)
        self.assertEqual(len(chunks_pg), 1)
        self.assertEqual(chunks_pg[0].id, "PG_8_1")
        self.assertEqual(chunks_pg[0].metadata.secao, "PARTE_GERAL")
        self.assertEqual(chunks_pg[0].metadata.codigo, "PG_8_1")
        self.assertEqual(chunks_pg[0].metadata.artigo, "270")
        self.assertIn("8.1. Retenção do Veículo", chunks_pg[0].texto_para_embedding)


if __name__ == "__main__":
    unittest.main()

