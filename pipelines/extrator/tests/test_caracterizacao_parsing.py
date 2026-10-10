import pytest
from mbft_extrator.colunas import processar_coluna_normativa
from mbft_extrator.cabecalho import (
    extrair_celulas_cabecalho,
    extrair_metadados_cabecalho,
    fatiar_texto_em_campos,
)
from mbft_extrator.models import PaginaExtraida, RetanguloTexto
from mbft_extrator.pdf_geometry import RE_COLUMN_HEADER


class TestCaracterizacaoColunasNormativas:
    def test_nao_trata_decimais_como_itens(self):
        # Números decimais ou com separador de milhar não devem virar itens isolados
        linhas = [
            "1. Autuação obrigatória nas seguintes condições:",
            "1.5 km do posto de fiscalização rodoviária.",
            "100.000 pontos acumulados no prontuário.",
        ]
        campo = processar_coluna_normativa(linhas)
        # Deve ter apenas 1 item inicial, com os decimais costurados como corpo
        assert len(campo.itens) == 1
        assert "1.5 km do posto de fiscalização rodoviária." in campo.itens[0]
        assert "100.000 pontos acumulados no prontuário." in campo.itens[0]

    def test_decimais_como_primeira_linha(self):
        # Linha isolada iniciando com decimal não deve receber marcação de item
        linhas = ["1.5 km de extensão da via", "100.000 pontos computados"]
        campo = processar_coluna_normativa(linhas)
        # Deve ser mantido como linha de texto simples
        assert len(campo.itens) == 1
        assert campo.itens[0] == "1.5 km de extensão da via 100.000 pontos computados"
        assert not campo.itens[0].startswith("1.5. km")
        assert not campo.itens[0].startswith("100.00. ")
        assert not campo.itens[0].startswith("100. ")

    def test_itens_e_subitens_legitimos(self):
        linhas = [
            "1. Primeiro item principal",
            "1.1. Subitem específico",
            "1.1.1. Sub-subitem detalhado",
            "2. Segundo item principal",
            "10.1. Subitem com dois dígitos no pai",
            "1.10. Subitem com dois dígitos no filho",
        ]
        campo = processar_coluna_normativa(linhas)
        assert len(campo.itens) == 6
        assert campo.itens[0] == "1. Primeiro item principal"
        assert campo.itens[1] == "1.1. Subitem específico"
        assert campo.itens[2] == "1.1.1. Sub-subitem detalhado"
        assert campo.itens[3] == "2. Segundo item principal"
        assert campo.itens[4] == "10.1. Subitem com dois dígitos no pai"
        assert campo.itens[5] == "1.10. Subitem com dois dígitos no filho"

    def test_variacoes_de_decimais_e_unidades(self):
        linhas = [
            "1. Critérios de medição:",
            "0.5 l de combustível residual.",
            "1.50 metros de largura total.",
            "2.345 km de percurso realizado.",
        ]
        campo = processar_coluna_normativa(linhas)
        assert len(campo.itens) == 1
        assert "0.5 l de combustível residual." in campo.itens[0]
        assert "1.50 metros de largura total." in campo.itens[0]
        assert "2.345 km de percurso realizado." in campo.itens[0]


