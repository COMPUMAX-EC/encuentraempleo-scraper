"""Portales de empleo que exigen un navegador real o una sesión iniciada, leídos con el Chrome del scraper.

GitHub Actions no puede leerlos, así que se recogen desde este computador y se escriben en los JSON del sitio de
Oportunidades (los mismos que llenan los recolectores del workflow, que conservan las ofertas de estas fuentes):
  - CACPECO (cooperativa): publica en Laburo (quierolaburo.com), cuya API exige Firebase App Check. Se toma la
    respuesta que recibe la propia página -> lib/data/finance-jobs.json
  - Corporación El Rosado (Mi Comisariato, Supercines...): exige cuenta; el usuario inicia sesión en
    empleo.elrosado.com -> lib/data/private-jobs.json

Usa el Chrome de abrir_chrome.ps1 (puerto 9222) con las sesiones que inició el usuario: nunca escribe credenciales ni
postula. Después, publicar_sitio.py sube los cambios en un PR.

Uso:  python portales_navegador.py
      python portales_navegador.py --fuente cacpeco --chrome-propio
          Solo CACPECO, en un Chrome que abre el script (una ventana unos segundos: Laburo no responde a un navegador
          invisible). Lo corre el runner de COMPUMAX-EC/oportunidades-runner dos veces al día, sin que haga falta abrir
          abrir_chrome.ps1. El Rosado necesita la sesión del usuario y sigue yendo por el puerto 9222.
"""

import argparse
import json
import re
import sys
from datetime import date

from playwright.sync_api import Page, sync_playwright

from publicar_sitio import ESTADO, SITIO, json_sitio
from scraper import CDP, PAUSA_PETICION, pausa

# Mismo criterio que scripts/lib/it-roles.mjs del sitio, resumido: cargo de TI por su título
ROL_TI = re.compile(r"tecnolog[ií]as? de (la )?informaci[oó]n|\bTICS?\b|\bTI\b|inform[aá]tic|software|desarrollador|"
                    r"programador|devops|ciberseguridad|base de datos|\bdatos\b|\bdata\b|soporte t[eé]cnico|"
                    r"\b(ingenier[oa]|analista|t[eé]cnic[oa]) de soporte\b|"
                    r"\b(analista|asistente|t[eé]cnic[oa]|especialista|ingenier[oa]|jefe) (de )?(sistemas|redes)\b", re.I)


def laburo(page: Page, slug: str) -> list[dict]:
    """Vacantes de una empresa en Laburo: la página pide la lista a su API y se toma esa respuesta."""
    url = f"https://quierolaburo.com/empresas/{slug}"
    with page.expect_response(lambda r: "getpubliccompanyjobs" in r.url, timeout=60_000) as info:
        page.goto(url)
    datos = info.value.json()
    paginacion = datos.get("pagination") or {}
    if paginacion.get("totalPages", 1) > 1:
        print(f"  Laburo {slug}: {paginacion['total']} vacantes en {paginacion['totalPages']} páginas; solo se leyó la primera.")
    # Laburo abre cada vacante en una ventana sobre la página de la empresa: el enlace es esa página
    return [{"key": j["_id"], "title": j["title"].strip(), "city": (j.get("location") or {}).get("city"),
             "publishedAt": (j.get("datePosted") or "")[:10] or None, "url": url} for j in datos.get("jobs", [])]


def el_rosado(page: Page) -> list[dict]:
    """Corporación El Rosado (empleo.elrosado.com): exige cuenta. Recorre sus áreas (Retail, Entretenimiento,
    Restaurantes, Industrial) como lo haría el usuario: la página guarda el área elegida en localStorage y al abrir la
    lista pide las ofertas a su API (ConsultaOferta); se toma esa respuesta."""
    base = "https://empleo.elrosado.com"
    with page.expect_response(lambda r: "ConsultaLogoSociedad" in r.url, timeout=60_000) as info:
        page.goto(f"{base}/Postulante/frmAplicacionSociedad")
    if "/Home/Login" in page.url:
        raise RuntimeError("no hay sesión: inicia sesión en El Rosado en el Chrome del scraper")
    areas = [a for grupo in info.value.json()["root"] for a in grupo]
    ofertas = {}
    for i, area in enumerate(areas):
        if i:
            pausa(*PAUSA_PETICION)
        page.evaluate("id => localStorage.setItem('ls.ofertaArea', id)", area["id"])
        with page.expect_response(lambda r: "ConsultaOferta" in r.url, timeout=60_000) as info:
            page.goto(f"{base}/Postulante/frmAplicacionOferta")
        raiz = info.value.json().get("root") or []
        for o in (raiz[0] if raiz and isinstance(raiz[0], list) else raiz):
            d, m, a = (o.get("fechaOferta") or "//").split("/")
            ofertas[o["idOferta"]] = {
                # descCargo es el cargo oficial; descripcionCargo es texto libre (a veces una frase de funciones)
                "key": o["idOferta"], "title": " – ".join(x.strip() for x in (o["descCargo"], o.get("descDependencia") or "") if x.strip()),
                "area": o.get("descArea") or None,
                "city": (o.get("descCiudad") or "").strip() or None,
                "publishedAt": f"{a}-{m.zfill(2)}-{d.zfill(2)}" if a else None,
                "url": f"{base}/Postulante/frmAplicacionSociedad",  # la oferta se abre dentro del portal, con cuenta
            }
    return list(ofertas.values())


