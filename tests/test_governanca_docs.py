"""
Testes automatizados das invariantes de Governança de Documentação (§5 do GEMINI.md).
"""

from dataclasses import dataclass
import re
import tomllib
import unittest
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]

PADRAO_NOME_ARQUIVO_PMS = re.compile(r"^PMS-(\d{3}) - .+\.md$")
TITULO_ANEXO_A = "Anexo A — Mapa de Seções"
TITULO_ANEXO_B = "Anexo B — Chaves Canônicas do Frontmatter"


@dataclass(frozen=True)
class ContratoPMS000:
    """Especificação canônica extraída dos Anexos A e B do PMS-000."""

    caminho_relativo: Path
    regras_frontmatter: dict[str, re.Pattern[str]]
    secoes_canonicas: list[str]


@dataclass(frozen=True)
class DocumentoPMSParseado:
    """Representação estrutural extraída de um arquivo docs/PMS-*.md."""

    caminho_relativo: Path
    codigo_arquivo: str
    eh_template: bool
    frontmatter: dict[str, str]
    num_linha_h1: int
    linha_h1: str
    secoes_numeradas: list[str]


def extrair_secao_h2(linhas: list[str], titulo_h2: str, rel: Path) -> list[str]:
    """Recorta as linhas abaixo de um cabeçalho H2 exato até o próximo H2 ou fim do arquivo."""
    alvo = f"## {titulo_h2}"
    idx_inicio = next((i for i, l in enumerate(linhas) if l.strip() == alvo), None)
    if idx_inicio is None:
        raise ValueError(f"'{rel}': cabeçalho '{alvo}' não encontrado.")

    bloco: list[str] = []
    for linha in linhas[idx_inicio + 1 :]:
        if re.match(r"^##\s+", linha):
            break
        bloco.append(linha.strip())
    return bloco


def extrair_linhas_tabela_markdown(
    bloco: list[str], rel: Path, contexto: str
) -> list[list[str]]:
    """Extrai as linhas de dados (pós-separador) de uma tabela Markdown em um bloco delimitado."""
    apos_separador = False
    linhas_dados: list[list[str]] = []
    for linha in bloco:
        if not linha.startswith("|"):
            if apos_separador and linhas_dados:
                break
            continue
        if re.match(r"^\|[\s:\-|]+\|$", linha):
            apos_separador = True
            continue
        if apos_separador:
            celulas = [
                c.strip().replace(r"\|", "|")
                for c in re.split(r"(?<!\\)\|", linha.strip("|"))
            ]
            if celulas and celulas[0]:
                linhas_dados.append(celulas)

    if not linhas_dados:
        raise ValueError(f"'{rel}': nenhuma linha de tabela encontrada em '{contexto}'.")
    chaves_col1 = [l[0] for l in linhas_dados]
    if len(chaves_col1) != len(set(chaves_col1)):
        raise ValueError(f"'{rel}': chaves duplicadas na tabela de '{contexto}': {chaves_col1}.")
    return linhas_dados


def carregar_contrato_pms000(docs_dir: Path) -> ContratoPMS000:
    """Localiza o PMS-000 e carrega as especificações declaradas nos Anexos A e B."""
    candidatos = sorted(docs_dir.glob("PMS-000*.md"))
    if len(candidatos) != 1:
        raise ValueError(
            f"Esperado exatamente 1 'docs/PMS-000*.md' (encontrados: {[p.name for p in candidatos]})."
        )
    pms000_path = candidatos[0]
    rel = pms000_path.relative_to(RAIZ_REPO)
    linhas = pms000_path.read_text(encoding="utf-8").splitlines()

    tabela_a = extrair_linhas_tabela_markdown(
        extrair_secao_h2(linhas, TITULO_ANEXO_A, rel), rel, TITULO_ANEXO_A
    )
    secoes_canonicas = [linha[0] for linha in tabela_a]

    tabela_b = extrair_linhas_tabela_markdown(
        extrair_secao_h2(linhas, TITULO_ANEXO_B, rel), rel, TITULO_ANEXO_B
    )
    regras_frontmatter: dict[str, re.Pattern[str]] = {}
    for linha in tabela_b:
        if len(linha) < 2 or not linha[1].startswith("`") or not linha[1].endswith("`"):
            raise ValueError(
                f"'{rel}': a 2ª coluna de '{TITULO_ANEXO_B}' deve conter regex entre crases para '{linha[0]}'."
            )
        regras_frontmatter[linha[0]] = re.compile(linha[1][1:-1])

    return ContratoPMS000(
        caminho_relativo=rel,
        regras_frontmatter=regras_frontmatter,
        secoes_canonicas=secoes_canonicas,
    )


