"""
MBFT Core - Contratos de dados, guardrails e constantes compartilhadas do monorepo MBFT.
"""

from .models import (
    CampoNormativo,
    Ficha,
    FichaMapeada,
    GravidadeEnum,
    CompetenciaEnum,
    CompetenciaFonteEnum,
    ReferenciaCTB,
    FichaEnriquecida,
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
