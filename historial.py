"""Frecuencia real de vacantes TI por institución, a partir de todo lo que publicas.py ha ido guardando.

publicas.json acumula cada vacante por su código y no borra las cerradas, así que corrida tras corrida
se va formando el historial. Este script cuenta, por institución, cuántas vacantes TI y cuántas en total
ha publicado, en cuántas semanas distintas, y cuándo fue la última.

Uso:
    python historial.py            # registra la corrida de hoy y genera salida/frecuencia_ti.xlsx
    python historial.py excel      # solo rehace el Excel, sin registrar corrida
"""

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from publicas import AREA_TI, REGISTRO, cargar_directorio
from scraper import DATOS, SALIDA, normalizar

CORRIDAS = DATOS / "corridas_publicas.json"  # fechas en que se corrió publicas.py (semanas observadas)


def semana(fecha: str) -> str:
    a, s, _ = date.fromisoformat(fecha[:10]).isocalendar()
    return f"{a}-S{s:02d}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    registro = json.loads(REGISTRO.read_text(encoding="utf-8"))
    try:
        corridas = json.loads(CORRIDAS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        corridas = []
    if sys.argv[1:] != ["excel"]:
        hoy = date.today().isoformat()
        if hoy not in corridas:
            corridas.append(hoy)
            CORRIDAS.write_text(json.dumps(sorted(corridas), indent=1), encoding="utf-8")

    stats = defaultdict(lambda: {"ti": 0, "total": 0, "semanas_ti": set(), "semanas": set(), "ultima_ti": "",
                                 "puestos_ti": []})
    for v in registro.values():
        fecha = v.get("primera_vez") or v["cierre"][:10]  # las vacantes anteriores al historial no traen primera_vez
        s = stats[v["institucion"]]
        n = int(v["vacantes"]) if str(v["vacantes"]).isdigit() else 1
        s["total"] += n
        s["semanas"].add(semana(fecha))
        if re.search(AREA_TI, normalizar(v.get("area_conocimiento", ""))):
            s["ti"] += n
            s["semanas_ti"].add(semana(fecha))
            s["ultima_ti"] = max(s["ultima_ti"], fecha)
            s["puestos_ti"].append(v["puesto"])

    contactos = cargar_directorio()["instituciones"]
    filas = sorted(stats.items(), key=lambda kv: (-len(kv[1]["semanas_ti"]), -kv[1]["ti"], -kv[1]["total"], kv[0]))
    observadas = len({semana(c) for c in corridas}) or 1

    columnas = [("Institución", 60), ("Semanas con vacantes TI", 12), ("Vacantes TI", 10),
                ("Semanas con vacantes", 12), ("Vacantes totales", 10), ("% semanas con TI", 10),
                ("Última vacante TI", 14), ("Puestos TI publicados", 60), ("Correo", 38), ("Teléfono", 18)]
    wb = Workbook()
    ws = wb.active
    ws.title = "Frecuencia TI"
    for c, (titulo, ancho) in enumerate(columnas, start=1):
        celda = ws.cell(row=1, column=c, value=titulo)
        celda.font = Font(name="Arial", bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", start_color="1F4E78")
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = ancho
    for r, (inst, s) in enumerate(filas, start=2):
        contacto = contactos.get(inst, {})
        valores = [inst, len(s["semanas_ti"]), s["ti"], len(s["semanas"]), s["total"],
                   len(s["semanas_ti"]) / observadas, s["ultima_ti"], "; ".join(sorted(set(s["puestos_ti"]))),
                   contacto.get("correo", ""), contacto.get("telefono", "")]
        for c, valor in enumerate(valores, start=1):
            celda = ws.cell(row=r, column=c, value=valor)
            celda.font = Font(name="Arial", size=10)
            celda.alignment = Alignment(vertical="top", wrap_text=c == 8)
        ws.cell(row=r, column=6).number_format = "0%"
        if s["ti"]:
            ws.cell(row=r, column=1).fill = PatternFill("solid", start_color="C6EFCE")
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columnas))}{len(filas) + 1}"
    nota = ws.cell(row=len(filas) + 3, column=1, value=(
        f"Semanas observadas: {observadas} ({', '.join(sorted(corridas)) or 'ninguna'}). "
        f"Generado {datetime.now():%Y-%m-%d %H:%M}. La frecuencia es más fiable mientras más semanas haya."))
    nota.font = Font(name="Arial", italic=True, color="595959")

    ruta = SALIDA / "frecuencia_ti.xlsx"
    wb.save(ruta)
    con_ti = sum(1 for _, s in filas if s["ti"])
    print(f"{len(filas)} instituciones con vacantes, {con_ti} con vacantes TI, {observadas} semana(s) observadas; "
          f"Excel: {ruta}")


if __name__ == "__main__":
    main()
