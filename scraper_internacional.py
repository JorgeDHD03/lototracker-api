"""
scraper_internacional.py — scrapers separados por turno y fuente

FUENTES:
  Pick 3/4 → lotteryusa.com/florida/pick-X  (solo Evening)
  Win 4    → nylottery.org/es/win-4/resultados (Mediodía + Tarde)
  Evening  → resultadodelaloteria.com/colombia/evening

HTML CONFIRMADO:
  lotteryusa: <li class="c-ball c-ball--sm">7</li> x N  (ignorar c-result__bonus)
  nylottery:  td[1] contiene 8 spans.resultBall — primeros 4 = WM, últimos 4 = WN
"""

import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def _get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def _lotteryusa(url: str, n: int) -> str | None:
    """Primera fila de lotteryusa.com — Evening más reciente."""
    try:
        soup = _get_soup(url)
        fila = soup.select_one("tr.c-draw-card")
        if not fila:
            logger.warning(f"lotteryusa: sin filas en {url}")
            return None
        balls = [li.get_text(strip=True)
                 for li in fila.select("li.c-ball--sm")
                 if li.get_text(strip=True).isdigit()]
        if len(balls) == n:
            return "".join(balls)
        logger.warning(f"lotteryusa: esperaba {n}, encontró {len(balls)}")
    except Exception as e:
        logger.warning(f"lotteryusa error {url}: {e}")
    return None


def _win4() -> dict:
    """
    nylottery.org — primera fila con resultBall.
    td[1] tiene 8 spans en orden: [WM0,WM1,WM2,WM3, WN0,WN1,WN2,WN3]
    """
    resultado = {"WM": None, "WN": None}
    try:
        soup = _get_soup("https://www.nylottery.org/es/win-4/resultados")
        for fila in soup.select("table tr"):
            tds = fila.find_all("td", class_="centred")
            if len(tds) < 2:
                continue
            spans = [s.get_text(strip=True)
                     for s in tds[1].find_all("span")
                     if "resultBall" in " ".join(s.get("class", []))
                     and s.get_text(strip=True).isdigit()]
            if len(spans) >= 4:
                resultado["WM"] = "".join(spans[:4])
            if len(spans) >= 8:
                resultado["WN"] = "".join(spans[4:8])
            break  # solo primera fila
    except Exception as e:
        logger.warning(f"Win4 error: {e}")
    return resultado


def _evening() -> str | None:
    try:
        soup = _get_soup("https://resultadodelaloteria.com/colombia/evening")
        for tag in soup.select("[class*='result'],[class*='number'],[class*='ball'],[class*='winning']"):
            txt = re.sub(r"\D", "", tag.get_text(separator="", strip=True))
            if len(txt) == 4:
                return txt
        m = re.findall(r'\b\d{4}\b', soup.get_text())
        return m[0] if m else None
    except Exception as e:
        logger.warning(f"Evening error: {e}")
    return None


def obtener_sorteos_internacional() -> dict:
    """
    Retorna resultados con fecha real por turno:
      DIA   (P3_DIA, P4_DIA, WM)          → fecha_dia   = hoy
      NOCHE (P3_NOCHE, P4_NOCHE, WN, EV)  → fecha_noche = ayer
    """
    from datetime import date, timedelta
    hoy  = date.today().isoformat()
    ayer = (date.today() - timedelta(days=1)).isoformat()

    win4 = _win4()
    return {
        "P3_DIA":      _lotteryusa("https://www.lotteryusa.com/florida/midday-pick-3/", 3),
        "P3_NOCHE":    _lotteryusa("https://www.lotteryusa.com/florida/pick-3/", 3),
        "P4_DIA":      _lotteryusa("https://www.lotteryusa.com/florida/midday-pick-4/", 4),
        "P4_NOCHE":    _lotteryusa("https://www.lotteryusa.com/florida/pick-4/", 4),
        "WM":          win4["WM"],
        "WN":          win4["WN"],
        "EV":          _evening(),
        "fecha_dia":   hoy,    # P3_DIA, P4_DIA, WM corresponden a hoy
        "fecha_noche": ayer,   # P3_NOCHE, P4_NOCHE, WN, EV corresponden a ayer
    }
