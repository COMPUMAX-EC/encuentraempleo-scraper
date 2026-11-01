"""Concursos públicos (méritos y oposición) de Encuentra Empleo: descarga las bases de cada vacante abierta.

Recorre la lista de instituciones de busquedaOfertaPublica.jsf, abre "Nuevas vacantes" (concursos en
postulación; "Puesto en concurso" es el histórico de concursos nulos/desiertos/ganados y no se usa),
descarga el PDF "Bases del concurso" de cada vacante y extrae de él el área del conocimiento exigida.
Nunca pulsa "Aplicar".

Uso (con la sesión abierta en el Chrome de abrir_chrome.ps1):
    python publicas.py              # descarga y genera salida/publicas_AAAAMMDD_HHMM.xlsx
    python publicas.py vacantes     # solo refresca las instituciones con vacantes (sin recorrer las 175 páginas)
    python publicas.py excel        # rehace el Excel con lo ya descargado (sin Chrome)

Los PDF quedan en salida/bases/; los que ya existen no se vuelven a descargar.
"""

import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from playwright.sync_api import Page, sync_playwright
from pypdf import PdfReader

from scraper import CDP, DATOS, PAUSA_ENTRE_AREAS, SALIDA, SesionCaducada, esperar_ajax, normalizar, pausa

URL_PUBLICAS = "https://encuentraempleo.trabajo.gob.ec/socioEmpleo-war/paginas/aspirante/busquedaOfertaPublica.jsf"
BASES = SALIDA / "bases"
# Copia pública de los PDF en GitHub (la sube subir_bases.py)
REPO_GITHUB = "COMPUMAX-EC/encuentraempleo-scraper"
RELEASE_BASES = "bases-concursos"
BASES_GITHUB = f"https://github.com/{REPO_GITHUB}/releases/download/{RELEASE_BASES}/"
REGISTRO = DATOS / "publicas.json"  # vacantes leídas, por código del puesto
DIRECTORIO = DATOS / "instituciones.json"  # todas las instituciones (contacto) y la página por la que va el recorrido

TABLA_INST = "formBuscaPublica:itemsTable"
TABLA_VAC = "vacantesAplMpForm:vacantesTableMp"

# Áreas del conocimiento que un profesional TI cumple (se buscan solo en el área exigida por las bases).
AREA_TI = (r"informatic|sistemas|computacion|software|tecnologias? de la informacion|telecomunic|\bredes\b"
           r"|\btics?\b|ciencia de datos|electronica y automatizacion|electronica y telecomunicaciones")


def slug(texto: str, largo: int = 40) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:largo]


def pestana(p) -> Page:
    try:
        navegador = p.chromium.connect_over_cdp(CDP, timeout=30_000)
    except Exception:
        sys.exit("No encuentro Chrome en el puerto 9222. Ábrelo con: .\\abrir_chrome.ps1")
    ctx = navegador.contexts[0]
    page = next((pg for pg in ctx.pages if "trabajo.gob.ec" in pg.url), None) or ctx.new_page()
    page.goto(URL_PUBLICAS, wait_until="networkidle")
    if "busquedaOfertaPublica" not in page.url or not page.locator(f"[id='{TABLA_INST}']").count():
        sys.exit("No hay sesión activa: inicia sesión como aspirante en esa ventana de Chrome y vuelve a ejecutar.")
    return page


def pagina_actual(page: Page, tabla: str) -> tuple[int, int]:
    """Lee '(3 of 175)' del paginador de una tabla."""
    texto = page.evaluate(
        f"document.querySelector(\"[id='{tabla}_paginator_bottom'] .ui-paginator-current\")?.innerText || ''")
    m = re.search(r"\((\d+) of (\d+)\)", texto)
    return (int(m.group(1)), int(m.group(2))) if m else (1, 1)


def siguiente_pagina(page: Page, tabla: str) -> bool:
    boton = page.locator(f"[id='{tabla}_paginator_bottom'] .ui-paginator-next")
    if not boton.count() or "ui-state-disabled" in (boton.get_attribute("class") or ""):
        return False
    esperar_ajax(page, lambda: boton.evaluate("a => a.click()"))
    return True


