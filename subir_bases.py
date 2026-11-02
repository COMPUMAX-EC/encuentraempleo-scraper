"""Sube a GitHub los PDF de bases de los concursos públicos, para tener un enlace público de cada vacante.

Los PDF quedan como archivos del release "bases-concursos" de este repositorio (no entran al historial de
git). Solo sube los que faltan. Usa la sesión de la CLI de GitHub (gh) de este computador.

Uso:  python subir_bases.py
El enlace de cada PDF es BASES_GITHUB + nombre del archivo (lo usan publicas.py y historial.py).
"""

import json
import os
import subprocess
import sys

from publicas import BASES, BASES_GITHUB, RELEASE_BASES, REPO_GITHUB


def token_del_dueno() -> dict:
    """Usa la sesión de gh del dueño del repositorio aunque la cuenta activa sea otra (no cambia la activa)."""
    dueno = REPO_GITHUB.split("/")[0]
    r = subprocess.run(["gh", "auth", "token", "--user", dueno], capture_output=True, text=True)
    return {**os.environ, "GH_TOKEN": r.stdout.strip()} if r.returncode == 0 else dict(os.environ)


ENTORNO = token_del_dueno()


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO_GITHUB], capture_output=True, text=True, encoding="utf-8",
                          env=ENTORNO)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    r = gh("release", "view", RELEASE_BASES, "--json", "assets")
    if r.returncode:
        r = gh("release", "create", RELEASE_BASES, "--target", "main", "--title", "Bases de concursos públicos",
               "--notes", "PDF de las bases de cada concurso de méritos y oposición de Encuentra Empleo. "
                          "Los sube subir_bases.py; el nombre empieza con el código de la vacante.")
        if r.returncode:
            sys.exit(f"No se pudo crear el release ({r.stderr.strip()}). ¿gh está instalado y con sesión? (gh auth status)")
        subidos = set()
    else:
        subidos = {a["name"] for a in json.loads(r.stdout)["assets"]}

    faltan = sorted(p for p in BASES.glob("*.pdf") if p.name not in subidos)
    for i in range(0, len(faltan), 20):  # de 20 en 20 para no armar una línea de comandos enorme
        lote = faltan[i:i + 20]
        r = gh("release", "upload", RELEASE_BASES, *map(str, lote))
        if r.returncode:
            sys.exit(f"Falló la subida: {r.stderr.strip()}")
        print(f"  subidos {i + len(lote)}/{len(faltan)}", flush=True)
    print(f"{len(faltan)} PDF nuevos, {len(subidos) + len(faltan)} en total: {BASES_GITHUB}")


if __name__ == "__main__":
    main()
