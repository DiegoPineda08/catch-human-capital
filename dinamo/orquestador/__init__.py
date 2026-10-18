"""Orquestador con IA: entiende la intención, planea con herramientas autorizadas y redacta con citas."""
from .herramientas import HERRAMIENTAS, Material, ejecutar
from .orquestador import completar_desde_navegador, procesar
from .planificador import PlanOrquestador, corregir, planificar, por_reglas
from .sintesis import construir_mensajes, sin_llm, verificar

__all__ = ["procesar", "completar_desde_navegador", "planificar", "por_reglas", "corregir", "PlanOrquestador",
           "HERRAMIENTAS", "Material", "ejecutar", "construir_mensajes", "sin_llm", "verificar"]
