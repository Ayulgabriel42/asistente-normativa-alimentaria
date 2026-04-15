import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI
import fitz
import re

# =========================
# CONFIG INICIAL
# =========================

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")

st.set_page_config(page_title="Asistente Normativa Alimentaria", layout="wide")

if api_key:
    client = OpenAI(api_key=api_key)
else:
    st.error("Error de configuración interna")
    client = None

st.title("Asistente Normativa Alimentaria")
st.subheader("Consulta normativa con apoyo de IA")
st.caption("Basado en el Real Decreto 1021/2022")

pdf_path = "data/BOE-A-2022-21681-consolidado.pdf"


# =========================
# FUNCIONES PDF
# =========================

def extraer_texto_pdf(ruta_pdf):
    doc = fitz.open(ruta_pdf)
    texto_completo = ""

    for pagina in doc:
        texto_completo += pagina.get_text()

    return texto_completo, len(doc)


def limpiar_texto_normativo(texto):
    marcador = "CAPÍTULO I\nDisposiciones generales"
    inicio = texto.find(marcador)

    if inicio != -1:
        return texto[inicio:]

    inicio_alt = texto.find("CAPÍTULO I")
    if inicio_alt != -1:
        return texto[inicio_alt:]

    return texto


def separar_por_articulos(texto):
    patron = r"(Artículo\s+\d+\..*?)(?=Artículo\s+\d+\.|Disposición|$)"
    coincidencias = re.findall(patron, texto, re.DOTALL)
    return coincidencias


def limpiar_articulo(articulo):
    articulo = re.sub(r"\nBOLETÍN OFICIAL DEL ESTADO.*?(?=\n|$)", "", articulo)
    articulo = re.sub(r"\nLEGISLACIÓN CONSOLIDADA.*?(?=\n|$)", "", articulo)
    articulo = re.sub(r"\nPágina\s+\d+", "", articulo)
    articulo = re.sub(r"[ \t]+", " ", articulo)
    articulo = re.sub(r"\n{3,}", "\n\n", articulo)
    return articulo.strip()


def extraer_titulo_articulo(articulo_texto):
    primera_linea = articulo_texto.split("\n")[0].strip()
    return primera_linea


# =========================
# BÚSQUEDA
# =========================

def buscar_en_articulos(articulos, consulta):
    resultados = []
    consulta_limpia = consulta.lower().strip()

    for articulo in articulos:
        if consulta_limpia in articulo.lower():
            resultados.append({
                "titulo": extraer_titulo_articulo(articulo),
                "contenido": articulo
            })

    return resultados


def buscar_en_articulos_por_palabras(articulos, consulta):
    palabras = [p.lower() for p in re.findall(r"\w+", consulta) if len(p) > 2]
    resultados = []

    for articulo in articulos:
        contenido_lower = articulo.lower()
        puntaje = sum(1 for palabra in palabras if palabra in contenido_lower)

        if puntaje > 0:
            resultados.append({
                "titulo": extraer_titulo_articulo(articulo),
                "contenido": articulo,
                "puntaje": puntaje
            })

    resultados.sort(key=lambda x: x["puntaje"], reverse=True)
    return resultados


# =========================
# RESPUESTA BÁSICA
# =========================

