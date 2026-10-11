"""
Módulo de modelos canônicos e contratos do MBFT.
"""

from .extracao import CampoNormativo, Ficha, FichaMapeada
from .enriquecimento import (
    GravidadeEnum,
    CompetenciaEnum,
    CompetenciaFonteEnum,
    InfratorEnum,
    PenalidadeEnum,
    MedidaAdministrativaEnum,
    ConstatacaoInfracaoEnum,
    NaturezaRegraEnum,
    TipoSecaoParteGeralEnum,
    ReferenciaCTB,
    FichaEnriquecida,
    ItemGlossario,
    SecaoParteGeral,
    ParteGeralEnriquecida,
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
    "InfratorEnum",
    "PenalidadeEnum",
    "MedidaAdministrativaEnum",
    "ConstatacaoInfracaoEnum",
    "NaturezaRegraEnum",
    "TipoSecaoParteGeralEnum",
    "ReferenciaCTB",
    "FichaEnriquecida",
    "ItemGlossario",
    "SecaoParteGeral",
    "ParteGeralEnriquecida",
    "ChunkMetadados",
    "ChunkPayload",
]


