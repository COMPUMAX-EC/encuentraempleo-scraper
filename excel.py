"""Exporta las ofertas a un único Excel con hojas: Resumen, TI directo, TI afín, Todas y Requisitos.

El Resumen usa fórmulas COUNTIFS sobre la hoja "Todas", así que si se filtra o corrige
el sector de una oferta a mano, los totales se actualizan solos.
"""

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from sectores import palabras_frecuentes

# (clave en la oferta, encabezado, ancho de columna)
COLUMNAS = [
    ("codigo", "Código", 22),
    ("cargo", "Cargo", 40),
    ("empresa", "Empresa", 28),
    ("sector", "Sector", 30),
    ("perfil_ti", "Perfil TI", 11),
    ("postulable_ti", "Postulable desde TI", 22),
    ("area_laboral", "Área declarada", 24),
    ("area_estudios", "Área de estudios", 24),
    ("ubicacion", "Provincia - Ciudad", 28),
    ("remuneracion", "Remuneración", 15),
    ("instruccion", "Instrucción", 22),
    ("experiencia", "Experiencia", 14),
    ("conocimientos", "Conocimientos del cargo", 60),
    ("actividades", "Actividades", 60),
    ("capacitacion", "Capacitación", 14),
    ("tipo_contrato", "Contrato", 16),
    ("jornada", "Jornada", 22),
    ("vacantes", "Vacantes", 9),
    ("tipo_empleador", "Empleador", 14),
    ("fecha_inicio", "Publicada", 12),
    ("fecha_fin", "Cierra", 12),
    ("publicado_hace", "Hace", 10),
    ("region_amazonica", "En Amazonía", 11),
    ("requisito_amazonico", "Exige residente amazónico", 13),
    ("info_adicional", "Información adicional", 50),
]
COLUMNAS_TI = ["codigo", "cargo", "perfil_ti", "postulable_ti", "empresa", "sector", "area_estudios", "ubicacion",
               "remuneracion", "instruccion", "experiencia", "conocimientos", "fecha_fin", "info_adicional"]

FUENTE = "Arial"
ENCABEZADO = PatternFill("solid", start_color="1F4E78")
TI_DIRECTO = PatternFill("solid", start_color="E2EFDA")
TI_AFIN = PatternFill("solid", start_color="FFF2CC")
BORDE = Border(bottom=Side(style="thin", color="BFBFBF"))


def _encabezados(ws, titulos: list[str], anchos: list[int]) -> None:
    for c, (t, w) in enumerate(zip(titulos, anchos), start=1):
        celda = ws.cell(row=1, column=c, value=t)
        celda.font = Font(name=FUENTE, bold=True, color="FFFFFF")
        celda.fill = ENCABEZADO
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "B2"


def _tabla_ofertas(ws, ofertas: list[dict], claves: list[str]) -> None:
    defs = {k: (t, w) for k, t, w in COLUMNAS}
    _encabezados(ws, [defs[k][0] for k in claves], [defs[k][1] for k in claves])
    largo = {"conocimientos", "actividades", "info_adicional"}
    for f, o in enumerate(ofertas, start=2):
        relleno = TI_DIRECTO if o.get("perfil_ti") == "TI directo" else TI_AFIN if o.get("perfil_ti") == "TI afín" else None
        for c, k in enumerate(claves, start=1):
            valor = o.get(k, "")
            if k == "vacantes" and str(valor).isdigit():
                valor = int(valor)
            celda = ws.cell(row=f, column=c, value=valor)
            celda.font = Font(name=FUENTE, size=10)
            celda.alignment = Alignment(vertical="top", wrap_text=k in largo)
            celda.border = BORDE
            if relleno and k in ("codigo", "cargo", "perfil_ti"):
                celda.fill = relleno
    ws.auto_filter.ref = f"A1:{get_column_letter(len(claves))}{len(ofertas) + 1}"