def parsear_documento_pms(
    nome_arquivo: str, texto: str, rel: Path
) -> DocumentoPMSParseado:
    """Analisa estruturalmente o nome, frontmatter, H1 e seções H2 numeradas de um PMS."""
    m_nome = PADRAO_NOME_ARQUIVO_PMS.match(nome_arquivo)
    if not m_nome:
        raise ValueError(f"'{rel}': nome fora do padrão 'PMS-NNN - <Título>.md'.")
    codigo_arquivo = m_nome.group(1)

    linhas = texto.splitlines()
    if not linhas or linhas[0] != "---":
        primeiro = linhas[0] if linhas else "<arquivo vazio>"
        raise ValueError(
            f"'{rel}:1': documento deve começar com '---' e sem BOM UTF-8 (encontrado: {primeiro!r})."
        )

    idx_fim = next((i for i in range(1, len(linhas)) if linhas[i] == "---"), None)
    if idx_fim is None:
        raise ValueError(
            f"'{rel}:1': frontmatter aberto na linha 1 não possui delimitador '---' de fechamento."
        )

    frontmatter: dict[str, str] = {}
    for idx in range(1, idx_fim):
        chave, sep, valor = linhas[idx].partition(":")
        chave, valor = chave.strip(), valor.strip()
        if not sep or not chave or not valor:
            raise ValueError(
                f"'{rel}:{idx + 1}': linha de frontmatter inválida (esperado 'Chave: valor'): {linhas[idx]!r}."
            )
        if chave in frontmatter:
            raise ValueError(f"'{rel}:{idx + 1}': chave de frontmatter duplicada '{chave}'.")
        frontmatter[chave] = valor

    h1_par = next(
        ((i + 1, linhas[i]) for i in range(idx_fim + 1, len(linhas)) if linhas[i].strip()),
        None,
    )
    if h1_par is None:
        raise ValueError(f"'{rel}:{idx_fim + 1}': documento sem conteúdo após o frontmatter.")

    secoes = [
        m.group(1)
        for l in linhas[idx_fim + 1 :]
        if (m := re.match(r"^## (\d+\. .+)$", l.strip()))
    ]
    return DocumentoPMSParseado(
        caminho_relativo=rel,
        codigo_arquivo=codigo_arquivo,
        eh_template=(codigo_arquivo == "000"),
        frontmatter=frontmatter,
        num_linha_h1=h1_par[0],
        linha_h1=h1_par[1],
        secoes_numeradas=secoes,
    )


def listar_pacotes_workspace(raiz: Path) -> list[Path]:
    """Resolve os diretórios de pacotes declarados em [tool.uv.workspace].members."""
    with open(raiz / "pyproject.toml", "rb") as f:
        membros = (
            tomllib.load(f).get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
        )
    if not membros:
        raise ValueError("'[tool.uv.workspace].members' está vazio em pyproject.toml.")
    pacotes = [
        subdir
        for padrao in membros
        for subdir in sorted(raiz.glob(padrao))
        if subdir.is_dir() and (subdir / "pyproject.toml").is_file()
    ]
    if not pacotes:
        raise ValueError(f"Nenhum pacote encontrado para members={membros!r}.")
    return list(dict.fromkeys(pacotes))


class TestParsersGovernanca(unittest.TestCase):
    """Testes unitários das funções puras de parsing de governança."""

    def test_extrair_secao_h2_respeita_fronteira_e_cabecalho_exato(self):
        linhas = ["## Anexo A", "ignorado", "## Anexo A — Mapa de Seções", "| A |", "## Anexo B", "| B |"]
        bloco = extrair_secao_h2(linhas, TITULO_ANEXO_A, Path("PMS-000.md"))
        self.assertEqual(bloco, ["| A |"])

    def test_parsear_documento_pms_rejeita_chave_duplicada_e_falta_de_fechamento(self):
        with self.assertRaisesRegex(ValueError, "duplicada 'PMS'"):
            parsear_documento_pms("PMS-001 - T.md", "---\nPMS: 001\nPMS: 002\n---\n# H1", Path("p.md"))
        with self.assertRaisesRegex(ValueError, "fechamento"):
            parsear_documento_pms("PMS-001 - T.md", "---\nPMS: 001\n# H1", Path("p.md"))


