"""
Scraper para https://loteriasdehoy.co

ESTRUCTURA HTML CONFIRMADA:

CHANCES (div.chances_hoy):
  span.chance1 x4 = número | span.premio5 x1 = serie opcional

LOTERIAS GRANDES (div.loterias_resultados):
  span.redondoc.premio1 x4 = número | span.redondoc.serie1 x3 = serie

REGLA DE FECHAS:
  DIA      → fecha = HOY
  NOCHE    → fecha = AYER  (loterías nocturnas, se publican al día siguiente)
  LOTERIAS → fecha = AYER  (loterías grandes también se publican al día siguiente)
"""

from curl_cffi import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
import re
import logging

logger = logging.getLogger(__name__)

URL = "https://loteriasdehoy.co"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

LOTERIAS_NOCHE = {
    "astro luna",
    "caribeña noche",
    "sinuano noche",
    "motilon noche",
    "fantastica noche",
    "culona noche",
    "cafeterito noche",
    "chontico noche",
    "super chontico noche",
    "paisita noche",
}

EXCLUIR_NOMBRES = {"pick 3", "pick 4"}

# Loterías grandes — NO son chances, van en su propia sección
LOTERIAS_GRANDES_NOMBRES = {
    "lotería de bogotá", "lotería de medellín", "lotería del meta",
    "lotería del tolima", "lotería de manizales", "lotería del quindío",
    "lotería de santander", "lotería del huila", "lotería de la cruz roja",
    "lotería del valle", "lotería de boyacá", "lotería del chocó",
    "lotería de cundinamarca", "lotería del risaralda", "lotería de nariño",
    "lotería dorada", "baloto", "superastro", "extra de colombia",
    "lotería del cauca", "lotería de caldas", "lotería del cesar",
    "lotería de córdoba", "lotería del magdalena", "lotería de nariño",
    "lotería del pacifico", "lotería de sucre", "lotería del vichada",
    "lotería", "loterias",
}

NOMBRES_COMPLETOS = {
    "culona día", "culona noche",
    "chontico día", "chontico noche", "super chontico noche",
    "saman",
}

ACRONIMOS_FIJOS = {
    "cafeterito noche":  "CFN",
    "cafeterito tarde":  "CF",
    "caribeña día":      "C",
    "caribeña noche":    "CN",
    "sinuano día":       "S",
    "sinuano noche":     "SN",
    "antioqueñita 1":    "AM",
    "antioqueñita 2":    "AT",
    "dorado mañana":     "DM",
    "dorado tarde":      "DT",
    "dorado noche":      "DN",
    "motilon tarde":     "MT",
    "motilon noche":     "MTN",
    "paisita día":       "P",
    "paisita noche":     "PN",
    "fantastica día":    "F",
    "fantastica noche":  "FN",
    "pijao de oro":      "PJ",
    "astro sol":         "AS",
    "astro luna":        "AL",
}


def _parsear_fecha(texto: str):
    texto = re.sub(r"\bde\b", "", texto.lower().strip())
    partes = texto.split()
    try:
        dia  = int(partes[0])
        mes  = MESES_ES.get(partes[1])
        anio = int(partes[2])
        if mes:
            return date(anio, mes, dia)
    except (IndexError, ValueError):
        pass
    return None


def _es_noche(nombre: str) -> bool:
    return any(ln in nombre.lower().strip() for ln in LOTERIAS_NOCHE)


def _es_excluido(nombre: str) -> bool:
    n = nombre.lower().strip()
    if any(p in n for p in EXCLUIR_NOMBRES):
        return True
    # Excluir loterías grandes de la sección chances
    if any(lg in n for lg in LOTERIAS_GRANDES_NOMBRES):
        return True
    return False


def _generar_acronimo(nombre: str) -> str:
    clave = nombre.lower().strip()
    if clave in NOMBRES_COMPLETOS:
        return nombre.strip()
    if clave in ACRONIMOS_FIJOS:
        return ACRONIMOS_FIJOS[clave]
    palabras = nombre.split()
    acronimo = "".join(p[0].upper() for p in palabras if p and p[0].isalpha())
    return acronimo[:4] if acronimo else "??"


