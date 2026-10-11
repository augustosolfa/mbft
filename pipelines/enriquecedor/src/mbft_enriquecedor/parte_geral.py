"""
Processamento, higienização e enriquecimento semântico da Parte Geral do MBFT.

Converte o artefato bruto `mbft_parte_geral.md` em `ParteGeralEnriquecida`,
descartando ruídos pré-textuais/editoriais, estruturando o glossário de siglas
e vinculando deterministicamente as seções temáticas às 412 fichas enriquecidas.
"""

import re
from typing import Dict, List, Optional, Tuple

from mbft_core.models.enriquecimento import (
    ConstatacaoInfracaoEnum,
    FichaEnriquecida,
    InfratorEnum,
    ItemGlossario,
    MedidaAdministrativaEnum,
    ParteGeralEnriquecida,
    ReferenciaCTB,
    SecaoParteGeral,
    TipoSecaoParteGeralEnum,
)
from mbft_enriquecedor.extrator_regras import expandir_codigos
from mbft_enriquecedor.normalizador import parse_resolucoes_contran, sanitizar_texto

REGEX_H2 = re.compile(r"^##\s+(.+?)\s*$")
REGEX_GLOSSARIO_LINHA = re.compile(r"^([A-Za-zÀ-ÿ0-9.\-]+)\s*:\s*(.+)$")

# Marcador do início do bloco de Abordagem / Combinação de Veículos ao final da seção 7
MARCADOR_ABORDAGEM_SECAO_7 = (
    "O agente da autoridade de trânsito, sempre que possível, deverá abordar o condutor"
)


