"""Publica en el sitio de Oportunidades de Computación UPEC las ofertas de TI de Encuentra Empleo.

Lee la base local (salida/ofertas.db), arma un resumen de las ofertas "TI directo" y de los cargos de entrada de
cualquier área (asistentes, auxiliares, pasantes: sección Para recién graduados) (cargo, empresa, ubicación,
remuneración, cierre y sector; los requisitos completos quedan solo en tu base) y lo escribe en
lib/data/encuentra-empleo-jobs.json del repositorio del sitio. También agrega al historial de concursos públicos
(lib/data/public-jobs.json) las vacantes de TI y las de entrada que bajó publicas.py, con el enlace a sus bases, y registra en
lib/data/scrape-status.json el día de la última revisión de las plataformas locales. Si algo cambió, abre un PR y
lo fusiona cuando pasa el check de Vercel: el sitio se actualiza solo en unos minutos.

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
from publicas import AREA_TI, BASES, BASES_GITHUB, REGISTRO
from sectores import TI_CARGO, normalizar

RAIZ = Path(__file__).parent
SITIO = Path(os.environ.get("SITIO_REPO", RAIZ.parent / "student"))
DESTINO = "lib/data/encuentra-empleo-jobs.json"
CUENTA_GITHUB = "COMPUMAX-EC"  # cuenta de gh con permiso para publicar en el repositorio del sitio
CONCURSOS = "lib/data/public-jobs.json"
ESTADO = "lib/data/scrape-status.json"
# Los escribe portales_navegador.py (El Rosado, CACPECO): se publican junto con lo demás
PORTALES = ("lib/data/private-jobs.json", "lib/data/finance-jobs.json")
# Plataformas que solo se revisan en este computador: clave en scrape-status.json -> nombre en la base local
LOCALES = {"Encuentra-Empleo": "Encuentra Empleo", "Remotas": "Empresas remotas (Get on Board, Greenhouse, Lever)"}
PORTAL = "https://encuentraempleo.trabajo.gob.ec/socioEmpleo-war/paginas/index.jsf"
DIAS_HISTORIAL = 90  # ofertas vistas en este plazo
# Cargo de entrada (para recién graduados): mismo criterio que scripts/lib/entry-roles.mjs del sitio
CARGO_ENTRADA = re.compile(r"\bauxiliar(es)?\b|\basistentes?\b|\bayudantes?\b|\bpasant(e|es|[ií]as?)\b|\bpracticantes?\b|"
                           r"pr[aá]cticas (pre)?profesionales|\btrainees?\b|\bjunior\b|\bjr\b|\baprendiz|\bbecari[oa]s?\b|"
                           r"reci[eé]n graduad|sin experiencia|primer empleo|servidor(a)? p[uú]blic[oa] de apoyo|"
                           r"\brecepcionistas?\b|\bcajer[oa]s?\b|\bdigitador(es|a)?\b|\bnotificador(es|a)?\b", re.I)
SENIOR = re.compile(r"\b(senior|sr)\b", re.I)
MESES_ENTRADA = 12  # concursos cuyas bases piden hasta un año de experiencia
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9,
         "oct": 10, "nov": 11, "dic": 12}


def fecha_iso(texto: str | None) -> str | None:
    """"05-nov-2026" -> "2026-11-05"."""
    m = re.match(r"(\d{1,2})-([a-z]+)\.?-(\d{4})", (texto or "").strip().lower())
    if not m or m.group(2) not in MESES:
        return None
    return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1))).isoformat()


def es_entrada(cargo: str | None) -> bool:
    return bool(cargo) and bool(CARGO_ENTRADA.search(cargo)) and not SENIOR.search(cargo)


def meses_experiencia(texto: str | None) -> int | None:
    """"2 años 6 meses" (de las bases) -> 30."""
    m = re.match(r"(\d+) a\S+ (\d+) meses", texto or "")
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def exportar() -> dict:
    limite = (datetime.now() - timedelta(days=DIAS_HISTORIAL)).isoformat(timespec="seconds")
    with bdd.conectar() as con:
        filas = con.execute("""
            SELECT codigo, datos, primera_vez, ultima_vez FROM ofertas
            -- "TI directo" ("TI afín" incluye ventas y atención al cliente que no son roles de TI) y, aparte,
            -- los cargos de entrada de cualquier área, para la sección Para recién graduados
            WHERE plataforma = 'Encuentra Empleo' AND ultima_vez >= ?
            """, (limite,)).fetchall()
        ultima = con.execute("""SELECT fin FROM actualizaciones WHERE plataforma = 'Encuentra Empleo'
                                AND estado IN ('ok', 'parcial') ORDER BY id DESC LIMIT 1""").fetchone()
    trabajos = []
    for f in filas:
        o = json.loads(f["datos"])
        entrada = es_entrada(o.get("cargo"))
        if o.get("perfil_ti") != "TI directo" and not entrada:
            continue
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
            **({"entryLevel": True} if entrada else {}),
            "closesOn": fecha_iso(o.get("fecha_fin")),
            "firstSeen": f["primera_vez"][:10],
            "lastSeen": f["ultima_vez"][:10],
        })
    trabajos.sort(key=lambda t: (t["closesOn"] or "", t["title"] or ""), reverse=True)
    return {"source": PORTAL, "updatedAt": ultima["fin"] if ultima else None, "jobs": trabajos}


def json_sitio(datos: dict) -> str:
    """Mismo formato que JSON.stringify(datos, null, 2) de los recolectores del sitio."""
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def exportar_concursos(actual: dict) -> dict:
    """Agrega al historial de concursos del sitio las vacantes de TI de publicas.json, con el enlace a sus bases.

    Entra el cargo de TI por su título (como en el sitio), el que no lo es pero cuyas bases aceptan una carrera de TI
    (acceptsIT) y el de entrada (asistente, auxiliar... o que pide hasta un año de experiencia), para la sección Para
    recién graduados. El resto de vacantes se queda solo en la base local."""
    trabajos = {t["id"]: t for t in actual.get("jobs", [])}
    for v in json.loads(REGISTRO.read_text(encoding="utf-8")).values():
        es_ti = bool(re.search(TI_CARGO, normalizar(v["puesto"])))
        acepta = bool(re.search(AREA_TI, normalizar(v.get("area_conocimiento", ""))))
        meses = meses_experiencia(v.get("experiencia_bases"))
        entrada = es_entrada(v["puesto"]) or (meses is not None and meses <= MESES_ENTRADA)
        if not (es_ti or acepta or entrada):
            continue
        visto = v.get("primera_vez") or v["cierre"][:10]
        nuevo = {
            "id": v["codigo"], "institution": v["institucion"], "title": v["puesto"],
            "vacancies": int(v["vacantes"]) if str(v["vacantes"]).isdigit() else 1,
            "salary": float(v["rmu"]) if v.get("rmu") else None, "city": v.get("ubicacion") or "",
            "stage": v.get("etapa") or "", "opensAt": None,
            "closesAt": v["cierre"][:16].replace(" ", "T") + ":00-05:00" if v.get("cierre") else None,
            "isIT": es_ti, "firstSeen": visto, "lastSeen": visto,
            **trabajos.get(v["codigo"], {}),  # lo que ya vio el recolector del sitio manda (apertura, isIT, fechas)
        }
        if acepta and not nuevo["isIT"]:
            nuevo["acceptsIT"] = True
        if entrada:
            nuevo["entryLevel"] = True
        if meses is not None:
            nuevo["minExperienceMonths"] = meses
        if v.get("archivo_bases") and (BASES / v["archivo_bases"]).exists():
            nuevo["basesUrl"] = BASES_GITHUB + v["archivo_bases"]
        trabajos[v["codigo"]] = nuevo
    return {**actual, "jobs": sorted(trabajos.values(), key=lambda t: t.get("closesAt") or "", reverse=True)}


def exportar_estado(actual: dict) -> dict:
    """Día de la última revisión de las plataformas que solo corren en este computador."""
    plataformas = dict(actual.get("platforms", {}))
    with bdd.conectar() as con:
        for clave, nombre in LOCALES.items():
            fila = con.execute("SELECT fin, estado FROM actualizaciones WHERE plataforma = ? ORDER BY id DESC LIMIT 1",
                               (nombre,)).fetchone()
            if fila:
                ok = fila["estado"] in ("ok", "parcial")
                dia = fila["fin"][:10]
                plataformas[clave] = {"lastRun": dia, "lastSuccess": dia if ok else plataformas.get(clave, {}).get("lastSuccess"),
                                      "ok": ok}
    if REGISTRO.exists():  # publicas.py guarda el registro al terminar cada página
        dia = datetime.fromtimestamp(REGISTRO.stat().st_mtime).strftime("%Y-%m-%d")
        plataformas["Encuentra-Empleo-bases"] = {"lastRun": dia, "lastSuccess": dia, "ok": True}
    return {"platforms": dict(sorted(plataformas.items()))}


def escribir_sitio(datos: dict) -> None:
    """Escribe en el sitio las ofertas privadas de TI, el historial de concursos de TI y el estado de las plataformas."""
    ruta = SITIO / DESTINO
    # updatedAt cambia en cada corrida: solo se reescribe si cambiaron las ofertas
    if not ruta.exists() or json.loads(ruta.read_text(encoding="utf-8")).get("jobs") != datos["jobs"]:
        ruta.write_text(json_sitio(datos), encoding="utf-8", newline="\n")
    for archivo, exportar_archivo in ((CONCURSOS, exportar_concursos), (ESTADO, exportar_estado)):
        ruta = SITIO / archivo
        actual = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
        nuevo = json_sitio(exportar_archivo(actual))
        if not ruta.exists() or ruta.read_text(encoding="utf-8").replace("\r\n", "\n") != nuevo:
            ruta.write_text(nuevo, encoding="utf-8", newline="\n")


def entorno_github() -> dict:
    """Usa la sesión de gh de CUENTA_GITHUB (con acceso al sitio) aunque la cuenta activa sea otra; no cambia la activa."""
    r = subprocess.run(["gh", "auth", "token", "--user", CUENTA_GITHUB], capture_output=True, text=True)
    return {**os.environ, "GH_TOKEN": r.stdout.strip()} if r.returncode == 0 else dict(os.environ)


ENTORNO = entorno_github()
# git se autentica con el mismo token de gh, no con el administrador de credenciales de Windows
GIT_CREDENCIALES = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]


def git(*args: str) -> str:
    r = subprocess.run(["git", *GIT_CREDENCIALES, "-C", str(SITIO), *args], check=True, text=True, encoding="utf-8",
                       capture_output=True, env=ENTORNO)
    return r.stdout.strip()


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=SITIO, text=True, encoding="utf-8", capture_output=True, env=ENTORNO)


def publicar(datos: dict) -> str:
    if not (SITIO / ".git").exists():
        raise RuntimeError(f"No encuentro el repositorio del sitio en {SITIO} (define SITIO_REPO).")
    if git("status", "--porcelain"):
        raise RuntimeError("El repositorio del sitio tiene cambios sin guardar: no se publica para no mezclarlos.")
    original = git("rev-parse", "--abbrev-ref", "HEAD")
    try:
        git("checkout", "-q", "main")
        git("pull", "-q", "--ff-only")
        escribir_sitio(datos)
        if not git("status", "--porcelain"):
            return "Sin ofertas nuevas ni cambios: no hace falta publicar."
        sello = datetime.now().strftime("%Y-%m-%d-%H%M")
        rama = f"data/encuentra-empleo-{sello}"
        git("checkout", "-q", "-b", rama)
        git("add", DESTINO, CONCURSOS, ESTADO, *PORTALES)
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
    de_ti = sum(t["profile"] == "TI directo" for t in datos["jobs"])
    print(f"{len(datos['jobs'])} ofertas ({de_ti} de TI, {len(datos['jobs']) - de_ti} solo de entrada; {abiertas} abiertas)"
          f" · última actualización {datos['updatedAt']}")
    if args.solo_exportar:
        escribir_sitio(datos)
        print(f"Escritos {DESTINO}, {CONCURSOS} y {ESTADO} en {SITIO}")
        return
    try:
        print(publicar(datos))
    except (RuntimeError, subprocess.CalledProcessError) as e:
        detalle = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        sys.exit(f"No se publicó: {detalle}")


if __name__ == "__main__":
    main()