def instituciones_de_la_pagina(page: Page) -> list[dict]:
    return page.evaluate(f"""() => [...document.querySelectorAll("[id='{TABLA_INST}_data'] tr[data-ri]")].map(tr => ({{
        ri: tr.getAttribute('data-ri'), institucion: tr.cells[0].innerText.trim(),
        nuevas: parseInt((tr.cells[1].innerText.match(/(\\d+)\\s*Nuevas/) || [0, 0])[1]),
        correo: tr.cells[3]?.innerText.trim() || '', telefono: tr.cells[4]?.innerText.trim() || '' }}))""")


def ir_a_pagina_instituciones(page: Page, n: int) -> None:
    """Salta a la página n (1..total) con el paginador del widget: una sola petición."""
    if pagina_actual(page, TABLA_INST)[0] != n:
        esperar_ajax(page, lambda: page.evaluate(f"PF('itemsTableVar').paginator.setPage({n - 1})"))


def leer_pdf(ruta: Path) -> dict:
    try:
        texto = " ".join(p.extract_text() or "" for p in PdfReader(ruta).pages)
    except Exception:
        return {"area_conocimiento": "", "instruccion_bases": "", "experiencia_bases": ""}
    texto = re.sub(r"\s+", " ", texto)
    area = re.search(r"AREA DEL CONOCIMIENTO:\s*(.+?)\s*TITULO:", texto)
    nivel = re.search(r"NIVEL:\s*(.+?)\s*AREA DEL CONOCIMIENTO", texto)
    exp = re.search(r"(\d+) AÑO\(S\) - (\d+) MESE\(S\)", texto)
    return {
        "area_conocimiento": area.group(1).strip() if area else "",
        "instruccion_bases": nivel.group(1).strip() if nivel else "",
        "experiencia_bases": f"{exp.group(1)} años {exp.group(2)} meses" if exp else "",
    }


