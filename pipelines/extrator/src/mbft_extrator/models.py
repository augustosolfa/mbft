"""
Re-exportação de modelos canônicos a partir do pacote neutro mbft-core.
Mantido para retrocompatibilidade com imports internos e externos de mbft_extrator.
"""

from mbft_core.models import CampoNormativo, Ficha, FichaMapeada

__all__ = ["CampoNormativo", "Ficha", "FichaMapeada"]
