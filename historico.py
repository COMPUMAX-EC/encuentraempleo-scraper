"""Carga la serie histórica diaria en la base (tabla observaciones) desde el historial de git.

El sitio de Oportunidades (Computacion-UPEC/student) recolecta las plataformas a diario con GitHub Actions y solo
hace commit de cada JSON cuando sus ofertas cambian. Por eso, las ofertas publicadas un día son las del último commit
de ese JSON hasta ese día. Este script recorre ese historial y anota, para cada día desde el primer commit, qué
ofertas estaban publicadas. Las empresas remotas (buscador de BecasChamba) no se recolectan a diario: de ellas solo
se anotan los días con commit.

Además siembra observaciones con la primera y la última vez de las ofertas que ya estaban en la base (por ejemplo,
las de Encuentra Empleo, que no tienen historial diario).

Se puede correr las veces que haga falta: no duplica nada.

Uso:
    python historico.py              # carga todo el historial disponible
    python historico.py --desde 2026-10-16
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import bdd
import plataformas as pl

RAIZ = Path(__file__).parent
SITIO = Path(os.environ.get("STUDENT_REPO", RAIZ.parent / "student"))
RAMA_SITIO = "origin/main"

# clave de plataformas.py -> JSON del sitio
ARCHIVOS = {
    "inec": "inec-jobs.json",
    "cnt": "cnt-jobs.json",
    "concursos": "public-jobs.json",
    "petroecuador": "petroecuador-jobs.json",
    "celec": "celec-jobs.json",
    "bancos": "finance-jobs.json",
    "software": "tech-jobs.json",
    "privadas": "private-jobs.json",
}


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def commits(repo: Path, rama: str, ruta: str) -> list[tuple[str, datetime]]:
    """Commits que cambiaron `ruta`, del más antiguo al más reciente, con su fecha local."""
    salida = git(repo, "log", rama, "--reverse", "--format=%H %cI", "--", ruta)
    filas = []
    for linea in salida.splitlines():
        sha, cuando = linea.split(" ", 1)
        filas.append((sha, datetime.fromisoformat(cuando).astimezone().replace(tzinfo=None)))
    return filas


def leer_json(repo: Path, sha: str, ruta: str) -> dict:
    return json.loads(git(repo, "show", f"{sha}:{ruta}"))


def momento_del_dia(dia: date, commit: datetime) -> str:
    """Hora con la que se anota el día: la del commit si es de ese día; si no, el mediodía (sin pasar de ahora)."""
    if commit.date() == dia:
        m = commit
    else:
        m = min(datetime.combine(dia, datetime.min.time()).replace(hour=12), datetime.now())
    return m.isoformat(timespec="seconds")


def cargar_sitio(con, clave: str, desde: date | None) -> tuple[int, int, list[str]]:
    """Anota cada día del historial de una plataforma del sitio. Devuelve (días, observaciones, errores)."""
    nombre, leer = pl.PLATAFORMAS[clave]
    ruta = f"lib/data/{ARCHIVOS[clave]}"
    lista = commits(SITIO, RAMA_SITIO, ruta)
    if not lista:
        return 0, 0, [f"{ruta}: sin commits"]
    cache: dict[str, list[dict] | None] = {}
    errores = []

    def ofertas_de(sha: str) -> list[dict] | None:
        if sha not in cache:
            pl.LECTOR = lambda _archivo: leer_json(SITIO, sha, ruta)
            try:
                cache[sha] = leer()
            except Exception as e:  # noqa: BLE001 - una versión antigua con otro formato no detiene el resto
                cache[sha] = None
                errores.append(f"{sha[:7]}: {type(e).__name__}: {e}")
            finally:
                pl.LECTOR = None
        return cache[sha]

    dia, hoy = lista[0][1].date(), date.today()
    if desde and desde > dia:
        dia = desde
    dias = obs = 0
    i = 0
    while dia <= hoy:
        # último commit hasta el final de ese día
        while i + 1 < len(lista) and lista[i + 1][1].date() <= dia:
            i += 1
        sha, cuando = lista[i]
        if cuando.date() <= dia:
            ofertas = ofertas_de(sha)
            if ofertas is not None:
                bdd.guardar_ofertas(con, nombre, ofertas, momento_del_dia(dia, cuando))
                dias += 1
                obs += len(ofertas)
        dia += timedelta(days=1)
    return dias, obs, errores


def cargar_remotas(con, desde: date | None) -> tuple[int, int, list[str]]:
    """Empresas remotas: solo los días en que el buscador de BecasChamba dejó un commit."""
    nombre = pl.PLATAFORMAS["remotas"][0]
    ruta = "fuentes/candidatas.json"
    if not (pl.BECASCHAMBA / ".git").exists():
        return 0, 0, [f"no encuentro el repo de BecasChamba en {pl.BECASCHAMBA}"]
    por_dia: dict[date, tuple[str, datetime]] = {}
    for sha, cuando in commits(pl.BECASCHAMBA, "HEAD", ruta):
        por_dia[cuando.date()] = (sha, cuando)  # el último commit de cada día
    dias = obs = 0
    errores = []
    for dia, (sha, cuando) in sorted(por_dia.items()):
        if desde and dia < desde:
            continue
        try:
            ofertas = pl.remotas_de(leer_json(pl.BECASCHAMBA, sha, ruta))
        except Exception as e:  # noqa: BLE001
            errores.append(f"{sha[:7]}: {type(e).__name__}: {e}")
            continue
        bdd.guardar_ofertas(con, nombre, ofertas, cuando.isoformat(timespec="seconds"))
        dias += 1
        obs += len(ofertas)
    return dias, obs, errores


def sembrar_existentes(con) -> int:
    """Observaciones de la primera y la última vez de cada oferta que ya estaba en la base."""
    antes = con.execute("SELECT COUNT(*) FROM observaciones").fetchone()[0]
    for columna in ("primera_vez", "ultima_vez"):
        con.execute(f"""INSERT OR IGNORE INTO observaciones (plataforma, codigo, fecha)
                        SELECT plataforma, codigo, substr({columna}, 1, 10) FROM ofertas""")
    con.commit()
    return con.execute("SELECT COUNT(*) FROM observaciones").fetchone()[0] - antes


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde", type=date.fromisoformat, help="primer día a cargar (AAAA-MM-DD)")
    args = parser.parse_args()

    if not (SITIO / ".git").exists():
        sys.exit(f"No encuentro el repo del sitio en {SITIO} (define STUDENT_REPO).")
    git(SITIO, "fetch", "--quiet", "origin")

    with bdd.conectar() as con:
        print(f"Ofertas que ya estaban en la base: {sembrar_existentes(con)} observaciones nuevas")
        for clave in ARCHIVOS:
            dias, obs, errores = cargar_sitio(con, clave, args.desde)
            print(f"{pl.PLATAFORMAS[clave][0]}: {dias} días, {obs} observaciones")
            for e in errores:
                print(f"   ⚠ {e}")
        dias, obs, errores = cargar_remotas(con, args.desde)
        print(f"{pl.PLATAFORMAS['remotas'][0]}: {dias} días con commit, {obs} observaciones")
        for e in errores:
            print(f"   ⚠ {e}")
        total = con.execute("SELECT COUNT(*), MIN(fecha), MAX(fecha) FROM observaciones").fetchone()
    print(f"\nTabla observaciones: {total[0]} filas, del {total[1]} al {total[2]}")


if __name__ == "__main__":
    main()