def vacantes_de(page: Page, inst: dict, registro: dict) -> None:
    ir_a_pagina_instituciones(page, int(inst["ri"]) // 8 + 1)
    ver = page.locator(f"[id='{TABLA_INST}_data'] tr[data-ri='{inst['ri']}'] td:nth-child(2) a")
    esperar_ajax(page, lambda: ver.evaluate("a => a.click()"))
    # La tabla de vacantes recuerda la página en que quedó con la institución anterior: volver a la 1.
    if pagina_actual(page, TABLA_VAC)[0] != 1:
        esperar_ajax(page, lambda: page.evaluate(
            f"Object.values(PrimeFaces.widgets).find(w => w && w.id === '{TABLA_VAC}').paginator.setPage(0)"))
    leidas = 0
    while True:
        filas = page.evaluate(f"""() => [...document.querySelectorAll("[id='{TABLA_VAC}_data'] tr[data-ri]")].map(tr => ({{
            ri: tr.getAttribute('data-ri'), codigo: tr.cells[0].innerText.trim(), puesto: tr.cells[1].innerText.trim(),
            vacantes: tr.cells[2].innerText.trim(), rmu: tr.cells[3].innerText.trim(), ubicacion: tr.cells[4].innerText.trim(),
            etapa: tr.cells[6].innerText.trim(),
            cierre: tr.cells[7].querySelector('[data-countdown]')?.getAttribute('data-countdown') || '' }}))""")
        for f in filas:
            if not f["codigo"].isdigit():
                continue
            leidas += int(f["vacantes"]) if f["vacantes"].isdigit() else 0
            ruta = BASES / f"{f['codigo']}_{slug(inst['institucion'])}_{slug(f['puesto'], 30)}.pdf"
            if not ruta.exists():
                enlace = page.locator(f"[id='{TABLA_VAC}_data'] tr[data-ri='{f['ri']}'] a:has-text('Ver bases')")
                try:
                    with page.expect_download(timeout=45_000) as d:
                        enlace.evaluate("a => a.click()")
                    d.value.save_as(ruta)
                except Exception:
                    # Con la sesión caducada, el envío de "Ver bases" (no AJAX) no da un 302 sino una página
                    # de error 404 de Payara que reemplaza al portal.
                    if "busquedaOfertaPublica" not in page.url or page.evaluate("typeof PrimeFaces === 'undefined'"):
                        raise SesionCaducada()
                    print(f"\n  ! sin bases {f['codigo']}")
                pausa(1.0, 2.5)
            registro[f["codigo"]] = {
                "institucion": inst["institucion"], "codigo": f["codigo"], "puesto": f["puesto"],
                "vacantes": f["vacantes"], "rmu": f["rmu"], "ubicacion": f["ubicacion"], "etapa": f["etapa"],
                "cierre": f["cierre"].replace("/", "-"), "correo": inst["correo"], "telefono": inst["telefono"],
                "archivo_bases": ruta.name if ruta.exists() else "",
                **(leer_pdf(ruta) if ruta.exists() else {}),
                # fecha en que se vio por primera vez; historial.py la usa para medir la frecuencia
                "primera_vez": registro.get(f["codigo"], {}).get("primera_vez", datetime.now().strftime("%Y-%m-%d")),
            }
        if not siguiente_pagina(page, TABLA_VAC):
            break
    page.evaluate("PF('vacAplDgl').hide()")
    if leidas != inst["nuevas"]:  # el contador de la lista cuenta puestos (vacantes), no filas
        print(f"\n  ! {inst['institucion'][:50]}: el portal anuncia {inst['nuevas']} vacantes y se leyeron {leidas}")


def exportar(registro: dict) -> Path:
    filas = sorted(registro.values(), key=lambda v: (v["cierre"], v["institucion"], v["puesto"]))
    for v in filas:
        v["postulable_ti"] = "Sí" if re.search(AREA_TI, normalizar(v.get("area_conocimiento", ""))) else ""
        v["bases_github"] = BASES_GITHUB + v["archivo_bases"] if v.get("archivo_bases") else ""
    columnas = [("postulable_ti", "Postulable desde TI", 12), ("cierre", "Cierre postulación", 18),
                ("institucion", "Institución", 40), ("puesto", "Puesto", 34), ("codigo", "Código", 10),
                ("vacantes", "Vacantes", 9), ("rmu", "RMU ($)", 10), ("ubicacion", "Ubicación", 16),
                ("instruccion_bases", "Instrucción", 30), ("experiencia_bases", "Experiencia", 16),
                ("area_conocimiento", "Área del conocimiento exigida", 70), ("archivo_bases", "Bases (PDF)", 30),
                ("bases_github", "Bases en GitHub", 30), ("correo", "Correo", 30), ("telefono", "Teléfono", 14)]
    wb = Workbook()
    hojas = [("Vacantes públicas", filas), ("Postulables desde TI", [v for v in filas if v["postulable_ti"]])]
    for i, (nombre, datos) in enumerate(hojas):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = nombre
        for c, (_, titulo, ancho) in enumerate(columnas, start=1):
            celda = ws.cell(row=1, column=c, value=titulo)
            celda.font = Font(name="Arial", bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", start_color="1F4E78")
            celda.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[get_column_letter(c)].width = ancho
        for r, v in enumerate(datos, start=2):
            for c, (k, _, _) in enumerate(columnas, start=1):
                valor = v.get(k, "")
                if k in ("vacantes",) and str(valor).isdigit():
                    valor = int(valor)
                elif k == "rmu":
                    try:
                        valor = float(valor)
                    except ValueError:
                        pass
                celda = ws.cell(row=r, column=c, value=valor)
                celda.font = Font(name="Arial", size=10)
                celda.alignment = Alignment(vertical="top", wrap_text=k == "area_conocimiento")
                if k in ("archivo_bases", "bases_github") and valor:
                    # enlace relativo: el Excel está en salida/, los PDF en salida/bases/
                    celda.hyperlink = f"bases/{valor}" if k == "archivo_bases" else valor
                    celda.font = Font(name="Arial", size=10, color="0563C1", underline="single")
                if k == "rmu":
                    celda.number_format = "#,##0.00"
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columnas))}{len(datos) + 1}"

    # Directorio de todas las instituciones públicas del portal, tengan o no vacantes abiertas.
    directorio = cargar_directorio()
    insts = sorted(directorio["instituciones"].values(), key=lambda i: (-i["nuevas_vacantes"], i["institucion"]))
    ws = wb.create_sheet("Instituciones")
    cols = [("institucion", "Institución", 60), ("nuevas_vacantes", "Vacantes abiertas", 11),
            ("correo", "Correo de contacto", 38), ("telefono", "Teléfono", 18), ("revisado", "Revisado", 16)]
    for c, (_, titulo, ancho) in enumerate(cols, start=1):
        celda = ws.cell(row=1, column=c, value=titulo)
        celda.font = Font(name="Arial", bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", start_color="1F4E78")
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = ancho
    for r, inst in enumerate(insts, start=2):
        for c, (k, _, _) in enumerate(cols, start=1):
            ws.cell(row=r, column=c, value=inst.get(k, "")).font = Font(name="Arial", size=10)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:E{len(insts) + 1}"
    if not directorio.get("completo"):
        ws.cell(row=len(insts) + 3, column=1, value=(
            f"Recorrido incompleto: faltan instituciones desde la página {directorio['pagina']}. "
            "Repite `python publicas.py` para completarlo.")).font = Font(name="Arial", italic=True, color="C00000")

    ruta = SALIDA / f"publicas_{datetime.now():%Y%m%d_%H%M}.xlsx"
    wb.save(ruta)
    return ruta


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    BASES.mkdir(parents=True, exist_ok=True)
    DATOS.mkdir(parents=True, exist_ok=True)
    try:
        registro = json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        registro = {}

    if sys.argv[1:] == ["excel"]:
        print(f"Excel: {exportar(registro)}")
        return

    directorio = cargar_directorio()
    # Modo "vacantes": solo repasa las páginas donde el directorio tiene instituciones con vacantes
    # (las primeras), sin rehacer el recorrido completo ni tocar su avance.
    solo_vacantes = sys.argv[1:] == ["vacantes"]
    pendientes = {i["institucion"] for i in directorio["instituciones"].values() if i["nuevas_vacantes"]}
    if solo_vacantes:
        if not pendientes:
            sys.exit("El directorio no tiene instituciones con vacantes: ejecuta primero `python publicas.py`.")
        avance = (directorio["pagina"], directorio["completo"])
        directorio["pagina"] = 1
    elif directorio.get("completo"):  # recorrido anterior terminado: empezar uno nuevo desde la página 1
        directorio = {"pagina": 1, "completo": False, "instituciones": directorio.get("instituciones", {})}

    def guardar_todo():
        REGISTRO.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
        DIRECTORIO.write_text(json.dumps(directorio, ensure_ascii=False, indent=1), encoding="utf-8")

    # Un solo recorrido, página por página: se guardan todas las instituciones (contacto) y, si alguna
    # tiene vacantes nuevas, se bajan sus bases en ese momento. Así las bases llegan primero (la lista
    # viene ordenada por vacantes) sin suponer ese orden, y se puede reanudar en la misma página.
    try:
        with sync_playwright() as p:
            page = pestana(p)
            n = directorio["pagina"]
            if n > 1:
                print(f"Reanudando en la página {n}")
            ir_a_pagina_instituciones(page, n)
            while True:
                n, total = pagina_actual(page, TABLA_INST)
                for inst in instituciones_de_la_pagina(page):
                    pendientes.discard(inst["institucion"])
                    directorio["instituciones"][inst["institucion"]] = {
                        "institucion": inst["institucion"], "correo": inst["correo"], "telefono": inst["telefono"],
                        "nuevas_vacantes": inst["nuevas"], "revisado": datetime.now().strftime("%Y-%m-%d %H:%M")}
                    if inst["nuevas"] > 0:
                        vacantes_de(page, inst, registro)
                        print(f"\n  {inst['institucion'][:60]} — {inst['nuevas']} vacantes, bases descargadas")
                        pausa(*PAUSA_ENTRE_AREAS)
                if solo_vacantes:
                    if not pendientes:
                        directorio["pagina"], directorio["completo"] = avance
                        guardar_todo()
                        break
                else:
                    directorio["pagina"] = n + 1
                    guardar_todo()
                print(f"  instituciones: pág. {n}/{total} — {len(directorio['instituciones'])} guardadas", end="\r")
                if not siguiente_pagina(page, TABLA_INST):
                    directorio["completo"] = True
                    guardar_todo()
                    break
    except SesionCaducada:
        if solo_vacantes:
            directorio["pagina"], directorio["completo"] = avance
        guardar_todo()
        print(f"\nLa sesión caducó en la página {directorio['pagina']}: inicia sesión de nuevo y repite el comando "
              "(continúa ahí y no repite los PDF ya bajados).")
    print(f"\n{len(registro)} vacantes, {len(directorio['instituciones'])} instituciones; Excel: {exportar(registro)}")


def cargar_directorio() -> dict:
    try:
        return json.loads(DIRECTORIO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"pagina": 1, "completo": False, "instituciones": {}}


if __name__ == "__main__":
    main()