def extrair_artigos_ctb_prosa(texto: str) -> List[ReferenciaCTB]:
    """
    Extrai referências a artigos do CTB em texto corrido da Parte Geral,
    ignorando menções a artigos de outras leis (ex.: 'art. 5º da Lei nº 13.022').
    """
    artigos_vistos = set()
    referencias: List[ReferenciaCTB] = []

    # Remove temporariamente trechos explícitos "art. X da Lei nº ..."
    texto_limpo = re.sub(
        r"art(?:igo)?s?\.?\s*\d+[º°]?\s+da\s+Lei\s+n[º°o]?\s*[\d\.]+",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    # Remove observações entre parênteses para facilitar listas como "artigos 221 (...), 243 (...)"
    texto_sem_parenteses = re.sub(r"\([^)]*\)", "", texto_limpo)

    # 1. Padrão plural/lista após "art.", "arts.", "artigo", "artigos"
    for match_plural in re.finditer(
        r"\bart(?:igo)?s?\.?\s+((?:(?:inciso\s+[IVXLCDM]+\s*,?\s*)?\d{1,3}(?:-[A-Za-z]+)?(?:\s*,\s*(?:inciso\s+)?[IVXLCDM]+)?(?:\s*(?:[;,]|\be\b|\bou\b)\s*)*)+)",
        texto_sem_parenteses,
        flags=re.IGNORECASE,
    ):
        bloco = match_plural.group(1)
        for m_num in re.finditer(r"\b(\d{1,3}(?:-[A-Za-z]+)?)\b(?!\s*-\d{2})", bloco):
            num = m_num.group(1).upper()
            if num not in artigos_vistos:
                artigos_vistos.add(num)
                referencias.append(ReferenciaCTB(artigo=num))

    # 2. Padrão individual "art. 280", "artigo 269", "(art. 167)"
    for match_sing in re.finditer(
        r"\bart(?:igo)?s?\.?\s*(\d{1,3}(?:-[A-Za-z]+)?)\b(?!\s*-\d{2})",
        texto_limpo,
        flags=re.IGNORECASE,
    ):
        num = match_sing.group(1).upper()
        if num not in artigos_vistos:
            artigos_vistos.add(num)
            referencias.append(ReferenciaCTB(artigo=num))

    return referencias




def _extrair_paragrafos(linhas: List[str]) -> List[str]:
    paragrafos: List[str] = []
    for linha in linhas:
        limpa = sanitizar_texto(linha.strip())
        if limpa:
            paragrafos.append(limpa)
    return paragrafos


def _dividir_em_blocos_h2(markdown_texto: str) -> List[Tuple[str, List[str]]]:
    """
    Divide o Markdown bruto em blocos `(titulo_h2, linhas_conteudo)` a partir
    do primeiro cabeçalho normativo `## 1. APRESENTAÇÃO`.
    """
    linhas = markdown_texto.splitlines()
    blocos: List[Tuple[str, List[str]]] = []
    titulo_atual: Optional[str] = None
    buffer_linhas: List[str] = []
    iniciou_normativo = False

    for linha in linhas:
        m = REGEX_H2.match(linha.strip())
        if m:
            titulo_h2 = sanitizar_texto(m.group(1))
            if titulo_h2.upper().startswith("1. APRESENTA"):
                iniciou_normativo = True
            if not iniciou_normativo:
                continue
            if titulo_atual is not None:
                blocos.append((titulo_atual, buffer_linhas))
            titulo_atual = titulo_h2
            buffer_linhas = []
        else:
            if iniciou_normativo and titulo_atual is not None:
                buffer_linhas.append(linha)

    if titulo_atual is not None:
        blocos.append((titulo_atual, buffer_linhas))

    return blocos


def _vincular_fichas_secao(
    secao_id: str,
    medidas: List[MedidaAdministrativaEnum],
    infratores: List[InfratorEnum],
    artigos_secao: List[ReferenciaCTB],
    fichas: List[FichaEnriquecida],
) -> List[str]:
    """
    Calcula deterministicamente a lista de `codigo_enquadramento` das fichas
    às quais uma seção `TEMATICO` da Parte Geral se aplica.
    """
    codigos_alvo = set()
    artigos_nums = {a.artigo for a in artigos_secao}

    for f in fichas:
        artigos_ficha = {a.artigo for a in f.artigos_ctb}

        # 1. Vínculo por Medida Administrativa controlada
        if medidas and any(m in f.medidas_administrativas for m in medidas):
            codigos_alvo.add(f.codigo_enquadramento)
            continue

        # 2. Vínculo por Infrator controlado
        if infratores and any(inf in f.infratores for inf in infratores):
            codigos_alvo.add(f.codigo_enquadramento)
            continue

        # 3. Regras específicas por seção temática
        if secao_id == "PG_7_CONCORRENTES":
            # Fichas que possuem redirecionamento ("Quando não autuar -> usar outro código") ou artigos citados
            tem_redirecionamento = any(
                bool(r.codigos_redirecionamento) for r in f.quando_nao_autuar_itens
            )
            if tem_redirecionamento or (artigos_nums & artigos_ficha):
                codigos_alvo.add(f.codigo_enquadramento)

        elif secao_id == "PG_7_CONCOMITANTES":
            # Fichas que possuem regras de concomitância ou artigos citados
            todas_regras = (
                f.quando_autuar_itens
                + f.quando_nao_autuar_itens
                + f.definicoes_procedimentos_itens
            )
            tem_concomitancia = any(bool(r.codigos_concomitantes) for r in todas_regras)
            if tem_concomitancia or (artigos_nums & artigos_ficha):
                codigos_alvo.add(f.codigo_enquadramento)

        elif secao_id == "PG_7_1":
            # Fiscalização de veículos de emergência por equipamentos eletrônicos:
            # aplica-se às fichas passíveis de constatação sem abordagem / videomonitoramento ou arts. citados
            if (
                ConstatacaoInfracaoEnum.SEM_ABORDAGEM in f.constatacao_infracao
                or ConstatacaoInfracaoEnum.VIDEOMONITORAMENTO in f.constatacao_infracao
                or (artigos_nums & artigos_ficha)
            ):
                codigos_alvo.add(f.codigo_enquadramento)

        elif secao_id == "PG_8_7":
            # Medidas Administrativas Inominadas (arts. 221, 243, 245, 255, 278)
            if artigos_nums & artigos_ficha:
                codigos_alvo.add(f.codigo_enquadramento)

        elif secao_id == "PG_9_1":
            # Condutor Oriundo de País Estrangeiro (infrações de habilitação: arts. 162, 163, 164, 232)
            if artigos_ficha & {"162", "163", "164", "232"}:
                codigos_alvo.add(f.codigo_enquadramento)

    return sorted(codigos_alvo)


def _construir_secao(
    id_secao: str,
    slug: str,
    titulo: str,
    tipo: TipoSecaoParteGeralEnum,
    paragrafos: List[str],
    fichas: List[FichaEnriquecida],
    medidas: Optional[List[MedidaAdministrativaEnum]] = None,
    infratores: Optional[List[InfratorEnum]] = None,
) -> SecaoParteGeral:
    medidas_lista = medidas or []
    infratores_lista = infratores or []
    texto_markdown = "\n\n".join(paragrafos)

    artigos_ctb = extrair_artigos_ctb_prosa(texto_markdown)
    resolucoes = sorted(set(parse_resolucoes_contran(texto_markdown)))
    codigos_citados = expandir_codigos(texto_markdown)

    aplica_a_todos = tipo in (
        TipoSecaoParteGeralEnum.GLOBAL,
        TipoSecaoParteGeralEnum.APOIO,
        TipoSecaoParteGeralEnum.GLOSSARIO,
    )

    enquadramentos_alvo: List[str] = []
    if tipo == TipoSecaoParteGeralEnum.TEMATICO:
        enquadramentos_alvo = _vincular_fichas_secao(
            secao_id=id_secao,
            medidas=medidas_lista,
            infratores=infratores_lista,
            artigos_secao=artigos_ctb,
            fichas=fichas,
        )

    m_num = re.match(r"^(\d+(?:\.\d+)?)\.", titulo)
    numero = m_num.group(1) if m_num else id_secao.replace("PG_", "").lower()

    return SecaoParteGeral(
        id=id_secao,
        slug=slug,
        numero=numero,
        titulo=titulo,
        tipo=tipo,
        texto=texto_markdown,
        paragrafos=paragrafos,
        artigos_ctb=artigos_ctb,
        resolucoes_contran=resolucoes,
        codigos_citados=codigos_citados,
        medidas_associadas=medidas_lista,
        infratores_associados=infratores_lista,
        aplica_a_todos=aplica_a_todos,
        enquadramentos_alvo=enquadramentos_alvo,
    )



# Mapa determinístico de classificação das seções H2 da Parte Geral
MAPA_SECOES_H2: Dict[str, dict] = {
    "1. APRESENTAÇÃO": {"descartar": True},
    "1.1. A SEGURANÇA VIÁRIA E O MANUAL BRASILEIRO DE FISCALIZAÇÃO DE TRÂNSITO (MBFT)": {
        "descartar": True
    },
    "1.2. MBFT - DIVISÃO E MODO DE UTILIZAÇÃO": {
        "id": "PG_1_2",
        "slug": "pg_1_2",
        "titulo": "1.2. MBFT - Divisão e Modo de Utilização",
        "tipo": TipoSecaoParteGeralEnum.APOIO,
    },
    "2. LISTA DE ABREVIATURAS E SIGLAS": {
        "id": "PG_2",
        "slug": "pg_2",
        "titulo": "2. Lista de Abreviaturas e Siglas",
        "tipo": TipoSecaoParteGeralEnum.GLOSSARIO,
    },
    "3. INTRODUÇÃO": {"descartar": True},
    "4. AGENTE DA AUTORIDADE DE TRÂNSITO": {
        "id": "PG_4",
        "slug": "pg_4",
        "titulo": "4. Agente da Autoridade de Trânsito",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "5. INFRAÇÃO DE TRÂNSITO": {
        "id": "PG_5",
        "slug": "pg_5",
        "titulo": "5. Infração de Trânsito",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "6. RESPONSABILIDADE PELA INFRAÇÃO": {
        "id": "PG_6",
        "slug": "pg_6",
        "titulo": "6. Responsabilidade pela Infração",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "6.1. PROPRIETÁRIO": {
        "id": "PG_6_1",
        "slug": "pg_6_1",
        "titulo": "6.1. Responsabilidade — Proprietário",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "infratores": [
            InfratorEnum.PROPRIETARIO,
            InfratorEnum.CONDUTOR_OU_PROPRIETARIO,
        ],
    },
    "6.2. CONDUTOR": {
        "id": "PG_6_2",
        "slug": "pg_6_2",
        "titulo": "6.2. Responsabilidade — Condutor",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "infratores": [
            InfratorEnum.CONDUTOR,
            InfratorEnum.CONDUTOR_OU_PROPRIETARIO,
        ],
    },
    "6.3. EMBARCADOR": {
        "id": "PG_6_3",
        "slug": "pg_6_3",
        "titulo": "6.3. Responsabilidade — Embarcador",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "infratores": [InfratorEnum.EMBARCADOR],
    },
    "6.4. TRANSPORTADOR": {
        "id": "PG_6_4",
        "slug": "pg_6_4",
        "titulo": "6.4. Responsabilidade — Transportador",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "infratores": [InfratorEnum.TRANSPORTADOR],
    },
    "6.5. RESPONSABILIDADE SOLIDÁRIA": {
        "id": "PG_6_5",
        "slug": "pg_6_5",
        "titulo": "6.5. Responsabilidade Solidária",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "infratores": [
            InfratorEnum.CONDUTOR_OU_PROPRIETARIO,
            InfratorEnum.PESSOA_FISICA_OU_JURIDICA,
            InfratorEnum.EMBARCADOR,
            InfratorEnum.TRANSPORTADOR,
        ],
    },
    "7. AUTUAÇÃO": {
        "id": "PG_7",
        "slug": "pg_7",
        "titulo": "7. Autuação",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "INFRAÇÕES CONCORRENTES": {
        "id": "PG_7_CONCORRENTES",
        "slug": "pg_7_concorrentes",
        "titulo": "7. Autuação — Infrações Concorrentes",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
    },
    "INFRAÇÕES CONCOMITANTES": {
        "id": "PG_7_CONCOMITANTES",
        "slug": "pg_7_concomitantes",
        "titulo": "7. Autuação — Infrações Concomitantes",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
    },
    "INFRAÇÕES CONTINUADAS": {
        "id": "PG_7_CONTINUADAS",
        "slug": "pg_7_continuadas",
        "titulo": "7. Autuação — Infrações Continuadas",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "INFRAÇÕES SUCESSIVAS": {
        "id": "PG_7_SUCESSIVAS",
        "slug": "pg_7_sucessivas",
        "titulo": "7. Autuação — Infrações Sucessivas",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "7.1. FISCALIZAÇÃO DE VEÍCULOS DE EMERGÊNCIA POR EQUIPAMENTOS ELETRÔNICOS": {
        "id": "PG_7_1",
        "slug": "pg_7_1",
        "titulo": "7.1. Fiscalização de Veículos de Emergência por Equipamentos Eletrônicos",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
    },
    "8. MEDIDAS ADMINISTRATIVAS": {
        "id": "PG_8",
        "slug": "pg_8",
        "titulo": "8. Medidas Administrativas",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "8.1. RETENÇÃO DO VEÍCULO": {
        "id": "PG_8_1",
        "slug": "pg_8_1",
        "titulo": "8.1. Retenção do Veículo",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "medidas": [MedidaAdministrativaEnum.RETENCAO_VEICULO],
    },
    "8.2. REMOÇÃO DO VEÍCULO": {
        "id": "PG_8_2",
        "slug": "pg_8_2",
        "titulo": "8.2. Remoção do Veículo",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "medidas": [MedidaAdministrativaEnum.REMOCAO_VEICULO],
    },
    "8.3. RECOLHIMENTO DO DOCUMENTO DE HABILITAÇÃO": {
        "id": "PG_8_3",
        "slug": "pg_8_3",
        "titulo": "8.3. Recolhimento do Documento de Habilitação",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "medidas": [MedidaAdministrativaEnum.RECOLHIMENTO_CNH],
    },
    "8.4. RECOLHIMENTO DO CERTIFICADO DE LICENCIAMENTO ANUAL (CLA/CRLV-E)": {
        "id": "PG_8_4",
        "slug": "pg_8_4",
        "titulo": "8.4. Recolhimento do Certificado de Licenciamento Anual (CLA/CRLV-e)",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "medidas": [
            MedidaAdministrativaEnum.RECOLHIMENTO_CRLV,
            MedidaAdministrativaEnum.RETENCAO_VEICULO,
            MedidaAdministrativaEnum.REMOCAO_VEICULO,
        ],
    },
    "8.5. TRANSBORDO DO EXCESSO DE CARGA": {
        "id": "PG_8_5",
        "slug": "pg_8_5",
        "titulo": "8.5. Transbordo do Excesso de Carga",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "medidas": [MedidaAdministrativaEnum.TRANSBORDO_CARGA],
    },
    "8.6. RECOLHIMENTO DE ANIMAIS QUE SE ENCONTREM SOLTOS NAS VIAS E NA FAIXA DE DOMÍNIO DAS VIAS DE CIRCULAÇÃO": {
        "id": "PG_8_6",
        "slug": "pg_8_6",
        "titulo": "8.6. Recolhimento de Animais que se Encontrem Soltos nas Vias e na Faixa de Domínio das Vias de Circulação",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "8.7. MEDIDAS ADMINISTRATIVAS INOMINADAS": {
        "id": "PG_8_7",
        "slug": "pg_8_7",
        "titulo": "8.7. Medidas Administrativas Inominadas",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
        "medidas": [
            MedidaAdministrativaEnum.RECOLHIMENTO_PLACAS,
            MedidaAdministrativaEnum.REMOCAO_MERCADORIA_MATERIAL,
        ],
    },
    "9. HABILITAÇÃO": {
        "id": "PG_9",
        "slug": "pg_9",
        "titulo": "9. Habilitação",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "9.1. CONDUTOR ORIUNDO DE PAÍS ESTRANGEIRO": {
        "id": "PG_9_1",
        "slug": "pg_9_1",
        "titulo": "9.1. Condutor Oriundo de País Estrangeiro",
        "tipo": TipoSecaoParteGeralEnum.TEMATICO,
    },
    "10. DISPOSIÇÕES FINAIS": {
        "id": "PG_10",
        "slug": "pg_10",
        "titulo": "10. Disposições Finais",
        "tipo": TipoSecaoParteGeralEnum.GLOBAL,
    },
    "11. FICHAS DE FISCALIZAÇÃO": {"descartar": True},
}


def processar_parte_geral(
    markdown_texto: str, fichas_enriquecidas: List[FichaEnriquecida]
) -> ParteGeralEnriquecida:
    """
    Processa o Markdown da Parte Geral e retorna o contrato `ParteGeralEnriquecida`.
    """
    blocos = _dividir_em_blocos_h2(markdown_texto)

    # 1 bloco descartado correspondente às páginas pré-textuais (capa, autoridades, sumário)
    secoes_descartadas = 1
    glossario: List[ItemGlossario] = []
    secoes: List[SecaoParteGeral] = []

    for titulo_h2, linhas_brutas in blocos:
        chave = titulo_h2.upper()
        spec = MAPA_SECOES_H2.get(chave)

        if spec is None or spec.get("descartar"):
            secoes_descartadas += 1
            continue

        paragrafos = _extrair_paragrafos(linhas_brutas)
        if not paragrafos:
            secoes_descartadas += 1
            continue

        tipo: TipoSecaoParteGeralEnum = spec["tipo"]

        # Extração estruturada do Glossário (Seção 2)
        if tipo == TipoSecaoParteGeralEnum.GLOSSARIO:
            for p in paragrafos:
                m_glos = REGEX_GLOSSARIO_LINHA.match(p)
                if m_glos:
                    glossario.append(
                        ItemGlossario(
                            sigla=m_glos.group(1).strip(),
                            significado=m_glos.group(2).strip(),
                        )
                    )

        # Caso especial: separar o bloco final de Abordagem / Combinação de Veículos de "Infrações Sucessivas"
        if spec["id"] == "PG_7_SUCESSIVAS":
            idx_split = next(
                (
                    i
                    for i, p in enumerate(paragrafos)
                    if p.startswith(MARCADOR_ABORDAGEM_SECAO_7)
                ),
                None,
            )
            if idx_split is not None:
                paragrafos_sucessivas = paragrafos[:idx_split]
                paragrafos_abordagem = paragrafos[idx_split:]

                secoes.append(
                    _construir_secao(
                        id_secao=spec["id"],
                        slug=spec["slug"],
                        titulo=spec["titulo"],
                        tipo=tipo,
                        paragrafos=paragrafos_sucessivas,
                        fichas=fichas_enriquecidas,
                    )
                )
                secoes.append(
                    _construir_secao(
                        id_secao="PG_7_ABORDAGEM",
                        slug="pg_7_abordagem",
                        titulo="7. Autuação — Regras de Abordagem e Combinação de Veículos",
                        tipo=TipoSecaoParteGeralEnum.GLOBAL,
                        paragrafos=paragrafos_abordagem,
                        fichas=fichas_enriquecidas,
                    )
                )
                continue

        secoes.append(
            _construir_secao(
                id_secao=spec["id"],
                slug=spec["slug"],
                titulo=spec["titulo"],
                tipo=tipo,
                paragrafos=paragrafos,
                fichas=fichas_enriquecidas,
                medidas=spec.get("medidas"),
                infratores=spec.get("infratores"),
            )
        )

    return ParteGeralEnriquecida(
        secoes_descartadas=secoes_descartadas,
        glossario=glossario,
        secoes=secoes,
    )
