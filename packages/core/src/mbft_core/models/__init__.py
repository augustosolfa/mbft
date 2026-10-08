"""
Módulo de modelos canônicos e contratos do MBFT.
"""

from .extracao import CampoNormativo, Ficha, FichaMapeada
from .enriquecimento import (
    GravidadeEnum,
    CompetenciaEnum,
    CompetenciaFonteEnum,
    ReferenciaCTB,
    FichaEnriquecida,
)
from .indexacao import (
    ChunkMetadados,
    ChunkPayload,
)

__all__ = [
    "CampoNormativo",
    "Ficha",
    "FichaMapeada",
    "GravidadeEnum",
    "CompetenciaEnum",
    "CompetenciaFonteEnum",
    "ReferenciaCTB",
    "FichaEnriquecida",
    "ChunkMetadados",
    "ChunkPayload",
]
