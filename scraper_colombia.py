"""
scraper_colombia.py — Scraper para chancehoy.com
=================================================
HTML confirmado:
  <a class="box-post" href="/sorteo?s=nombre-sorteo">
    <p class="box-post-title">Nombre Sorteo</p>
    <span class="score">4</span><span class="score">1</span>...  (4 digitos)
    <span class="score-quinta">3</span>  (serie, opcional, clase diferente)
  </a>
"""

from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import re
import logging

logger = logging.getLogger(__name__)

URL = "https://www.chancehoy.com/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

URL_ASTRO = "https://superastro.com.co/resultados-super-astro-sol-super-astro-luna.php"

LOTERIAS_NOCHE = {
    "astro luna", "caribeña noche", "sinuano noche", "motilon noche",
    "fantastica noche", "fantástica noche", "culona noche",
    "cafeterito noche", "chontico noche", "super chontico noche",
    "paisita noche", "dorado noche", "super astro luna",
}

EXCLUIR = {
    "pick 4", "pick 3", "pick 4 dia", "pick 4 día",
    "pick 4 noche", "pick 3 dia", "pick 3 día", "pick 3 noche",
    "pick4", "pick3",
}

ACRONIMOS = {
    "cafeterito noche":   "CFN",
    "cafeterito tarde":   "CF",
    "caribeña día":       "C",
    "caribeña dia":       "C",
    "caribeña noche":     "CN",
    "sinuano día":        "S",
    "sinuano dia":        "S",
    "sinuano noche":      "SN",
    "antioqueñita 1":     "AM",
    "antioqueñita dia":   "AM",
    "antioqueñita día":   "AM",
    "antioqueñita 2":     "AT",
    "antioqueñita tarde": "AT",
    "dorado mañana":      "DM",
    "dorado tarde":       "DT",
    "dorado noche":       "DN",
    "motilon tarde":      "MT",
    "motilon dia":        "MT",
    "motilon día":        "MT",
    "motilon noche":      "MTN",
    "paisita día":        "P",
    "paisita dia":        "P",
    "paisita noche":      "PN",
    "fantastica día":     "F",
    "fantastica dia":     "F",
    "fantástica dia":     "F",
    "fantástica día":     "F",
    "fantastica noche":   "FN",
    "fantástica noche":   "FN",
    "pijao de oro":       "PJ",
    "astro sol":          "AS",
    "super astro sol":    "AS",
    "astro luna":         "AL",
    "super astro luna":   "AL",
}

NORMALIZAR = {
    "Antioqueñita Dia":    "Antioqueñita 1",
    "Antioqueñita Día":    "Antioqueñita 1",
    "Antioqueñita Tarde":  "Antioqueñita 2",
    "Motilon Dia":         "Motilon Tarde",
    "Motilon Día":         "Motilon Tarde",
    "Fantástica Dia":      "Fantastica Día",
    "Fantástica Día":      "Fantastica Día",
    "Fantástica Noche":    "Fantastica Noche",
    "Super Astro Sol":     "Astro Sol",
    "Super Astro Luna":    "Astro Luna",
    "Saman De La Suerte":  "Saman",
    "Caribeña Dia":        "Caribeña Día",
    "Sinuano Dia":         "Sinuano Día",
    "Chontico Dia":        "Chontico Día",
    "Culona Dia":          "Culona Día",
    "Paisita Dia":         "Paisita Día",
}


def _es_noche(nombre: str) -> bool:
    return nombre.lower().strip() in LOTERIAS_NOCHE


def _generar_acronimo(nombre: str) -> str:
    clave = nombre.lower().strip()
    if clave in ACRONIMOS:
        return ACRONIMOS[clave]
    partes = clave.split()
    return "".join(p[0].upper() for p in partes
                   if p not in ("de", "la", "el", "los", "las", "del"))