class TestGovernancaDocumentacao(unittest.TestCase):
    """Valida as regras estruturais de governança documental do monorepo."""

    pacotes: list[Path]
    contrato: ContratoPMS000
    arquivos_pms: list[Path]

    @classmethod
    def setUpClass(cls):
        cls.pacotes = listar_pacotes_workspace(RAIZ_REPO)
        docs_dir = RAIZ_REPO / "docs"
        cls.contrato = carregar_contrato_pms000(docs_dir)
        cls.arquivos_pms = sorted(docs_dir.glob("PMS-*.md"))

    def _obter_doc_pms(self, pms_path: Path) -> DocumentoPMSParseado:
        rel = pms_path.relative_to(RAIZ_REPO)
        return parsear_documento_pms(pms_path.name, pms_path.read_text(encoding="utf-8"), rel)

    def _listar_documentos_markdown_governanca(self) -> list[Path]:
        candidatos = (
            set(RAIZ_REPO.glob("*.md"))
            | set((RAIZ_REPO / "docs").rglob("*.md"))
            | set((RAIZ_REPO / ".agents" / "rules").glob("*.md"))
        )
        candidatos.update(p / "README.md" for p in self.pacotes if (p / "README.md").is_file())
        return sorted(candidatos, key=lambda p: str(p.relative_to(RAIZ_REPO)))

    def test_documentos_markdown_nao_possuem_bom_utf8(self):
        for md_path in self._listar_documentos_markdown_governanca():
            rel = md_path.relative_to(RAIZ_REPO)
            with self.subTest(arquivo=str(rel)):
                self.assertFalse(
                    md_path.read_bytes().startswith(b"\xef\xbb\xbf"),
                    f"'{rel}' foi gravado com BOM UTF-8.",
                )

    def test_documentos_markdown_nao_possuem_links_absolutos_locais(self):
        padrao_absoluto = re.compile(r"\]\((?:file:///|[a-zA-Z]:[\\/])", re.IGNORECASE)

        for md_path in self._listar_documentos_markdown_governanca():
            rel = md_path.relative_to(RAIZ_REPO)
            texto = md_path.read_text(encoding="utf-8")
            for num_linha, linha in enumerate(texto.splitlines(), start=1):
                with self.subTest(arquivo=f"{rel}:{num_linha}"):
                    self.assertNotRegex(
                        linha,
                        padrao_absoluto,
                        f"'{rel}:{num_linha}': link absoluto local proibido (use caminhos relativos): {linha.strip()!r}",
                    )

    def test_regras_condicionais_antigravity_possuem_frontmatter_valido(self):
        regras = sorted((RAIZ_REPO / ".agents" / "rules").glob("*.md"))
        self.assertTrue(regras, "Nenhuma regra encontrada em '.agents/rules/*.md'.")
        triggers_validos = {"always_on", "glob", "model_decision", "manual"}

        for rule_path in regras:
            rel = rule_path.relative_to(RAIZ_REPO)
            with self.subTest(regra=str(rel)):
                linhas = rule_path.read_text(encoding="utf-8").splitlines()
                self.assertTrue(
                    linhas and linhas[0] == "---",
                    f"'{rel}:1' deve iniciar com frontmatter YAML '---'.",
                )
                idx_fim = next((i for i in range(1, len(linhas)) if linhas[i] == "---"), None)
                self.assertIsNotNone(idx_fim, f"'{rel}' não possui fechamento '---' do frontmatter.")

                fm: dict[str, str] = {}
                for idx in range(1, idx_fim):
                    chave, sep, valor = linhas[idx].partition(":")
                    self.assertTrue(sep, f"'{rel}:{idx + 1}' linha de frontmatter inválida.")
                    fm[chave.strip()] = valor.strip()

                self.assertIn(fm.get("trigger"), triggers_validos, f"'{rel}': trigger inválido.")
                self.assertTrue(fm.get("description"), f"'{rel}': description obrigatória.")
                if fm.get("trigger") == "glob":
                    globs_raw = fm.get("globs", "")
                    self.assertTrue(globs_raw, f"'{rel}': campo 'globs' obrigatório para trigger=glob.")
                    self.assertFalse(
                        globs_raw.startswith("[") or globs_raw.endswith("]"),
                        f"'{rel}': no Antigravity, 'globs' deve ser string separada por vírgulas entre aspas, não lista YAML.",
                    )

    def test_todos_os_pacotes_possuem_readme_declarado_e_existente(self):
        for pkg_dir in self.pacotes:
            rel_pkg = pkg_dir.relative_to(RAIZ_REPO)
            with self.subTest(pacote=str(rel_pkg)):
                with open(pkg_dir / "pyproject.toml", "rb") as f:
                    dados = tomllib.load(f)
                self.assertEqual(
                    dados.get("project", {}).get("readme"),
                    "README.md",
                    f"'{rel_pkg / 'pyproject.toml'}' deve declarar readme = 'README.md'.",
                )
                self.assertTrue((pkg_dir / "README.md").is_file(), f"'{rel_pkg / 'README.md'}' ausente.")

    def test_todos_os_readmes_de_pacote_referenciam_pms_no_cabecalho(self):
        for pkg_dir in self.pacotes:
            readme_path = pkg_dir / "README.md"
            rel = readme_path.relative_to(RAIZ_REPO)
            with self.subTest(readme=str(rel)):
                topo = "\n".join(readme_path.read_text(encoding="utf-8").splitlines()[:15])
                self.assertRegex(topo, r"\bPMS-\d{3}\b", f"'{rel}:1-15' não referencia PMS-NNN.")

    def test_integridade_referencial_de_documentos_pms(self):
        mapa_arquivos: dict[str, Path] = {}
        for pms_path in self.arquivos_pms:
            rel = pms_path.relative_to(RAIZ_REPO)
            with self.subTest(arquivo_pms=str(rel)):
                doc = self._obter_doc_pms(pms_path)
                pms_id = f"PMS-{doc.codigo_arquivo}"
                self.assertNotIn(pms_id, mapa_arquivos, f"'{pms_id}' duplicado em '{rel}'.")
                mapa_arquivos[pms_id] = rel

        fontes = (
            [RAIZ_REPO / "GEMINI.md", RAIZ_REPO / "README.md"]
            + sorted((RAIZ_REPO / ".agents" / "rules").glob("*.md"))
            + [p / "README.md" for p in self.pacotes if (p / "README.md").is_file()]
        )
        citados: set[str] = set()
        for fonte in fontes:
            rel_f = fonte.relative_to(RAIZ_REPO)
            for idx, linha in enumerate(fonte.read_text(encoding="utf-8").splitlines(), start=1):
                for pms_id in re.findall(r"\b(PMS-\d{3})\b", linha):
                    citados.add(pms_id)
                    with self.subTest(citacao=f"{rel_f}:{idx}:{pms_id}"):
                        self.assertIn(pms_id, mapa_arquivos, f"'{rel_f}:{idx}' cita '{pms_id}' inexistente.")

        for pms_id, rel_pms in sorted(mapa_arquivos.items()):
            with self.subTest(pms_orfao=str(rel_pms)):
                self.assertIn(pms_id, citados, f"'{rel_pms}' ({pms_id}) está órfão de citação.")

    def test_documentos_pms_seguem_frontmatter_declarado_no_pms000(self):
        regras = self.contrato.regras_frontmatter
        chaves_obrigatorias = set(regras.keys())

        for pms_path in self.arquivos_pms:
            rel = pms_path.relative_to(RAIZ_REPO)
            with self.subTest(pms=str(rel)):
                doc = self._obter_doc_pms(pms_path)
                if doc.eh_template:
                    self.assertEqual(
                        set(doc.frontmatter.keys()),
                        chaves_obrigatorias,
                        f"'{rel}' deve ter exatamente as chaves do Anexo B.",
                    )
                    self.assertEqual(doc.frontmatter.get("PMS"), "NNN")
                else:
                    ausentes = chaves_obrigatorias - set(doc.frontmatter.keys())
                    self.assertFalse(ausentes, f"'{rel}': chaves ausentes no frontmatter: {ausentes}.")
                    self.assertEqual(
                        doc.frontmatter["PMS"],
                        doc.codigo_arquivo,
                        f"'{rel}': 'PMS: {doc.frontmatter['PMS']}' diverge do arquivo 'PMS-{doc.codigo_arquivo}'.",
                    )
                    for chave, padrao in regras.items():
                        valor = doc.frontmatter[chave]
                        self.assertRegex(
                            valor,
                            padrao,
                            f"'{rel}': campo '{chave}: {valor}' viola o padrão '{padrao.pattern}' do Anexo B.",
                        )

    def test_documentos_pms_possuem_h1_e_secoes_declaradas_no_pms000(self):
        for pms_path in self.arquivos_pms:
            rel = pms_path.relative_to(RAIZ_REPO)
            with self.subTest(pms=str(rel)):
                doc = self._obter_doc_pms(pms_path)
                id_esp = "NNN" if doc.eh_template else doc.codigo_arquivo
                self.assertRegex(
                    doc.linha_h1,
                    rf"^# PMS-{id_esp}: .+",
                    f"'{rel}:{doc.num_linha_h1}': H1 inválido: {doc.linha_h1!r}.",
                )
                self.assertEqual(
                    doc.secoes_numeradas,
                    self.contrato.secoes_canonicas,
                    f"'{rel}': seções numeradas divergem do Anexo A do PMS-000.",
                )


if __name__ == "__main__":
    unittest.main()
