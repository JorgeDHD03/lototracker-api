"""
api.py — LotoTracker API
========================
FastAPI que expone los scrapers de LotoTracker para ser consumidos
desde la app móvil Flutter u otros clientes.

Endpoints:
  GET  /              → health check
  POST /consultar     → ejecuta scraping y guarda en Supabase
  GET  /consultar     → igual pero sin body (para pruebas desde browser)
  GET  /fechas        → fechas disponibles en Supabase
  GET  /sorteos/{fecha} → sorteos de una fecha específica
"""

import os
import logging
from datetime import date, datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Supabase ─────────────────────────────────────────────────
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    "https://vtzcovlgccsjsbqvxcqx.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ0emNvdmxnY2NzanNicXZ4Y3F4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0NDkzNjQsImV4cCI6MjA4OTAyNTM2NH0."
    "47VgTctMZw4WUJiWr8_dMW5lZx60vdpvDqT9v4bWLfg"
)

def _sb() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ── FastAPI ───────────────────────────────────────────────────
app = FastAPI(
    title="LotoTracker API",
    description="Scraping de sorteos colombianos e internacionales",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ─────────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "ok", "fecha": date.today().isoformat()}


# ── Consultar y guardar ──────────────────────────────────────
@app.get("/consultar")
@app.post("/consultar")
def consultar():
    """
    Ejecuta el scraping de loteriasdehoy.co y lotteryusa.com,
    luego guarda los resultados en Supabase.
    Retorna un resumen de lo guardado.
    """
    try:
        from scraper_colombia import obtener_sorteos_colombia
        from scraper_internacional import obtener_sorteos_internacional
    except ImportError as e:
        raise HTTPException(500, f"Error importando scrapers: {e}")

    # ── Scraping ─────────────────────────────────────────────
    try:
        logger.info("Iniciando scraping Colombia...")
        data_col = obtener_sorteos_colombia()
    except Exception as e:
        logger.error(f"Error scraping Colombia: {e}")
        data_col = {"DIA": [], "NOCHE": [], "LOTERIAS": []}

    try:
        logger.info("Iniciando scraping Internacional...")
        data_int = obtener_sorteos_internacional()
    except Exception as e:
        logger.error(f"Error scraping Internacional: {e}")
        data_int = {}

    # ── Guardar en Supabase ───────────────────────────────────
    sb = _sb()
    conteo = {"chances": 0, "loterias": 0, "int": 0}

    # Chances DÍA y NOCHE
    filas_chances = []
    for turno in ("DIA", "NOCHE"):
        for s in data_col.get(turno, []):
            filas_chances.append({
                "fecha":    s.get("fecha", date.today().isoformat()),
                "turno":    turno,
                "nombre":   s["nombre"],
                "acronimo": s.get("acronimo"),
                "numero":   s["numero"],
                "serie":    s.get("serie"),
                "signo":    s.get("signo"),
            })
    if filas_chances:
        sb.table("sorteos_chances").upsert(
            filas_chances, on_conflict="fecha,turno,nombre").execute()
        conteo["chances"] = len(filas_chances)

    # Loterías grandes
    filas_lot = []
    for s in data_col.get("LOTERIAS", []):
        filas_lot.append({
            "fecha":    s.get("fecha", date.today().isoformat()),
            "nombre":   s["nombre"],
            "acronimo": s.get("acronimo"),
            "numero":   s["numero"],
            "serie":    s.get("serie"),
        })
    if filas_lot:
        sb.table("sorteos_loterias").upsert(
            filas_lot, on_conflict="fecha,nombre").execute()
        conteo["loterias"] = len(filas_lot)

    # Internacionales
    hoy  = date.today().isoformat()
    ayer = (date.today().replace(day=date.today().day - 1)).isoformat()

    filas_int = []
    for turno, claves, fecha in (
        ("DIA",   ("P3_DIA",   "P4_DIA",   "WM",  None),  hoy),
        ("NOCHE", ("P3_NOCHE", "P4_NOCHE", "WN",  "EV"),  ayer),
    ):
        p3k, p4k, wk, evk = claves
        fila = {
            "fecha": fecha,
            "turno": turno,
            "p3":    data_int.get(p3k),
            "p4":    data_int.get(p4k),
            "wm_wn": data_int.get(wk),
            "ev":    data_int.get(evk) if evk else None,
        }
        if any(v is not None for k, v in fila.items() if k not in ("fecha","turno")):
            filas_int.append(fila)

    if filas_int:
        sb.table("sorteos_int").upsert(
            filas_int, on_conflict="fecha,turno").execute()
        conteo["int"] = len(filas_int)

    total = conteo["chances"] + conteo["loterias"] + conteo["int"]
    logger.info(f"Guardado OK: {conteo}")

    return {
        "ok": True,
        "fecha": hoy,
        "guardado": conteo,
        "total": total,
        "sorteos": {
            "dia":      data_col.get("DIA", []),
            "noche":    data_col.get("NOCHE", []),
            "loterias": data_col.get("LOTERIAS", []),
            "int":      data_int,
        }
    }