def generar_respuesta_basica(consulta, resultados):
    if not resultados:
        return "No se encontraron artículos relacionados con la consulta dentro del PDF."

    consulta_lower = consulta.lower().strip()
    respuesta = f'Se encontraron artículos relacionados con la consulta "{consulta}".\n\n'

    if "carne picada" in consulta_lower:
        respuesta += "Según el Artículo 4, la carne picada debe mantenerse a una temperatura igual o inferior a 2 °C.\n\n"
        respuesta += "Además, el Artículo 7 establece requisitos específicos para las carnes frescas, carne picada, preparados de carne y productos cárnicos."
        return respuesta

    if "huevo" in consulta_lower or "huevos" in consulta_lower:
        respuesta += (
            "Según el Artículo 9, el huevo crudo puede utilizarse si el alimento recibe un tratamiento térmico suficiente. "
            "Si no recibe ese tratamiento, debe sustituirse por ovoproductos autorizados. "
            "Además, los alimentos elaborados deben conservarse a ≤ 8 °C y consumirse dentro de 24 horas."
        )
        return respuesta

    if "anisakis" in consulta_lower:
        respuesta += (
            "Según el Artículo 8, los productos de la pesca destinados a consumirse crudos deben congelarse "
            "a -20 °C durante al menos 24 horas o a -35 °C durante al menos 15 horas para prevenir anisakis."
        )
        return respuesta

    if "appcc" in consulta_lower:
        respuesta += (
            "Según el Artículo 20, los establecimientos deben aplicar un sistema basado en los principios del APPCC "
            "y contar con una persona responsable de su implementación."
        )
        return respuesta

    if "recongel" in consulta_lower:
        respuesta += (
            "Según el Artículo 5, no se pueden recongelar alimentos, salvo que hayan sufrido una transformación posterior."
        )
        return respuesta

    principal = resultados[0]
    respuesta += f'El artículo principal identificado es: {principal["titulo"]}\n\n'
    respuesta += "Se recomienda revisar el contenido completo para obtener el detalle exacto."

    return respuesta


# =========================
# RESPUESTA CON IA
# =========================

def generar_respuesta_con_ia(consulta, resultados):
    if not client:
        return "La API Key no está disponible. No se puede generar respuesta con IA."

    if not resultados:
        return "No se encontraron artículos relevantes en el PDF para responder esa consulta."

    contexto = "\n\n".join(
        [f"{r['titulo']}\n{r['contenido']}" for r in resultados[:3]]
    )

    prompt = f"""
Sos un asistente experto en normativa alimentaria y seguridad alimentaria.

Respondé la consulta del usuario basándote únicamente en el contexto normativo proporcionado.

Consulta del usuario:
{consulta}

Contexto normativo:
{contexto}

Reglas obligatorias:
- Respondé solo con base en el contexto.
- No inventes información.
- Si el contexto no alcanza para responder con certeza, decilo claramente.
- Citá el artículo correspondiente cuando sea posible.
- Usá un tono profesional, claro y útil.
- Priorizá una respuesta breve pero completa.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Sos un experto en normativa alimentaria que responde únicamente con base documental."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"Error al generar respuesta con IA: {e}"


# =========================
# PROCESAMIENTO DEL PDF
# =========================

try:
    texto, total_paginas = extraer_texto_pdf(pdf_path)
    texto_limpio = limpiar_texto_normativo(texto)
    articulos_crudos = separar_por_articulos(texto_limpio)
    articulos = [limpiar_articulo(a) for a in articulos_crudos if len(a.strip()) > 50]

except Exception as e:
    st.error(f"Error al procesar el PDF: {e}")
    articulos = []

st.divider()

# =========================
# INTERFAZ
# =========================

modo_respuesta = st.radio(
    "Modo de respuesta",
    ["IA", "Básica"],
    horizontal=True
)

consulta = st.text_input(
    "Escribí una consulta (ej: ¿A qué temperatura debe conservarse la carne picada?)"
)

if consulta and articulos:
    resultados = buscar_en_articulos(articulos, consulta)

    if not resultados:
        resultados = buscar_en_articulos_por_palabras(articulos, consulta)

    if modo_respuesta == "IA":
        respuesta = generar_respuesta_con_ia(consulta, resultados)
    else:
        respuesta = generar_respuesta_basica(consulta, resultados)

    st.subheader("Respuesta")
    st.info(respuesta)

    st.write(f"Resultados encontrados: {len(resultados)}")

    if resultados:
        st.subheader("Artículos relacionados")
        for resultado in resultados[:5]:
            with st.expander(resultado["titulo"]):
                st.write(resultado["contenido"])
    else:
        st.warning("No se encontraron coincidencias.")