"""Publica en el sitio de Oportunidades de Computación UPEC las ofertas de TI de Encuentra Empleo.

Lee la base local (salida/ofertas.db), arma un resumen de las ofertas "TI directo" (cargo, empresa, ubicación,
remuneración, cierre y sector; los requisitos completos quedan solo en tu base) y lo escribe en
lib/data/encuentra-empleo-jobs.json del repositorio del sitio. Si cambió, abre un PR y lo fusiona cuando pasa
el check de Vercel: el sitio se actualiza solo en unos minutos.

Uso:
    python publicar_sitio.py               # exporta y publica (PR + fusión automática)
    python publicar_sitio.py --solo-exportar   # solo escribe el JSON, sin git

Ruta del sitio: variable de entorno SITIO_REPO (por defecto, ../student).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import bdd

RAIZ = Path(__file__).parent
SITIO = Path(os.environ.get("SITIO_REPO", RAIZ.parent / "student"))
DESTINO = "lib/data/encuentra-empleo-jobs.json"
PORTAL = "https://encuentraempleo.trabajo.gob.ec/socioEmpleo-war/paginas/index.jsf"
DIAS_HISTORIAL = 90  # ofertas vistas en este plazo
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9,
         "oct": 10, "nov": 11, "dic": 12}


def fecha_iso(texto: str | None) -> str | None:
    """"05-nov-2026" -> "2026-11-05"."""
    m = re.match(r"(\d{1,2})-([a-z]+)\.?-(\d{4})", (texto or "").strip().lower())
    if not m or m.group(2) not in MESES:
        return None
    return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1))).isoformat()


def exportar() -> dict:
    limite = (datetime.now() - timedelta(days=DIAS_HISTORIAL)).isoformat(timespec="seconds")
    with bdd.conectar() as con:
        filas = con.execute("""
            SELECT codigo, datos, primera_vez, ultima_vez FROM ofertas
            -- Solo "TI directo": "TI afín" incluye ventas y atención al cliente que no son roles de TI
            WHERE plataforma = 'Encuentra Empleo' AND ultima_vez >= ? AND perfil_ti = 'TI directo'
            """, (limite,)).fetchall()
        ultima = con.execute("""SELECT fin FROM actualizaciones WHERE plataforma = 'Encuentra Empleo'
                                AND estado IN ('ok', 'parcial') ORDER BY id DESC LIMIT 1""").fetchone()
    trabajos = []
    for f in filas:
        o = json.loads(f["datos"])
        trabajos.append({
            "id": f["codigo"],
            "title": o.get("cargo"),
            "company": o.get("empresa") or None,
            "location": o.get("ubicacion") or None,
            "salary": o.get("remuneracion") or None,
            "contract": o.get("tipo_contrato") or None,
            "employerType": o.get("tipo_empleador") or None,
            "sector": o.get("sector") or None,
            "profile": o.get("perfil_ti"),
            "applicableFromIT": o.get("postulable_ti") == "Sí",
            "closesOn": fecha_iso(o.get("fecha_fin")),
            "firstSeen": f["primera_vez"][:10],
            "lastSeen": f["ultima_vez"][:10],
        })
    trabajos.sort(key=lambda t: (t["closesOn"] or "", t["title"] or ""), reverse=True)
    return {"source": PORTAL, "updatedAt": ultima["fin"] if ultima else None, "jobs": trabajos}


def git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(SITIO), *args], check=True, text=True, encoding="utf-8",
                       capture_output=True)
    return r.stdout.strip()


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=SITIO, text=True, encoding="utf-8", capture_output=True)


def publicar(datos: dict) -> str:
    if not (SITIO / ".git").exists():
        raise RuntimeError(f"No encuentro el repositorio del sitio en {SITIO} (define SITIO_REPO).")
    if git("status", "--porcelain"):
        raise RuntimeError("El repositorio del sitio tiene cambios sin guardar: no se publica para no mezclarlos.")
    original = git("rev-parse", "--abbrev-ref", "HEAD")
    try:
        git("checkout", "-q", "main")
        git("pull", "-q", "--ff-only")
        ruta = SITIO / DESTINO
        nuevo = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
        anterior = ruta.read_text(encoding="utf-8") if ruta.exists() else ""
        # updatedAt cambia en cada corrida: solo se publica si cambiaron las ofertas
        if anterior and json.loads(anterior).get("jobs") == datos["jobs"]:
            return "Sin ofertas nuevas ni cambios: no hace falta publicar."
        ruta.write_text(nuevo, encoding="utf-8", newline="\n")
        sello = datetime.now().strftime("%Y-%m-%d-%H%M")
        rama = f"data/encuentra-empleo-{sello}"
        git("checkout", "-q", "-b", rama)
        git("add", DESTINO)
        git("commit", "-q", "-m", f"Update Encuentra Empleo IT jobs ({sello})")
        git("push", "-q", "-u", "origin", rama)
        r = gh("pr", "create", "--base", "main", "--head", rama, "--title", f"Update Encuentra Empleo IT jobs ({sello})",
               "--body", f"{len(datos['jobs'])} ofertas de TI de Encuentra Empleo, exportadas con `publicar_sitio.py` "
                         "desde la base local del scraper (resumen; se postula en el portal oficial).")
        if r.returncode:
            raise RuntimeError(f"No se pudo crear el PR: {r.stderr.strip()}")
        print(f"PR creado: {r.stdout.strip()} · esperando el check de Vercel…", flush=True)
        # Vercel tarda en registrar su check: sin check no se fusiona (antes de vigilarlo hay que verlo aparecer)
        for _ in range(60):  # Vercel encola sus builds: hasta ~15 min
            time.sleep(15)
            r = gh("pr", "checks", rama)
            if "no checks reported" not in (r.stdout + r.stderr):
                break
        else:
            raise RuntimeError(f"Vercel no registró su check: el PR {rama} queda abierto para revisarlo.")
        if gh("pr", "checks", rama, "--watch", "--interval", "20").returncode:
            raise RuntimeError(f"El check de Vercel falló: el PR {rama} queda abierto para revisarlo.")
        r = gh("pr", "merge", rama, "--merge", "--delete-branch")
        if r.returncode:
            raise RuntimeError(f"No se pudo fusionar el PR: {r.stderr.strip()}")
        return f"Publicado: {len(datos['jobs'])} ofertas de TI en la página (se ve en unos minutos)."
    finally:
        try:
            git("checkout", "-q", original)
            if original == "main":
                git("pull", "-q", "--ff-only")
        except subprocess.CalledProcessError:
            pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo-exportar", action="store_true", help="solo escribe el JSON en el sitio, sin git")
    args = parser.parse_args()
    datos = exportar()
    abiertas = sum(1 for t in datos["jobs"] if t["closesOn"] and t["closesOn"] >= date.today().isoformat())
    print(f"{len(datos['jobs'])} ofertas de TI ({abiertas} abiertas) · última actualización {datos['updatedAt']}")
    if args.solo_exportar:
        (SITIO / DESTINO).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Escrito {SITIO / DESTINO}")
        return
    try:
        print(publicar(datos))
    except (RuntimeError, subprocess.CalledProcessError) as e:
        detalle = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        sys.exit(f"No se publicó: {detalle}")


if __name__ == "__main__":
    main()