def _resumen(ws, ofertas: list[dict], n: int) -> None:
    """Conteos por sector con COUNTIFS sobre la hoja Todas (columnas según COLUMNAS)."""
    letra = {k: get_column_letter(i) for i, (k, _, _) in enumerate(COLUMNAS, start=1)}
    rango = lambda k: f"Todas!${letra[k]}$2:${letra[k]}${n + 1}"  # noqa: E731

    ws["A1"] = "Ofertas de Encuentra Empleo por sector"
    ws["A1"].font = Font(name=FUENTE, bold=True, size=14)
    ws["A2"] = ("Conteos calculados con fórmulas sobre la hoja «Todas». TI directo: cargo o funciones de TI. "
                "TI afín: habilidades transferibles (datos, ERP/CRM, web, automatización, CCTV...).")
    ws["A2"].font = Font(name=FUENTE, italic=True, size=9, color="595959")

    titulos = ["Sector", "Ofertas", "TI directo", "TI afín", "Postulables desde TI", "En Amazonía",
               "Exige residente amazónico"]
    for c, t in enumerate(titulos, start=1):
        celda = ws.cell(row=4, column=c, value=t)
        celda.font = Font(name=FUENTE, bold=True, color="FFFFFF")
        celda.fill = ENCABEZADO
        celda.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    for c, w in enumerate([42, 10, 11, 10, 13, 12, 14], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[4].height = 30

    sectores = [s for s, _ in Counter(o["sector"] for o in ofertas).most_common()]
    fila = 5
    for s in sectores:
        ws.cell(row=fila, column=1, value=s)
        sec = f'{rango("sector")},$A{fila}'
        ws.cell(row=fila, column=2, value=f"=COUNTIFS({sec})")
        ws.cell(row=fila, column=3, value=f'=COUNTIFS({sec},{rango("perfil_ti")},"TI directo")')
        ws.cell(row=fila, column=4, value=f'=COUNTIFS({sec},{rango("perfil_ti")},"TI afín")')
        ws.cell(row=fila, column=5, value=f'=COUNTIFS({sec},{rango("postulable_ti")},"Sí")')
        ws.cell(row=fila, column=6, value=f'=COUNTIFS({sec},{rango("region_amazonica")},"Sí")')
        ws.cell(row=fila, column=7, value=f'=COUNTIFS({sec},{rango("requisito_amazonico")},"Sí")')
        for c in range(1, 8):
            ws.cell(row=fila, column=c).font = Font(name=FUENTE, size=10)
            ws.cell(row=fila, column=c).border = BORDE
        fila += 1
    ws.cell(row=fila, column=1, value="Total").font = Font(name=FUENTE, bold=True)
    for c in range(2, 8):
        col = get_column_letter(c)
        celda = ws.cell(row=fila, column=c, value=f"=SUM({col}5:{col}{fila - 1})")
        celda.font = Font(name=FUENTE, bold=True)


def _requisitos(ws, ofertas: list[dict]) -> None:
    """Lo más pedido por sector (texto calculado al exportar), para preparar un perfil por sector."""
    titulos = ["Sector", "Ofertas", "Instrucción más pedida", "Experiencia más pedida",
               "Área de estudios más pedida", "Remuneraciones más comunes", "Términos más repetidos"]
    _encabezados(ws, titulos, [34, 9, 38, 30, 38, 34, 70])
    por_sector: dict[str, list[dict]] = {}
    for o in ofertas:
        por_sector.setdefault(o["sector"], []).append(o)

    def top(os, campo, k=3):
        return "; ".join(f"{v} ({c})" for v, c in Counter(o.get(campo) for o in os if o.get(campo)).most_common(k))

    orden = sorted(por_sector.items(), key=lambda kv: -len(kv[1]))
    for f, (s, os) in enumerate(orden, start=2):
        valores = [s, len(os), top(os, "instruccion"), top(os, "experiencia"), top(os, "area_estudios"),
                   top(os, "remuneracion"), ", ".join(p for p, _ in palabras_frecuentes(os, 12))]
        for c, v in enumerate(valores, start=1):
            celda = ws.cell(row=f, column=c, value=v)
            celda.font = Font(name=FUENTE, size=10)
            celda.alignment = Alignment(vertical="top", wrap_text=True)
            celda.border = BORDE
    ws.cell(row=len(orden) + 3, column=1,
            value="Nota: el número entre paréntesis es cuántas ofertas del sector lo piden.").font = Font(
        name=FUENTE, italic=True, size=9, color="595959")


def exportar_excel(ofertas: list[dict], ruta: Path) -> None:
    wb = Workbook()
    _resumen(wb.active, ofertas, len(ofertas))
    wb.active.title = "Resumen"
    ti = [o for o in ofertas if o.get("perfil_ti")]
    _tabla_ofertas(wb.create_sheet("Postulables desde TI"), [o for o in ti if o["postulable_ti"] == "Sí"], COLUMNAS_TI)
    _tabla_ofertas(wb.create_sheet("TI - revisar requisitos"), [o for o in ti if o["postulable_ti"] != "Sí"], COLUMNAS_TI)
    _tabla_ofertas(wb.create_sheet("Todas"), ofertas, [k for k, _, _ in COLUMNAS])
    _requisitos(wb.create_sheet("Requisitos por sector"), ofertas)
    wb.calculation.fullCalcOnLoad = True  # Excel calcula las fórmulas del Resumen al abrir
    wb.save(ruta)