# ── Fechas disponibles ────────────────────────────────────────
@app.get("/fechas")
def fechas():
    """Retorna todas las fechas con datos en Supabase."""
    sb = _sb()
    res1 = sb.table("sorteos_chances").select("fecha").execute()
    res2 = sb.table("sorteos_loterias").select("fecha").execute()
    res3 = sb.table("sorteos_int").select("fecha").execute()

    todas = set()
    for r in [*res1.data, *res2.data, *res3.data]:
        if r.get("fecha"):
            todas.add(r["fecha"])

    return {"fechas": sorted(todas, reverse=True)}


# ── Sorteos de una fecha ──────────────────────────────────────
@app.get("/sorteos/{fecha}")
def sorteos_fecha(fecha: str):
    """
    Retorna todos los sorteos de una fecha ISO (YYYY-MM-DD).
    """
    sb = _sb()

    chances  = sb.table("sorteos_chances").select("*").eq("fecha", fecha).order("id").execute()
    loterias = sb.table("sorteos_loterias").select("*").eq("fecha", fecha).order("id").execute()
    ints     = sb.table("sorteos_int").select("*").eq("fecha", fecha).execute()

    return {
        "fecha":    fecha,
        "dia":      [r for r in chances.data  if r["turno"] == "DIA"],
        "noche":    [r for r in chances.data  if r["turno"] == "NOCHE"],
        "loterias": loterias.data,
        "int":      ints.data,
    }


@app.get("/debug_html")
def debug_html():
    """Retorna fragmentos del HTML de chancehoy para diagnóstico."""
    try:
        from curl_cffi import requests as creq
        from bs4 import BeautifulSoup
        import re
        resp = creq.get(
            "https://www.chancehoy.com/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            timeout=20,
            impersonate="chrome110"
        )
        html = resp.text
        soup = BeautifulSoup(html, "lxml")
        # Find all links to sorteos
        links = soup.find_all("a", href=re.compile(r"/sorteo"))
        link_samples = []
        for a in links[:5]:
            link_samples.append({
                "href": a.get("href"),
                "text": a.get_text(separator="|").strip()[:100]
            })
        # Find number patterns
        nums = re.findall(r"\d{4}", html)[:20]
        # Sample from middle of HTML
        mid = len(html)//2
        return {
            "status": resp.status_code,
            "html_length": len(resp.text),
            "sorteo_links_found": len(links),
            "link_samples": link_samples,
            "numbers_found": nums,
            "html_mid_500": html[mid:mid+500],
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/debug_scraper")
def debug_scraper():
    """Muestra exactamente qué devuelve el scraper Colombia."""
    try:
        from scraper_colombia import obtener_sorteos_colombia
        data = obtener_sorteos_colombia()
        return {
            "dia_count":   len(data.get("DIA", [])),
            "noche_count": len(data.get("NOCHE", [])),
            "dia":   data.get("DIA", []),
            "noche": data.get("NOCHE", []),
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}


@app.get("/debug_int")
def debug_int():
    """Muestra exactamente qué devuelve el scraper Internacional."""
    try:
        from scraper_internacional import obtener_sorteos_internacional
        data = obtener_sorteos_internacional()
        return data
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()}
