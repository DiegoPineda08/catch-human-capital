import unicodedata

def _texto_plano(texto: str) -> str:
    """Normaliza el texto removiendo tildes y pasando a minúsculas."""
    if not texto:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()

class Brain:
    def __init__(self, datos):
        # Obtenemos los periodos asegurándonos de que sea una lista de tuplas (respetando regla 3: no es DataFrame)
        self.periodos = datos.periodos() 
        # ... resto de tus inicializaciones (kpis, empresa, etc.)

    def detectar_periodo(t: str, periodos: list[tuple[int, str]]) -> int | None:
        if "ultimo bimestre" in t or "ultimo periodo" in t:
            return max(orden for orden, _ in periodos)
    
        for orden, etiqueta in periodos:
            # Limpiamos y normalizamos el texto plano de la etiqueta (ej. "julio agosto 2025")
            if _texto_plano(etiqueta).strip() in t:  
                return orden
            
        return None