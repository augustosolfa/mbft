import unittest
from mbft_core.models.extracao import CampoNormativo, Ficha
from mbft_core.models.enriquecimento import TipoSecaoParteGeralEnum
from mbft_enriquecedor.main import Enriquecedor
from mbft_enriquecedor.parte_geral import processar_parte_geral


class TestEnriquecimentoParteGeral(unittest.TestCase):
    def setUp(self):
        self.enriquecedor = Enriquecedor()
        self.ficha_bruta = Ficha(
            id="518-51",
            codigo_enquadramento="518-51",
            tipificacao_resumida="Deixar o condutor de usar o cinto de segurança",
            amparo_legal="Art. 167.",
            tipificacao_enquadramento="Deixar o condutor ou passageiro de usar o cinto de segurança",
            gravidade="Grave",
            penalidade="Multa",
            medida_administrativa="Retenção do veículo até colocação do cinto pelo infrator (Vide a Parte Geral deste Manual).",
            pode_configurar_crime_transito="NÃO",
            infrator="Condutor",
            competencia="Órgão ou Entidade Executivo Estadual e Rodoviário",
            pontuacao="5",
            constatacao_infracao="Possível sem abordagem",
            quando_autuar=CampoNormativo(
                texto="1. Condutor que não estiver utilizando o cinto.",
                itens=["1. Condutor que não estiver utilizando o cinto."],
            ),
            quando_nao_autuar=CampoNormativo(
                texto="1. Passageiro sem usar o cinto, autuar no enquadramento 518-52.",
                itens=["1. Passageiro sem usar o cinto, autuar no enquadramento 518-52."],
            ),
            definicoes_procedimentos=CampoNormativo(
                texto="1. Se simultaneamente segurando celular, autuar concomitantemente no 763-31.",
                itens=["1. Se simultaneamente segurando celular, autuar concomitantemente no 763-31."],
            ),
            exemplos_observacoes_ait=CampoNormativo(texto="", itens=[]),
            informacoes_complementares="Ver também 653-00.",
            paginas=[123, 124],
            imagens=[],
        )
        self.ficha_enriq = self.enriquecedor.processar_ficha(self.ficha_bruta)

    def test_enquadramentos_correlatos_populados_na_ficha_enriquecida(self):
        self.assertEqual(
            self.ficha_enriq.enquadramentos_correlatos,
            ["518-52", "653-00", "763-31"],
        )

    def test_processar_parte_geral_filtra_ruidos_extrai_glossario_e_vincula_fichas(self):
        md_exemplo = """
## MANUAL BRASILEIRO DE FISCALIZAÇÃO DE TRÂNSITO
Ruído pré-textual de capa e sumário.

## 1. APRESENTAÇÃO

## 1.1. A Segurança Viária e o Manual Brasileiro de Fiscalização de Trânsito (MBFT)
Texto editorial que deve ser descartado.

## 1.2. MBFT - Divisão e Modo de Utilização
O MBFT contempla os procedimentos gerais.

## 2. LISTA DE ABREVIATURAS E SIGLAS
AIT: Auto de Infração de Trânsito
CRLV-e: Certificado de Registro e Licenciamento de Veículo em meio digital

## 3. INTRODUÇÃO
Outro texto editorial descartável.

## 7. AUTUAÇÃO
A autuação é ato administrativo previsto no art. 280 do CTB.

## Infrações Sucessivas
Caracterizam-se pelo cometimento de repetidas condutas idênticas, na forma dos arts. 266 e 280 do CTB.

O agente da autoridade de trânsito, sempre que possível, deverá abordar o condutor do veículo para constatar a infração.
- Caso 1: “possível sem abordagem”

## 8.1. Retenção do Veículo
Consiste na imobilização do veículo no local da abordagem, nos termos do art. 270 do CTB.

## 11. FICHAS DE FISCALIZAÇÃO
Em anexo.
"""
        pg = processar_parte_geral(md_exemplo, [self.ficha_enriq])

        # 5 blocos descartados: pré-textual + 1 + 1.1 + 3 + 11
        self.assertEqual(pg.secoes_descartadas, 5)
        self.assertEqual(len(pg.glossario), 2)
        self.assertEqual(pg.glossario[0].sigla, "AIT")
        self.assertEqual(pg.glossario[1].sigla, "CRLV-e")

        ids_secoes = [s.id for s in pg.secoes]
        self.assertEqual(
            ids_secoes,
            ["PG_1_2", "PG_2", "PG_7", "PG_7_SUCESSIVAS", "PG_7_ABORDAGEM", "PG_8_1"],
        )

        sec_8_1 = next(s for s in pg.secoes if s.id == "PG_8_1")
        self.assertEqual(sec_8_1.tipo, TipoSecaoParteGeralEnum.TEMATICO)
        self.assertFalse(sec_8_1.aplica_a_todos)
        self.assertEqual(sec_8_1.enquadramentos_alvo, ["518-51"])


if __name__ == "__main__":
    unittest.main()
