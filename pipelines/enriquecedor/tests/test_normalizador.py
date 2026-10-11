import unittest
from mbft_core.models.enriquecimento import InfratorEnum, ReferenciaCTB, MedidaAdministrativaEnum
from mbft_enriquecedor.normalizador import (
    parse_amparo_legal,
    higienizar_infrator_crime,
    normalizar_medidas_administrativas,
)

class TestNormalizador(unittest.TestCase):
    def test_parse_amparo_legal_artigo_simples(self):
        refs = parse_amparo_legal("Art. 95.")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0], ReferenciaCTB(artigo="95"))

    def test_parse_amparo_legal_paragrafo_e_inciso_mesma_instancia(self):
        refs = parse_amparo_legal("Art. 165, § 1º, I")
        self.assertEqual(len(refs), 1)
        self.assertEqual(
            refs[0],
            ReferenciaCTB(artigo="165", paragrafo="§ 1º", inciso="I")
        )

    def test_parse_amparo_legal_romano_case_sensitive(self):
        # Minúsculo não deve casar
        refs_minusculo = parse_amparo_legal("Art. 162, i")
        self.assertEqual(len(refs_minusculo), 1)
        self.assertIsNone(refs_minusculo[0].inciso)
        
        # Maiúsculo deve casar
        refs_maiusculo = parse_amparo_legal("Art. 162, I")
        self.assertEqual(len(refs_maiusculo), 1)
        self.assertEqual(refs_maiusculo[0].inciso, "I")

    def test_parse_amparo_legal_limitado_ao_texto_apos_artigo(self):
        # Inciso ou parágrafo antes do primeiro artigo não deve ser atribuído
        # e cada artigo deve receber apenas o que vem após ele
        refs = parse_amparo_legal("Art. 165 c/c 277, § 3º")
        self.assertEqual(len(refs), 2)
        # Art. 165 não tem parágrafo
        self.assertEqual(refs[0].artigo, "165")
        self.assertIsNone(refs[0].paragrafo)
        # Art. 277 tem o § 3º
        self.assertEqual(refs[1].artigo, "277")
        self.assertEqual(refs[1].paragrafo, "§ 3º")

    def test_higienizar_infrator_crime_word_boundary_sim(self):
        infratores, tem_crime, artigos = higienizar_infrator_crime(
            texto_infrator="Condutor SIM",
            texto_crime="NÃO"
        )
        self.assertEqual(infratores, [InfratorEnum.CONDUTOR])
        self.assertTrue(tem_crime)

    def test_higienizar_infrator_crime_nao_seta_crime_apenas_por_artigos(self):
        # Texto de crime diz NÃO, mas contém menção a Artigo
        infratores, tem_crime, artigos = higienizar_infrator_crime(
            texto_infrator="Condutor",
            texto_crime="NÃO Art. 310 do CTB"
        )
        self.assertEqual(infratores, [InfratorEnum.CONDUTOR])
        self.assertFalse(tem_crime, "Não deve setar tem_crime=True apenas por encontrar artigos")
        self.assertEqual(len(artigos), 1)
        self.assertEqual(artigos[0].artigo, "310")

    def test_higienizar_infrator_crime_detecta_crime_quando_sim(self):
        infratores, tem_crime, artigos = higienizar_infrator_crime(
            texto_infrator="Condutor",
            texto_crime="SIM Art. 309 do CTB"
        )
        self.assertEqual(infratores, [InfratorEnum.CONDUTOR])
        self.assertTrue(tem_crime)
        self.assertEqual(len(artigos), 1)
        self.assertEqual(artigos[0].artigo, "309")

    def test_normalizar_medidas_administrativas_palavra_exata_teste(self):
        res_teste = normalizar_medidas_administrativas("TESTE")
        self.assertIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_teste)

        res_testes_plural = normalizar_medidas_administrativas("Realização de testes toxicológicos ou de alcoolemia")
        self.assertIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_testes_plural)

        res_frase = normalizar_medidas_administrativas("Realização de teste com etilômetro")
        self.assertIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_frase)

        res_alcoolemia = normalizar_medidas_administrativas("Exame de alcoolemia")
        self.assertIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_alcoolemia)

    def test_normalizar_medidas_administrativas_evita_falso_positivo_testemunha(self):
        res_testemunha = normalizar_medidas_administrativas("TESTEMUNHA")
        self.assertNotIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_testemunha)
        self.assertEqual(res_testemunha, [MedidaAdministrativaEnum.NAO_APLICAVEL])

        res_testemunhas_plural = normalizar_medidas_administrativas("TESTEMUNHAS")
        self.assertNotIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_testemunhas_plural)
        self.assertEqual(res_testemunhas_plural, [MedidaAdministrativaEnum.NAO_APLICAVEL])

        res_proteste = normalizar_medidas_administrativas("PROTESTE")
        self.assertNotIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_proteste)

        res_atestado = normalizar_medidas_administrativas("ATESTADO MEDICO")
        self.assertNotIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_atestado)

        res_arrolamento = normalizar_medidas_administrativas("Arrolamento de testemunhas no local")
        self.assertNotIn(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA, res_arrolamento)
        self.assertEqual(res_arrolamento, [MedidaAdministrativaEnum.NAO_APLICAVEL])

    def test_parse_amparo_legal_incompatibilidade_mais_incisos_que_paragrafos(self):
        refs = parse_amparo_legal("Art. 165, § 1º e § 2º, I, II e III")
        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0], ReferenciaCTB(artigo="165", paragrafo="§ 1º", inciso="I"))
        self.assertEqual(refs[1], ReferenciaCTB(artigo="165", paragrafo="§ 2º", inciso="II"))
        self.assertEqual(refs[2], ReferenciaCTB(artigo="165", paragrafo=None, inciso="III"))

    def test_parse_amparo_legal_incompatibilidade_mais_paragrafos_que_incisos(self):
        refs = parse_amparo_legal("Art. 165, § 1º, § 2º e § 3º, I e II")
        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0], ReferenciaCTB(artigo="165", paragrafo="§ 1º", inciso="I"))
        self.assertEqual(refs[1], ReferenciaCTB(artigo="165", paragrafo="§ 2º", inciso="II"))
        self.assertEqual(refs[2], ReferenciaCTB(artigo="165", paragrafo="§ 3º", inciso=None))

    def test_parse_amparo_legal_multiplos_artigos_com_incompatibilidade(self):
        refs = parse_amparo_legal("Art. 165, § 1º, § 2º, I, II e III c/c Art. 277, § 3º e § 4º, IV")
        self.assertEqual(len(refs), 5)
        # Artigo 165: 2 parágrafos, 3 incisos -> 3 referências via zip_longest
        self.assertEqual(refs[0], ReferenciaCTB(artigo="165", paragrafo="§ 1º", inciso="I"))
        self.assertEqual(refs[1], ReferenciaCTB(artigo="165", paragrafo="§ 2º", inciso="II"))
        self.assertEqual(refs[2], ReferenciaCTB(artigo="165", paragrafo=None, inciso="III"))
        # Artigo 277: 2 parágrafos, 1 inciso -> 2 referências atribuindo o inciso a ambos
        self.assertEqual(refs[3], ReferenciaCTB(artigo="277", paragrafo="§ 3º", inciso="IV"))
        self.assertEqual(refs[4], ReferenciaCTB(artigo="277", paragrafo="§ 4º", inciso="IV"))

    def test_normalizar_medidas_administrativas_inominadas_mercadoria_e_placas(self):
        res_mercadoria = normalizar_medidas_administrativas("Remoção da mercadoria ou do material.")
        self.assertEqual(res_mercadoria, [MedidaAdministrativaEnum.REMOCAO_MERCADORIA_MATERIAL])

        res_veiculo = normalizar_medidas_administrativas("Remoção do veículo (Vide a Parte Geral deste Manual).")
        self.assertEqual(res_veiculo, [MedidaAdministrativaEnum.REMOCAO_VEICULO])

        res_apreensao_placas = normalizar_medidas_administrativas("Multa e apreensão das placas irregulares.")
        self.assertEqual(res_apreensao_placas, [MedidaAdministrativaEnum.RECOLHIMENTO_PLACAS])


if __name__ == "__main__":
    unittest.main()

