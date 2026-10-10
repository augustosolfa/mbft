"""
Configurações centralizadas de layout geométrico e metadados do documento MBFT.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class LayoutConfig:
    """Configurações geométricas e tolerâncias de layout para páginas do MBFT."""
    
    # Tolerâncias e limites verticais (Y)
    y_top_limit_default: float = 40.0
    y_min_image: float = 30.0
    min_img_size: float = 25.0
    y_limit_header: float = 350.0
    y_top_primeira_pagina: float = 715.0

    # Margens horizontais (X)
    margem_esquerda_titulo: float = 60.0
    margem_esquerda_secao_numerada: float = 80.0
    x_left_col_max: float = 290.0
    x_right_col_min: float = 280.0
    x_text_left_max: float = 300.0

    # Proporções de corte de colunas (fallback de limites divisórios verticais)
    col_bounds_pct: List[float] = field(default_factory=lambda: [0.28, 0.50, 0.73])


# Instância padrão imutável de geometria de layout
DEFAULT_LAYOUT_CONFIG = LayoutConfig()

# Metadados e limites estruturais de paginação da edição atual do MBFT
PAGINA_INICIO_PARTE_GERAL: int = 1
PAGINA_FIM_PARTE_GERAL: int = 31
PAGINA_INICIO_FICHAS: int = 32