def _obtener_signos_astro() -> dict:
    try:
        resp = requests.get(URL_ASTRO, headers=HEADERS, timeout=15,
                            impersonate="chrome110")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        tablas = soup.find_all("table")
        resultado = {}
        for i, tabla in enumerate(tablas):
            filas = tabla.find_all("tr")
            for fila in filas[1:2]:
                celdas = [td.get_text(strip=True) for td in fila.find_all("td")]
                if len(celdas) >= 4:
                    numero = celdas[0]
                    signo  = celdas[1]
                    fecha  = celdas[3]
                    if re.match(r"\d{4}", numero) and signo:
                        clave = "sol" if i == 0 else "luna"
                        resultado[clave] = {
                            "numero": numero,
                            "signo":  signo,
                            "fecha":  fecha,
                        }
        return resultado
    except Exception as e:
        logger.warning(f"No se pudo obtener signos astro: {e}")
        return {}


def obtener_sorteos_colombia() -> dict:
    hoy  = date.today()
    ayer = hoy - timedelta(days=1)

    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20,
                            impersonate="chrome110")
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Error chancehoy.com: {e}")
        return {"DIA": [], "NOCHE": [], "LOTERIAS": []}

    soup = BeautifulSoup(resp.text, "lxml")
    html = resp.text

    # Extraer SOLO la sección HOY del HTML
    # chancehoy.com muestra HOY y AYER en la misma página
    # Cortamos el HTML desde "resultados de hoy" hasta "resultados de ayer"
    html_lower = html.lower()
    pos_hoy  = html_lower.find("resultados de hoy")
    pos_ayer = html_lower.find("resultados de ayer")

    if pos_hoy >= 0 and pos_ayer > pos_hoy:
        html_hoy = html[pos_hoy:pos_ayer]
    elif pos_hoy >= 0:
        html_hoy = html[pos_hoy:]
    else:
        html_hoy = html

    soup_hoy = BeautifulSoup(html_hoy, "lxml")
    dia, noche, vistos = [], [], set()

    # Buscar solo en la sección HOY
    for a in soup_hoy.find_all("a", class_="box-post"):
        href = a.get("href", "")
        if "/sorteo" not in href:
            continue

        # Nombre del sorteo
        titulo = a.find("p", class_="box-post-title")
        if not titulo:
            continue
        nombre_raw = titulo.get_text(strip=True).title()

        # Excluir internacionales
        if nombre_raw.lower().strip() in EXCLUIR:
            continue
        if any(ex in nombre_raw.lower() for ex in ["pick 3", "pick 4"]):
            continue

        # Dígitos del número (spans con clase "score")
        scores = a.find_all("span", class_="score")
        digitos = [s.get_text(strip=True) for s in scores if s.get_text(strip=True).isdigit()]
        if len(digitos) < 4:
            continue
        numero = "".join(digitos[:4])

        # Serie (span con clase "score-quinta")
        quinta = a.find("span", class_="score-quinta")
        serie = quinta.get_text(strip=True) if quinta else None
        if serie and not serie.isdigit():
            serie = None

        # Normalizar nombre
        nombre = NORMALIZAR.get(nombre_raw, nombre_raw)
        es_noche = _es_noche(nombre)

        # Fecha: DÍA = hoy, NOCHE = ayer (se publican al día siguiente)
        fecha = ayer.isoformat() if es_noche else hoy.isoformat()

        # Deduplicar
        clave = f"{nombre}_{fecha}"
        if clave in vistos:
            continue
        vistos.add(clave)

        sorteo = {
            "nombre":   nombre,
            "acronimo": _generar_acronimo(nombre),
            "numero":   numero,
            "serie":    serie,
            "signo":    None,
            "fecha":    fecha,
        }
        (noche if es_noche else dia).append(sorteo)

    # Agregar signos zodiacales
    signos = _obtener_signos_astro()
    for sorteo in dia + noche:
        n = sorteo["nombre"].lower()
        if "astro sol" in n and "sol" in signos:
            sorteo["signo"] = signos["sol"]["signo"]
        elif "astro luna" in n and "luna" in signos:
            sorteo["signo"] = signos["luna"]["signo"]

    logger.info(f"chancehoy.com OK: DIA={len(dia)}, NOCHE={len(noche)}")
    return {"DIA": dia, "NOCHE": noche, "LOTERIAS": []}
