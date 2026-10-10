"""
Testes de contrato e guardrails do modelo Ficha (mbft_core).
"""

import unittest
from pydantic import ValidationError
from mbft_core.models.extracao import Ficha, CampoNormativo


class TestFichaGuardrails(unittest.TestCase):
    def setUp(self):
        self.dados_base = {
            "id": "768-42",
            "tipificacao_resumida": "Transitar em velocidade superior à máxima",
            "codigo_enquadramento": "768-42",
            "amparo_legal": "Art. 218, I",
            "tipificacao_enquadramento": "Transitar em velocidade superior à máxima permitida em até 20%",
            "gravidade": "Média",
            "penalidade": "Multa",
            "medida_administrativa": "Não",
            "pode_configurar_crime_transito": "NÃO",
            "infrator": "Condutor",
            "competencia": "Órgão ou Entidade de Trânsito Municipal e Rodoviário",
            "pontuacao": "4",
            "constatacao_infracao": "Sem abordagem",
            "quando_autuar": CampoNormativo(texto="Quando autuar."),
            "quando_nao_autuar": CampoNormativo(texto="Quando não autuar."),
            "definicoes_procedimentos": CampoNormativo(texto="Definições."),
            "exemplos_observacoes_ait": CampoNormativo(texto="Exemplos."),
            "informacoes_complementares": "<p>Não há.</p>",
            "paginas": [10, 11],
            "imagens": [],
        }

    def test_ficha_valida_com_competencia(self):
        ficha = Ficha(**self.dados_base)
        self.assertEqual(ficha.id, "768-42")
        self.assertEqual(ficha.competencia, "Órgão ou Entidade de Trânsito Municipal e Rodoviário")
        self.assertFalse(ficha.competencia_alterada_lei_14599)

    def test_ficha_valida_sem_competencia_none(self):
        dados = dict(self.dados_base)
        dados["competencia"] = None
        ficha = Ficha(**dados)
        self.assertIsNone(ficha.competencia)
        self.assertTrue(ficha.competencia_alterada_lei_14599)

    def test_ficha_invalida_competencia_string_vazia(self):
        dados = dict(self.dados_base)
        dados["competencia"] = ""
        with self.assertRaises(ValidationError) as ctx:
            Ficha(**dados)
        self.assertIn("competencia", str(ctx.exception))

        dados["competencia"] = "   "
        with self.assertRaises(ValidationError) as ctx:
            Ficha(**dados)
        self.assertIn("competencia", str(ctx.exception))

    def test_ficha_invalida_campos_vitais_vazios(self):
        campos_vitais = [
            "gravidade",
            "penalidade",
            "infrator",
            "amparo_legal",
            "tipificacao_enquadramento",
            "medida_administrativa",
            "pontuacao",
            "constatacao_infracao",
        ]
        for campo in campos_vitais:
            dados = dict(self.dados_base)
            dados[campo] = ""
            with self.assertRaises(ValidationError, msg=f"Campo {campo} deveria falhar com string vazia") as ctx:
                Ficha(**dados)
            self.assertIn(campo, str(ctx.exception))

    def test_ficha_invalida_campos_vitais_omitidos(self):
        campos_vitais = [
            "gravidade",
            "penalidade",
            "infrator",
            "amparo_legal",
            "tipificacao_enquadramento",
            "medida_administrativa",
            "pontuacao",
            "constatacao_infracao",
        ]
        for campo in campos_vitais:
            dados = dict(self.dados_base)
            del dados[campo]
            with self.assertRaises(ValidationError, msg=f"Campo {campo} deveria falhar quando omitido") as ctx:
                Ficha(**dados)
            self.assertIn(campo, str(ctx.exception))

    def test_ficha_crime_transito_none_ou_omitido(self):
        dados = dict(self.dados_base)
        dados["pode_configurar_crime_transito"] = None
        f1 = Ficha(**dados)
        self.assertIsNone(f1.pode_configurar_crime_transito)

        dados2 = dict(self.dados_base)
        del dados2["pode_configurar_crime_transito"]
        f2 = Ficha(**dados2)
        self.assertIsNone(f2.pode_configurar_crime_transito)

        dados3 = dict(self.dados_base)
        dados3["pode_configurar_crime_transito"] = ""
        f3 = Ficha(**dados3)
        self.assertIsNone(f3.pode_configurar_crime_transito)

    def test_validar_consistencia_id_e_codigo(self):
        dados = dict(self.dados_base)
        dados["id"] = "751-01_p2"
        dados["codigo_enquadramento"] = "751-01"
        f = Ficha(**dados)
        self.assertEqual(f.id, "751-01_p2")
        self.assertEqual(f.codigo_enquadramento, "751-01")


if __name__ == "__main__":
    unittest.main()