FUENTES = [
    {"archivo": "lib/data/private-jobs.json", "id": "elrosado", "nombre": "Corporación El Rosado", "campo": "company",
     "estado": "El-Rosado", "leer": el_rosado},
    {"archivo": "lib/data/finance-jobs.json", "id": "cacpeco", "nombre": "CACPECO", "campo": "institution",
     "estado": "CACPECO", "leer": lambda page: laburo(page, "cacpeco")},
]


def integrar(fuente: dict, encontradas: list[dict]) -> None:
    """Agrega lo leído al historial del JSON del sitio, como hacen los recolectores del workflow."""
    ruta = SITIO / fuente["archivo"]
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    hoy = date.today().isoformat()
    por_id = {j["id"]: j for j in datos["jobs"]}
    vistas = set()
    for item in encontradas:
        item = dict(item)
        id_ = f"{fuente['id']}-{item.pop('key')}"
        vistas.add(id_)
        por_id[id_] = {"id": id_, "source": fuente["id"], fuente["campo"]: fuente["nombre"], **item,
                       "isIT": bool(ROL_TI.search(item["title"])),
                       "firstSeen": por_id.get(id_, {}).get("firstSeen", hoy)}
    for id_, j in list(por_id.items()):  # las que ya no aparecen quedan como cerradas
        if j.get("source") == fuente["id"] and id_ not in vistas and not j.get("closedOn"):
            por_id[id_] = {**j, "closedOn": hoy}
    trabajos = sorted(por_id.values(), key=lambda j: j.get("publishedAt") or j["firstSeen"], reverse=True)
    trabajos.sort(key=lambda j: bool(j.get("closedOn")))  # estable: abiertas primero
    nuevo = json_sitio({**datos, "jobs": trabajos})
    if ruta.read_text(encoding="utf-8").replace("\r\n", "\n") != nuevo:
        ruta.write_text(nuevo, encoding="utf-8", newline="\n")


def registrar_estado(resultados: dict[str, bool]) -> None:
    ruta = SITIO / ESTADO
    estado = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {"platforms": {}}
    hoy = date.today().isoformat()
    for clave, ok in resultados.items():
        antes = estado["platforms"].get(clave, {})
        estado["platforms"][clave] = {"lastRun": hoy, "lastSuccess": hoy if ok else antes.get("lastSuccess"), "ok": ok}
    estado["platforms"] = dict(sorted(estado["platforms"].items()))
    ruta.write_text(json_sitio(estado), encoding="utf-8", newline="\n")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fuente", choices=[f["id"] for f in FUENTES], action="append",
                        help="solo esta fuente (se puede repetir); por defecto, todas")
    parser.add_argument("--chrome-propio", action="store_true",
                        help="abre su propio Chrome en vez de usar el de abrir_chrome.ps1 (sin sesiones iniciadas)")
    args = parser.parse_args()
    fuentes = [f for f in FUENTES if not args.fuente or f["id"] in args.fuente]
    resultados = {}
    with sync_playwright() as p:
        if args.chrome_propio:
            # Si la ventana queda detrás de otras, Chrome frena la página y Laburo no llega a pedir las vacantes
            navegador = p.chromium.launch(channel="chrome", headless=False, args=[
                "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling"])
            page = navegador.new_page(locale="es-EC")
            page.bring_to_front()
        else:
            try:
                navegador = p.chromium.connect_over_cdp(CDP)
            except Exception:  # noqa: BLE001
                sys.exit("No encuentro el Chrome del scraper en el puerto 9222: ábrelo con abrir_chrome.ps1.")
            page = navegador.contexts[0].new_page()
        try:
            for fuente in fuentes:
                try:
                    encontradas = fuente["leer"](page)
                except Exception as e:  # noqa: BLE001 - si una fuente falla no se cierra ninguna de sus ofertas
                    resultados[fuente["estado"]] = False
                    print(f"{fuente['nombre']}: error ({e})")
                    continue
                integrar(fuente, encontradas)
                resultados[fuente["estado"]] = True
                de_ti = sum(bool(ROL_TI.search(e["title"])) for e in encontradas)
                print(f"{fuente['nombre']}: {len(encontradas)} vacantes ({de_ti} de TI)")
        finally:
            page.close()
            if args.chrome_propio:
                navegador.close()
    registrar_estado(resultados)
    sys.exit(0 if all(resultados.values()) else 1)


if __name__ == "__main__":
    main()
