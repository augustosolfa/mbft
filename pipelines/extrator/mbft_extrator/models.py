"""
Re-exportação de modelos canônicos a partir do pacote neutro mbft-core,
e definição de modelos intermediários da pipeline de extração (DTOs geométricos).
"""
from dataclasses import dataclass
from typing import List, Tuple, Any, Optional

from mbft_core.models import CampoNormativo, Ficha, FichaMapeada

@dataclass
class MetadadosCabecalho:
    tipificacao_resumida: Optional[str] = None
    codigo_enquadramento: str = ""
    amparo_legal: Optional[str] = None
    tipificacao_enquadramento: Optional[str] = None
    gravidade: Optional[str] = None
    penalidade: Optional[str] = None
    medida_administrativa: Optional[str] = None
    pode_configurar_crime_transito: Optional[str] = None
    infrator: Optional[str] = None
    competencia: Optional[str] = None
    competencia_alterada_lei_14599: bool = False
    pontuacao: Optional[str] = None
    constatacao_infracao: Optional[str] = None

@dataclass
class RetanguloTexto:
    x0: float
    y0: float
    x1: float
    y1: float
    texto: str
    id: int = 0

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def rect(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

@dataclass
class PaginaExtraida:
    largura: float
    altura: float
    retangulos: List[RetanguloTexto]
    linhas_vetoriais: List[Tuple[float, float, float, float]]

@dataclass
class ImagemExtraida:
    bounds: Tuple[float, float, float, float]
    x0: float
    y0: float
    x1: float
    y1: float
    yc: float
    xc: float
    rel_path: str
    width: float
    img_data: Any = None

__all__ = ["MetadadosCabecalho", "CampoNormativo", "Ficha", "FichaMapeada", "RetanguloTexto", "PaginaExtraida", "ImagemExtraida"]