class TestCaracterizacaoCabecalhoLei14599:
    def test_competencia_alterada_lei_14599_detectada_no_conteudo(self):
        header_txt = (
            "Tipificação Resumida: Estacionar na calçada\n"
            "Código do Enquadramento: 554-12\n"
            "Competência: Órgão Municipal (competência alterada pela Lei 14.599/23)\n"
            "Pontuação: 5 pontos"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.competencia_alterada_lei_14599 is True
        assert "Lei 14.599/23" in (meta.competencia or "")

    def test_competencia_alterada_lei_14599_no_rotulo_antes_dos_dois_pontos(self):
        header_txt = (
            "Penalidade: Multa (3x)\n"
            "Competência (alterada pela Lei n. 14.599/23): Órgão ou Entidade de Trânsito Estadual, Municipal e Rodoviário.\n"
            "Pontuação: Não Computável"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.competencia_alterada_lei_14599 is True
        assert meta.penalidade == "Multa (3x)"
        assert meta.competencia == "Órgão ou Entidade de Trânsito Estadual, Municipal e Rodoviário."

    def test_competencia_alterada_lei_14599_no_rotulo_sem_dois_pontos(self):
        header_txt = (
            "Penalidade: Multa\n"
            "Competência (alterada pela Lei n. 14.599/23) Órgão ou Entidade de Trânsito Estadual, Municipal e Rodoviário.\n"
            "Pontuação: 7"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.competencia_alterada_lei_14599 is True
        assert meta.competencia == "Órgão ou Entidade de Trânsito Estadual, Municipal e Rodoviário."

    def test_competencia_alterada_lei_14599_formato_sem_ponto(self):
        header_txt = (
            "Competência Órgão Estadual - Alterada conforme Lei 14599\n"
            "Pontuação 4"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.competencia_alterada_lei_14599 is True

    def test_competencia_alterada_lei_14599_formato_com_espacos(self):
        header_txt_espaco = (
            "Competência: Órgão Municipal (alterada pela Lei 14. 599/23)\n"
            "Pontuação: 5 pontos"
        )
        meta_espaco = fatiar_texto_em_campos(header_txt_espaco)
        assert meta_espaco.competencia_alterada_lei_14599 is True

        header_txt_sem_ponto_espaco = (
            "Competência: Órgão Municipal (alterada pela Lei 14 599)\n"
            "Pontuação: 5 pontos"
        )
        meta_sem_ponto_espaco = fatiar_texto_em_campos(header_txt_sem_ponto_espaco)
        assert meta_sem_ponto_espaco.competencia_alterada_lei_14599 is True

    def test_competencia_sem_lei_14599(self):
        header_txt = (
            "Tipificação Resumida: Dirigir sob efeito de álcool\n"
            "Competência: Órgão Rodoviário Estadual e Municipal\n"
            "Pontuação: 7 pontos"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.competencia_alterada_lei_14599 is False


class TestCaracterizacaoMetadadosCabecalho:
    def test_remove_dois_pontos_e_ruido_governamental_com_acento_circunflexo(self):
        header_txt = (
            "FICHA DE FISCALIZAÇÃO\n"
            "Tipificação Resumida: Iniciar obra perturbe/interrompa circulação.\n"
            "Amparo Legal: Art. 95.\n"
            "Tipificação do Enquadramento: Nenhuma obra ou evento será iniciada sem permissão.\n"
            "Gravidade: Não aplicável\n"
            "Infrator: Pessoa Física ou Jurídica\n"
            "Pontuação: Não computável\n"
            "CONSELHO NACIONAL DE TRÂNSITO MANUAL BRASILEIRO DE FISCALIZAÇÃO DE TRÂNSITO – MBFT\n"
            "Penalidade: Multa\n"
            "Competência: Órgão ou Entidade de Trânsito Municipal e Rodoviário.\n"
            "Constatação da Infração: Mediante Abordagem.\n"
            "Medida Administrativa: Não aplicável\n"
            "Código Enquadramento: 751-01\n"
            "Pode Configurar Crime de Trânsito? : NÃO"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.tipificacao_resumida == "Iniciar obra perturbe/interrompa circulação."
        assert meta.amparo_legal == "Art. 95."
        assert meta.gravidade == "Não aplicável"
        assert meta.penalidade == "Multa"
        assert meta.medida_administrativa == "Não aplicável"
        assert meta.codigo_enquadramento == "751-01"
        assert meta.pode_configurar_crime_transito == "NÃO"
        assert meta.infrator == "Pessoa Física ou Jurídica"
        assert meta.competencia == "Órgão ou Entidade de Trânsito Municipal e Rodoviário."
        assert meta.pontuacao == "Não computável"
        assert meta.constatacao_infracao == "Mediante Abordagem."

    def test_nao_confunde_penalidade_ou_infrator_no_corpo_de_outros_campos(self):
        header_txt = (
            "Tipificação do Enquadramento: Incorre na mesma penalidade o condutor que não comprova exame.\n"
            "Penalidade: Multa (5x)\n"
            "Medida Administrativa: Retenção do veículo até a colocação do cinto pelo infrator.\n"
            "Pode Configurar Infração Penal: SIM 312 do CTB\n"
            "Infrator: Condutor"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.tipificacao_enquadramento == "Incorre na mesma penalidade o condutor que não comprova exame."
        assert meta.penalidade == "Multa (5x)"
        assert meta.medida_administrativa == "Retenção do veículo até a colocação do cinto pelo infrator."
        assert meta.pode_configurar_crime_transito == "SIM 312 do CTB"
        assert meta.infrator == "Condutor"

    def test_extrair_celulas_preserva_ordem_horizontal_com_variacao_yc_e_une_fragmentos(self):
        # Fragmentos na mesma linha com pequenas variações de yc (ex: ascendentes/descendentes/parênteses)
        # não devem ser embaralhados por sort direto em -yc, e fragmentos contíguos ("a" + "bordagem") devem unir-se.
        h_lines = [
            (36.0, 600.0, 560.0, 600.5),
            (36.0, 560.0, 560.0, 560.5),
            (36.0, 520.0, 560.0, 520.5),
        ]
        # Linha vertical com gap de 5.04pt em relação ao topo (como nas fichas 599-10 e 683-11)
        v_lines = [
            (36.0, 520.5, 36.5, 594.96),
            (170.0, 520.5, 170.5, 594.96),
            (435.0, 520.5, 435.5, 594.96),
            (560.0, 520.5, 560.5, 594.96),
        ]
        retangulos = [
            # Célula 1 (coluna 170..435, faixa 600..560): "Competência (alterada pela Lei n. 14.599/23):"
            RetanguloTexto(x0=171.2, y0=584.4, x1=224.6, y1=593.0, texto="Competência"),  # yc=588.7
            RetanguloTexto(x0=227.9, y0=584.4, x1=357.4, y1=593.5, texto="(alterada pela Lei n. 14.599/23)"),  # yc=588.95
            RetanguloTexto(x0=358.4, y0=586.1, x1=359.8, y1=590.7, texto=":"),  # yc=588.4
            # Linha 2 da mesma célula com diferentes yc para cada palavra:
            RetanguloTexto(x0=171.3, y0=572.1, x1=195.1, y1=582.1, texto="Órgão"),  # yc=577.1
            RetanguloTexto(x0=198.3, y0=573.8, x1=207.6, y1=578.6, texto="ou"),  # yc=576.2
            RetanguloTexto(x0=211.5, y0=573.8, x1=246.1, y1=580.6, texto="Entidade"),  # yc=577.2
            # Célula mesclada verticalmente na coluna 435..560 com "NÃO" exatamente sobre a divisória y=560
            RetanguloTexto(x0=440.0, y0=584.0, x1=550.0, y1=593.0, texto="Pode Configurar Crime de Trânsito:"),
            RetanguloTexto(x0=485.0, y0=556.0, x1=505.0, y1=564.0, texto="NÃO"),  # yc=560.0
            # Célula inferior com palavra quebrada "Mediante a" + "bordagem."
            RetanguloTexto(x0=171.4, y0=539.1, x1=273.5, y1=547.7, texto="Constatação da Infração:"),
            RetanguloTexto(x0=171.9, y0=526.9, x1=210.0, y1=535.4, texto="Mediante a"),
            RetanguloTexto(x0=210.5, y0=526.5, x1=260.8, y1=535.6, texto="bordagem."),
        ]
        page_ext = PaginaExtraida(
            largura=595.0,
            altura=842.0,
            retangulos=retangulos,
            linhas_vetoriais=h_lines + v_lines,
        )

        cells = extrair_celulas_cabecalho(page_ext, h_lines, v_lines)
        textos = [c["text"] for c in cells]
        assert "Competência (alterada pela Lei n. 14.599/23): Órgão ou Entidade" in textos
        assert "Constatação da Infração: Mediante abordagem." in textos
        # "NÃO" na fronteira de célula mesclada deve aparecer apenas uma vez
        assert sum("NÃO" in t for t in textos) == 1

        meta = extrair_metadados_cabecalho(page_ext, codigo_padrao="501-00")
        assert meta.competencia_alterada_lei_14599 is True
        assert meta.competencia == "Órgão ou Entidade"
        assert meta.constatacao_infracao == "Mediante abordagem."
        assert meta.pode_configurar_crime_transito == "NÃO"

    def test_extrair_celulas_fallback_sem_grade_vertical_preserva_colunas_e_multilinha(self):
        # Quando não há linhas verticais na faixa (ex: fichas 504-50 e 551-71 com paths compostos),
        # deve preservar a separação entre colunas mesmo quando os retângulos vêm em ordem linha-a-linha
        # (top-to-bottom) e quando uma coluna possui valor multilinha com x0 menor na segunda linha.
        h_lines = [
            (36.0, 628.0, 558.0, 628.5),
            (36.0, 566.5, 558.0, 567.0),
        ]
        v_lines = [
            (558.3, 567.0, 558.8, 628.0),  # Apenas 1 linha vertical (len(vl) < 2)
        ]
        # Retângulos deliberadamente em ordem linha-a-linha (intercalando colunas) e com segunda linha
        # da coluna Penalidade iniciando em x0=172.0 (< x0=180.0 da primeira linha do valor)
        retangulos = [
            RetanguloTexto(x0=42.0, y0=618.4, x1=86.5, y1=625.3, texto="Gravidade:"),
            RetanguloTexto(x0=172.5, y0=618.4, x1=220.2, y1=625.4, texto="Penalidade:"),
            RetanguloTexto(x0=180.0, y0=599.0, x1=285.0, y1=607.0, texto="Multa (10X) e suspensão do"),
            RetanguloTexto(x0=79.6, y0=581.8, x1=122.8, y1=588.8, texto="Gravíssima"),
            RetanguloTexto(x0=172.0, y0=586.0, x1=210.0, y1=594.0, texto="direito"),
            RetanguloTexto(x0=213.5, y0=586.0, x1=255.0, y1=594.0, texto="de dirigir."),
        ]
        page_ext = PaginaExtraida(
            largura=595.0,
            altura=842.0,
            retangulos=retangulos,
            linhas_vetoriais=h_lines + v_lines,
        )

        meta = extrair_metadados_cabecalho(page_ext, codigo_padrao="504-50")
        assert meta.gravidade == "Gravíssima"
        assert meta.penalidade == "Multa (10X) e suspensão do direito de dirigir."
        assert meta.codigo_enquadramento == "504-50"

    def test_cabecalho_entradas_vazias(self):
        meta_vazio = fatiar_texto_em_campos("")
        assert meta_vazio.tipificacao_resumida is None
        assert meta_vazio.competencia_alterada_lei_14599 is False

        page_vazia = PaginaExtraida(largura=595.0, altura=842.0, retangulos=[], linhas_vetoriais=[])
        meta_pag = extrair_metadados_cabecalho(page_vazia, codigo_padrao="501-00")
        assert meta_pag.codigo_enquadramento == "501-00"
        assert meta_pag.pode_configurar_crime_transito is None

    def test_codigo_de_enquadramento_e_medidas_administrativas_no_plural(self):
        from mbft_extrator.fatiador import REGEX_ENQUADRAMENTO

        for variante in [
            "Código do Enquadramento: 501-00",
            "Código de Enquadramento: 516-91",
            "Código Enquadramento: 751-01",
        ]:
            m = REGEX_ENQUADRAMENTO.search(variante)
            assert m is not None, f"Deveria casar '{variante}'"

        header_txt = (
            "Tipificação Resumida: Portar no veículo placas de identificação em desacordo c/ especif/modelo Contran.\n"
            "Amparo Legal: Art. 221.\n"
            "Tipificação de Enquadramento: Portar no veículo placas de identificação em desacordo com as especificações.\n"
            "Gravidade: Média\n"
            "Penalidade: Multa\n"
            "Competência (alterada pela Lei n. 14.599/23): Órgão ou Entidade de Trânsito Estadual, Municipal e Rodoviário.\n"
            "Constatação da Infração: Vide Definições e Procedimentos.\n"
            "Medidas Administrativas: Retenção do veículo para regularização e apreensão das placas irregulares.\n"
            "Código de Enquadramento: 640-80\n"
            "Pode Configurar Crime de Trânsito: NÃO"
        )
        meta = fatiar_texto_em_campos(header_txt)
        assert meta.codigo_enquadramento == "640-80"
        assert meta.medida_administrativa == "Retenção do veículo para regularização e apreensão das placas irregulares."
        assert meta.constatacao_infracao == "Vide Definições e Procedimentos."
        assert meta.tipificacao_enquadramento == "Portar no veículo placas de identificação em desacordo com as especificações."




class TestCaracterizacaoPdfGeometryReColumnHeader:
    def test_casamento_cabecalhos_colunas_validos(self):
        # Cabeçalhos válidos suportados (com e sem 'do AIT', com e sem dois-pontos)
        assert RE_COLUMN_HEADER.match("Quando Autuar")
        assert RE_COLUMN_HEADER.match("quando autuar:")
        assert RE_COLUMN_HEADER.match("Quando Não Autuar")
        assert RE_COLUMN_HEADER.match("Definições e Procedimentos")
        assert RE_COLUMN_HEADER.match("Definições e Procedimentos:")
        assert RE_COLUMN_HEADER.match("Exemplos do campo Observações do AIT:")
        assert RE_COLUMN_HEADER.match("Exemplos do campo Observações do AIT")
        assert RE_COLUMN_HEADER.match("Exemplos do campo 'Observações' do AIT")
        assert RE_COLUMN_HEADER.match("Exemplos do campo de observações do AIT:")
        assert RE_COLUMN_HEADER.match("Exemplos do campo de observações do AIT")
        assert RE_COLUMN_HEADER.match("Exemplos de Observações do AIT:")
        assert RE_COLUMN_HEADER.match("Exemplos de Observações do AIT")
        assert RE_COLUMN_HEADER.match("Exemplos do campo de observações")
        assert RE_COLUMN_HEADER.match("Exemplos do campo de observações:")
        assert RE_COLUMN_HEADER.match("Exemplos do campo observações")
        assert RE_COLUMN_HEADER.match("Exemplos de observações")
        assert RE_COLUMN_HEADER.match("Exemplos de observações:")
        assert RE_COLUMN_HEADER.match("Exemplos do campo 'observações'")

    def test_nao_descarta_linhas_de_corpo_com_exemplos_ou_definicoes(self):
        # Linhas de texto explicativo que NÃO são cabeçalhos de coluna
        linhas_corpo = [
            "Exemplos de situações que configuram a infração:",
            "Exemplos:",
            "Exemplos de preenchimento do auto de infração",
            "Exemplos práticos de abordagem",
            "Definições legais sobre velocidade",
            "Definições:",
            "Definições aplicáveis aos veículos de carga",
            "Definições operacionais",
            "1. Autuar condutor sem cinto",
        ]
        for linha in linhas_corpo:
            assert not RE_COLUMN_HEADER.match(linha), f"Linha de corpo não deveria casar: '{linha}'"
