"""
Presentation Engine v0: DINAMO en el navegador.

Ejecutar desde la carpeta del proyecto (con el entorno activado):
    streamlit run app/streamlit_app.py
Se abre solo en http://localhost:8501

Cómo funciona Streamlit: cada vez que el usuario hace algo (escribe, pulsa un botón), el script
se ejecuta OTRA VEZ de arriba abajo. Lo que debe sobrevivir entre ejecuciones (el Brain, el
historial) se guarda en st.session_state.

Esta versión sólo consume el contrato `Respuesta`: nunca toca tablas ni DataFrames del Data Engine.
Mejoras pendientes (Gabriela): subir archivos, perfil del usuario, gráficos, modo historia.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))   # para poder importar dinamo/

import pandas as pd
import streamlit as st

from dinamo.llm import formatear_valor
from dinamo.sistema import construir_sistema

st.set_page_config(page_title="DINAMO_ANALITICS", layout="wide")
st.title("DINAMO_ANALITICS")
st.caption("Pregúntale a tus datos. Cada cifra viene con su evidencia.")

if "brain" not in st.session_state:                    # sólo la primera vez: arma el sistema
    st.session_state.brain = construir_sistema()
    st.session_state.historial = [("", st.session_state.brain.bienvenida())]
    st.session_state.pendiente = None
brain = st.session_state.brain

with st.sidebar:
    st.header("Fuentes cargadas")
    for t in brain.biblioteca.resumen():
        st.markdown(f"**{t['tabla']}**  \n{t['origen']} · {t['filas']} filas · {t['indicadores']} indicadores")
    for d in brain.rac.documentos():
        st.markdown(f"**{d}**  \ntexto")


def mostrar(resp, clave: str) -> None:
    """Dibuja una respuesta: texto, evidencia, advertencias y botones de sugerencias."""
    st.markdown(resp.texto)
    if resp.evidencias:
        with st.expander(f"Evidencia ({len(resp.evidencias)} datos)"):
            st.dataframe(pd.DataFrame([{"id": e.id, "dato": e.descripcion, "valor": formatear_valor(e), "n": e.n}
                                       for e in resp.evidencias]), hide_index=True)
    for aviso in resp.advertencias:
        st.warning(aviso)
    for i, sugerencia in enumerate(resp.sugerencias):
        if st.button(sugerencia, key=f"sug-{clave}-{i}"):
            st.session_state.pendiente = sugerencia


for i, (pregunta, resp) in enumerate(st.session_state.historial):
    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
    with st.chat_message("assistant"):
        mostrar(resp, str(i))

pregunta = st.chat_input("Escribe tu pregunta (o pulsa una sugerencia)") or st.session_state.pendiente
if pregunta:
    st.session_state.pendiente = None
    with st.spinner("Analizando..."):
        resp = brain.responder(pregunta)
    st.session_state.historial.append((pregunta, resp))
    st.rerun()                                          # vuelve a dibujar con la respuesta nueva
