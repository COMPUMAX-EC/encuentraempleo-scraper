"""Las demás plataformas de empleo, en la misma base que Encuentra Empleo (salida/ofertas.db).

Dos tipos de fuente:
  - Las que recolecta a diario el sitio de Oportunidades de Computación UPEC (GitHub Actions y el recolector
    nocturno de CNT): se descargan sus JSON públicos de GitHub. Rápido y sin navegador.
  - Empresas con vacantes remotas o en Ecuador (Get on Board, Workable, Greenhouse, Lever): se ejecuta el buscador de
    BecasChamba (scripts/buscar-ofertas.mjs) si está en la carpeta vecina.

Cada actualización queda en el registro de la base, igual que las de Encuentra Empleo.

Uso:
    python plataformas.py lista          # plataformas disponibles
    python plataformas.py inec cnt       # actualiza las indicadas
    python plataformas.py todas          # actualiza todas
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import bdd

RAIZ = Path(__file__).parent
DATOS_SITIO = "https://raw.githubusercontent.com/Computacion-UPEC/student/main/lib/data/"
BECASCHAMBA = Path(os.environ.get("BECASCHAMBA_REPO", RAIZ.parent / "BecasChamba"))


def descargar(archivo: str) -> dict:
    req = urllib.request.Request(DATOS_SITIO + archivo, headers={"User-Agent": "encuentraempleo-scraper"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def ti(es_ti: bool) -> str:
    return "TI directo" if es_ti else ""


def fecha(valor: str | None) -> str | None:
    """Deja solo AAAA-MM-DD de una fecha ISO."""
    return valor[:10] if valor else None


def oferta(codigo, cargo, url=None, empresa=None, ubicacion=None, remuneracion=None, fecha_fin=None, es_ti=False,
           sector=None, **extra) -> dict:
    return {"codigo": str(codigo), "cargo": cargo, "empresa": empresa, "ubicacion": ubicacion,
            "remuneracion": remuneracion, "fecha_fin": fecha_fin, "url": url, "sector": sector,
            "perfil_ti": ti(es_ti), "postulable_ti": "Sí" if es_ti else "", **extra}


# --- Fuentes del sitio de Oportunidades -------------------------------------------------------------------------

def inec() -> list[dict]:
    return [oferta(j["id"], j["title"], j.get("applyUrl") or j["url"], "INEC", j.get("place"),
                   fecha_fin=fecha(j.get("closesAt")), es_ti=j["isIT"], sector=j.get("project"), bases=j["url"])
            for j in descargar("inec-jobs.json")["jobs"]]


def cnt() -> list[dict]:
    return [oferta(j["id"], j["title"], j["url"], "CNT EP", fecha_fin=j.get("closesOn"), es_ti=j["isIT"])
            for j in descargar("cnt-jobs.json")["jobs"]]


def concursos() -> list[dict]:
    return [oferta(j["id"], j["title"], "https://encuentraempleo.trabajo.gob.ec/socioEmpleo-war/paginas/procesos/busquedaOfertaPublica.jsf",
                   j["institution"], j.get("city"), f"USD {j['salary']:,.0f}" if j.get("salary") else None,
                   fecha(j.get("closesAt")), es_ti=True, etapa=j.get("stage"))
            for j in descargar("public-jobs.json")["jobs"]]


def petroecuador() -> list[dict]:
    return [oferta(j["code"], j["role"], "https://eppetroecuadorenlinea.eppetroecuador.ec/eppec-talento-humano-concursos-ang/#/",
                   "EP Petroecuador", j.get("city"), fecha_fin=fecha(j.get("closesAt")), es_ti=j["isIT"], tipo=j.get("type"))
            for j in descargar("petroecuador-jobs.json")["jobs"]]


def celec() -> list[dict]:
    # El código del proceso se repite entre unidades: la clave es el id propio de cada convocatoria
    return [oferta(j["id"], j["role"], j.get("url"), f"CELEC EP · {j.get('unit')}", None,
                   j.get("salary"), fecha(j.get("closesAt")), es_ti=j["isIT"], proceso=j.get("code"), encaje=j.get("fitDetail"))
            for j in descargar("celec-jobs.json")["jobs"]]


def bancos() -> list[dict]:
    return [oferta(j["id"], j["title"], j["url"], j["institution"], j.get("city"), es_ti=j["isIT"],
                   cerrada=j.get("closedOn"))
            for j in descargar("finance-jobs.json")["jobs"]]


def privadas() -> list[dict]:
    return [oferta(j["id"], j["title"], j["url"], j["company"], j.get("city"), es_ti=j["isIT"],
                   publicada=j.get("publishedAt"), cerrada=j.get("closedOn"))
            for j in descargar("private-jobs.json")["jobs"]]


def software() -> list[dict]:
    return [oferta(j["id"], j["title"], j["url"], j["company"], j.get("city"), es_ti=j["isIT"], cerrada=j.get("closedOn"))
            for j in descargar("tech-jobs.json")["jobs"]]


# --- Empresas con vacantes remotas (buscador de BecasChamba) ------------------------------------------------------

def remotas() -> list[dict]:
    script = BECASCHAMBA / "scripts" / "buscar-ofertas.mjs"
    if not script.exists():
        raise RuntimeError(f"No encuentro {script} (define BECASCHAMBA_REPO).")
    r = subprocess.run(["node", str(script)], cwd=BECASCHAMBA, capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.strip())
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "El buscador de BecasChamba falló.")
    datos = json.loads((BECASCHAMBA / "fuentes" / "candidatas.json").read_text(encoding="utf-8"))
    # El buscador ya filtra roles de TI publicados en los últimos 60 días
    return [oferta(j["id"], j["title"], j.get("url"), j.get("company") or j["source"], j.get("location"),
                   j.get("salary"), es_ti=True, sector=j["source"], publicada=j.get("publishedAt"))
            for j in datos["jobs"]]


PLATAFORMAS = {
    "inec": ("INEC", inec),
    "cnt": ("CNT EP", cnt),
    "concursos": ("Concursos públicos (Encuentra Empleo)", concursos),
    "petroecuador": ("EP Petroecuador", petroecuador),
    "celec": ("CELEC EP", celec),
    "bancos": ("Bancos y cooperativas", bancos),
    "software": ("Empresas de software (Workable)", software),
    "privadas": ("Empresas privadas grandes (Holcim, Arca, Farmaenlace, Tuti)", privadas),
    "remotas": ("Empresas remotas (Get on Board, Greenhouse, Lever)", remotas),
}


def actualizar(clave: str) -> bool:
    nombre, leer = PLATAFORMAS[clave]
    inicio = bdd.ahora()
    try:
        ofertas = leer()
    except Exception as e:  # noqa: BLE001 - se registra el error y se sigue con las demás
        with bdd.conectar() as con:
            id_act = bdd.iniciar_actualizacion(con, nombre, inicio)
            bdd.cerrar_actualizacion(con, id_act, "error", mensaje=str(e)[:500])
        print(f"✖ {nombre}: {e}")
        return False
    r = bdd.registrar(nombre, ofertas, inicio=inicio, mensaje=f"{sum(o['perfil_ti'] == 'TI directo' for o in ofertas)} de TI")
    print(f"✔ {nombre}: {r['total']} ofertas, {r['nuevas']} nuevas")
    return True


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a.lower() for a in sys.argv[1:]]
    if not args or args == ["lista"]:
        for clave, (nombre, _) in PLATAFORMAS.items():
            print(f"{clave:>13}  {nombre}")
        return
    claves = list(PLATAFORMAS) if args == ["todas"] else args
    desconocidas = [c for c in claves if c not in PLATAFORMAS]
    if desconocidas:
        sys.exit(f"Plataforma desconocida: {', '.join(desconocidas)}. Usa 'python plataformas.py lista'.")
    resultados = [actualizar(c) for c in claves]
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
