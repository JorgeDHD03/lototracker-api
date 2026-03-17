"""
scraper_colombia.py — Scraper para chancehoy.com
=================================================
Fuente: https://www.chancehoy.com/
No bloquea servidores en la nube.
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

LOTERIAS_NOCHE = {
    "astro luna", "caribeña noche", "sinuano noche", "motilon noche",
    "fantastica noche", "fantástica noche", "culona noche",
    "cafeterito noche", "chontico noche", "super chontico noche",
    "paisita noche", "dorado noche", "super astro luna",
}

EXCLUIR = {"pick 4", "pick 3", "pick 4 dia", "pick 4 día",
           "pick 4 noche", "pick 3 dia", "pick 3 día", "pick 3 noche"}

ACRONIMOS = {
    "cafeterito noche":   "CFN",
    "cafeterito tarde":   "CF",
    "caribeña día":       "C",
    "caribeña noche":     "CN",
    "sinuano día":        "S",
    "sinuano noche":      "SN",
    "antioqueñita 1":     "AM",
    "antioqueñita 2":     "AT",
    "dorado mañana":      "DM",
    "dorado tarde":       "DT",
    "dorado noche":       "DN",
    "motilon tarde":      "MT",
    "motilon noche":      "MTN",
    "paisita día":        "P",
    "paisita noche":      "PN",
    "fantastica día":     "F",
    "fantastica noche":   "FN",
    "pijao de oro":       "PJ",
    "astro sol":          "AS",
    "astro luna":         "AL",
}

NORMALIZAR = {
    "Antioqueñita Dia":   "Antioqueñita 1",
    "Antioqueñita Día":   "Antioqueñita 1",
    "Antioqueñita Tarde": "Antioqueñita 2",
    "Motilon Dia":        "Motilon Tarde",
    "Motilon Día":        "Motilon Tarde",
    "Fantástica Dia":     "Fantastica Día",
    "Fantástica Día":     "Fantastica Día",
    "Fantástica Noche":   "Fantastica Noche",
    "Super Astro Sol":    "Astro Sol",
    "Super Astro Luna":   "Astro Luna",
    "Saman De La Suerte": "Saman",
    "Caribeña Dia":       "Caribeña Día",
    "Sinuano Dia":        "Sinuano Día",
    "Chontico Dia":       "Chontico Día",
    "Culona Dia":         "Culona Día",
    "Paisita Dia":        "Paisita Día",
}


URL_ASTRO = "https://superastro.com.co/resultados-super-astro-sol-super-astro-luna.php"

def _obtener_signos_astro() -> dict:
    """
    Scrape superastro.com.co para obtener numero+signo de Sol y Luna.
    Retorna: {"sol": {"numero": "5242", "signo": "Acuario", "fecha": "2026-03-16"},
              "luna": {...}}
    """
    try:
        resp = requests.get(URL_ASTRO, headers=HEADERS, timeout=15, impersonate="chrome110")
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        
        # Tabla con columnas: NÚMERO | SIGNO | SORTEO | FECHA
        tablas = soup.find_all("table")
        resultado = {}
        
        for i, tabla in enumerate(tablas):
            filas = tabla.find_all("tr")
            for fila in filas[1:2]:  # Solo primera fila de datos
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



def _es_noche(nombre: str) -> bool:
    return nombre.lower().strip() in LOTERIAS_NOCHE


def _generar_acronimo(nombre: str) -> str:
    clave = nombre.lower().strip()
    if clave in ACRONIMOS:
        return ACRONIMOS[clave]
    partes = clave.split()
    return "".join(p[0].upper() for p in partes
                   if p not in ("de", "la", "el", "los", "las", "del"))


def obtener_sorteos_colombia() -> dict:
    hoy  = date.today()
    ayer = hoy - timedelta(days=1)

    try:
        resp = requests.get(URL, headers=HEADERS, timeout=20, impersonate="chrome110")
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Error chancehoy.com: {e}")
        return {"DIA": [], "NOCHE": [], "LOTERIAS": []}

    soup = BeautifulSoup(resp.text, "lxml")
    html = resp.text

    pos_hoy  = html.lower().find("resultados de hoy")
    pos_ayer = html.lower().find("resultados de ayer")

    dia, noche, vistos = [], [], set()

    for a in soup.find_all("a", href=re.compile(r"/sorteo")):
        texto = a.get_text(separator="\n").strip()
        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        if len(lineas) < 2:
            continue

        nombre_raw = lineas[0].title()
        resto = lineas[-1]
        m = re.match(r'^(\d{4})\s*(\d)?$', resto)
        if not m:
            continue

        numero = m.group(1)
        serie  = m.group(2)
        nombre = NORMALIZAR.get(nombre_raw, nombre_raw)

        if nombre.lower().strip() in EXCLUIR:
            continue
        if any(ex in nombre.lower() for ex in ["pick 3", "pick 4"]):
            continue

        es_noche = _es_noche(nombre)
        href = a.get("href", "")
        pos = html.find(href)

        if pos_ayer > 0 and pos > pos_ayer:
            fecha = ayer.isoformat()
        else:
            fecha = ayer.isoformat() if es_noche else hoy.isoformat()

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

    # Agregar signos zodiacales a Astro Sol y Astro Luna
    signos = _obtener_signos_astro()
    for sorteo in dia + noche:
        n = sorteo["nombre"].lower()
        if "astro sol" in n and "sol" in signos:
            sorteo["signo"] = signos["sol"]["signo"]
        elif "astro luna" in n and "luna" in signos:
            sorteo["signo"] = signos["luna"]["signo"]

    logger.info(f"chancehoy.com OK: DIA={len(dia)}, NOCHE={len(noche)}")
    return {"DIA": dia, "NOCHE": noche, "LOTERIAS": []}
