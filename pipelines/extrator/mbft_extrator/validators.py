import re
from typing import List

def detectar_anomalia_cabecalho(meta: dict) -> List[str]:
    """Retorna uma lista de campos que parecem conter ruído ou vazamento visual."""
    anomalias = []
    
    inf = meta.get("infrator", "")
    # Se contiver letras isoladas ou símbolos suspeitos no infrator
    if re.search(r'\b(p|c|gp|º|°)\b', inf, re.IGNORECASE) or len(inf) > 50:
        anomalias.append("infrator")
        
    const = meta.get("constatacao_infracao", "")
    # Se o texto de constatação "esbarrou" nos títulos da linha de baixo
    if re.search(r'(quando|autuar|gp)\b', const, re.IGNORECASE):
        anomalias.append("constatacao_infracao")
        
    return anomalias