def obtener_sorteos_colombia() -> dict:
    from datetime import timezone
    # Usar hora de Colombia (UTC-5) independientemente del servidor
    colombia_tz = timezone(timedelta(hours=-5))
    ahora_colombia = datetime.now(colombia_tz)
    hoy   = ahora_colombia.date()
    ayer  = hoy - timedelta(days=1)
    hora  = ahora_colombia.hour
    # Si ya pasaron las 19:00 hora Colombia, los sorteos noche ya pueden estar publicados
    noche_acepta_hoy = hora >= 19
    incluir_super_chontico = (ayer.weekday() == 3)  # solo jueves

    r = requests.get(URL, headers=HEADERS, timeout=15, impersonate="chrome110")
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    data = {"DIA": [], "NOCHE": [], "LOTERIAS": []}
    _noche_tiene_hoy = False

    # ── 1) CHANCES ──────────────────────────────────────────
    for bloque in soup.select("div.chances_hoy"):
        titulo_tag = bloque.select_one("div.titulo_chances_hoy")
        if not titulo_tag:
            continue
        nombre = titulo_tag.get_text(strip=True)

        if _es_excluido(nombre):
            continue
        if "super chontico" in nombre.lower() and not incluir_super_chontico:
            continue

        fecha_tag = bloque.select_one("div.fecha_resultado")
        if not fecha_tag:
            continue
        fecha = _parsear_fecha(fecha_tag.get_text(strip=True))
        if fecha is None:
            continue

        es_nocturno = _es_noche(nombre)
        if es_nocturno:
            # NOCHE: acepta ayer o hoy, pero SIEMPRE guarda con fecha = ayer
            if fecha not in (ayer, hoy):
                continue
            fecha = ayer  # forzar fecha correcta
        else:
            # DÍA: solo fecha de hoy
            if fecha != hoy:
                continue

        resultado_div = bloque.select_one("div.resultado_chances_hoy")
        if not resultado_div:
            continue

        # Número: spans chance1 (4 dígitos)
        spans = resultado_div.select("span.chance1")
        if not spans:
            spans = resultado_div.select("span.redondoc")
        digitos = [s.get_text(strip=True) for s in spans if s.get_text(strip=True).isdigit()]

        if len(digitos) < 4:
            continue

        numero = "".join(digitos[:4])

        # Serie: span.premio5
        serie = None
        span_serie = resultado_div.select_one("span.premio5")
        if span_serie:
            t = span_serie.get_text(strip=True)
            if t.isdigit():
                serie = t

        # Signo zodiacal
        signo = None
        m = re.search(r"-\s*([A-Za-záéíóúÁÉÍÓÚñÑ]+)", resultado_div.get_text(strip=True))
        if m:
            signo = m.group(1).strip()

        item = {
            "numero":   numero,
            "acronimo": _generar_acronimo(nombre),
            "nombre":   nombre,
            "serie":    serie,
            "signo":    signo,
            "fecha":    fecha.isoformat(),
        }
        # Deduplicar: la página muestra cada lotería varias veces ordenada de más
        # reciente a más antigua. Solo guardar la primera aparición de cada nombre.
        if es_nocturno:
            if nombre.lower() not in {x["nombre"].lower() for x in data["NOCHE"]}:
                data["NOCHE"].append(item)
                if fecha == hoy:
                    _noche_tiene_hoy = True
        else:
            if nombre.lower() not in {x["nombre"].lower() for x in data["DIA"]}:
                data["DIA"].append(item)

    # Si NOCHE tiene resultados de HOY, descartar los de AYER para no mezclar fechas
    if _noche_tiene_hoy:
        data["NOCHE"] = [s for s in data["NOCHE"] if s["fecha"] == hoy.isoformat()]

    # ── 2) LOTERÍAS GRANDES → fecha de AYER ─────────────────
    # Confirmado: la página publica las loterías grandes con fecha
    # del día anterior (ej: hoy es martes 3, muestra "2 Marzo 2026")
    for bloque in soup.select("div.loterias_resultados"):
        h3 = bloque.find("h3")
        if not h3:
            continue
        nombre = h3.get_text(strip=True).strip()

        fecha_tag = bloque.select_one("div.fecha_resultado")
        if not fecha_tag:
            continue
        fecha = _parsear_fecha(fecha_tag.get_text(strip=True))
        if fecha is None:
            continue

        # Aceptar fecha de hasta 7 días atrás (loterías no juegan todos los días)
        dias_diff = (hoy - fecha).days
        if dias_diff < 0 or dias_diff > 7:
            logger.debug(f"Lotería '{nombre}' ignorada: fecha {fecha} muy antigua")
            continue

        # Número: 4 spans con clase premio1
        spans_numero = bloque.select("span.premio1")
        digitos_numero = [s.get_text(strip=True) for s in spans_numero
                          if s.get_text(strip=True).isdigit()]

        if len(digitos_numero) < 4:
            logger.debug(f"Lotería '{nombre}': solo {len(digitos_numero)} dígitos")
            continue

        numero = "".join(digitos_numero[:4])

        # Serie: spans con clase serie1 (3 dígitos)
        spans_serie = bloque.select("span.serie1")
        digitos_serie = [s.get_text(strip=True) for s in spans_serie
                         if s.get_text(strip=True).isdigit()]
        serie = "".join(digitos_serie) if digitos_serie else None

        data["LOTERIAS"].append({
            "numero":   numero,
            "acronimo": _generar_acronimo(nombre),
            "nombre":   nombre,
            "serie":    serie,
            "signo":    None,
            "fecha":    fecha.isoformat(),
        })

    logger.info(
        f"DIA: {len(data['DIA'])} | NOCHE: {len(data['NOCHE'])} "
        f"| LOTERIAS: {len(data['LOTERIAS'])}"
    )
    return data
