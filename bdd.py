"""Base de datos local de ofertas laborales de todas las plataformas (SQLite: salida/ofertas.db).

Dos tablas:
  - ofertas: una fila por oferta y plataforma, con su primera y última vez vista.
  - actualizaciones: el registro de cada actualización (plataforma, inicio, fin, estado, totales).

Uso:
    python bdd.py importar salida/datos/ofertas_XXXX.json   # carga una descarga de Encuentra Empleo
    python bdd.py estado                                     # última actualización y conteos por plataforma
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).parent
RUTA_BDD = RAIZ / "salida" / "ofertas.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
    plataforma    TEXT NOT NULL,
    codigo        TEXT NOT NULL,
    cargo         TEXT,
    empresa       TEXT,
    ubicacion     TEXT,
    remuneracion  TEXT,
    sector        TEXT,
    perfil_ti     TEXT,
    postulable_ti TEXT,
    fecha_fin     TEXT,
    url           TEXT,
    datos         TEXT NOT NULL,     -- la oferta completa en JSON
    primera_vez   TEXT NOT NULL,     -- primera actualización en que apareció
    ultima_vez    TEXT NOT NULL,     -- última actualización en que seguía publicada
    PRIMARY KEY (plataforma, codigo)
);
CREATE TABLE IF NOT EXISTS actualizaciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plataforma  TEXT NOT NULL,
    inicio      TEXT NOT NULL,
    fin         TEXT,
    estado      TEXT NOT NULL,       -- en curso | ok | parcial | error
    total       INTEGER DEFAULT 0,   -- ofertas leídas en esta actualización
    nuevas      INTEGER DEFAULT 0,   -- ofertas que no estaban en la base
    mensaje     TEXT
);
CREATE INDEX IF NOT EXISTS ofertas_ti ON ofertas (perfil_ti, postulable_ti);
"""

# Columnas propias de la tabla; el resto de la oferta queda en "datos".
COLUMNAS = ["cargo", "empresa", "ubicacion", "remuneracion", "sector", "perfil_ti", "postulable_ti", "fecha_fin", "url"]


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def conectar(ruta: Path | None = None) -> sqlite3.Connection:
    ruta = ruta or RUTA_BDD
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def iniciar_actualizacion(con: sqlite3.Connection, plataforma: str, inicio: str | None = None) -> int:
    """Registra que empezó una actualización y devuelve su id."""
    cur = con.execute("INSERT INTO actualizaciones (plataforma, inicio, estado) VALUES (?, ?, 'en curso')",
                      (plataforma, inicio or ahora()))
    con.commit()
    return cur.lastrowid


def guardar_ofertas(con: sqlite3.Connection, plataforma: str, ofertas: list[dict], momento: str | None = None) -> int:
    """Inserta o actualiza las ofertas; devuelve cuántas eran nuevas."""
    momento = momento or ahora()
    existentes = {fila[0] for fila in con.execute("SELECT codigo FROM ofertas WHERE plataforma = ?", (plataforma,))}
    nuevas = 0
    for o in ofertas:
        codigo = str(o["codigo"])
        nuevas += codigo not in existentes
        valores = [o.get(c) or None for c in COLUMNAS]
        con.execute(f"""
            INSERT INTO ofertas (plataforma, codigo, {', '.join(COLUMNAS)}, datos, primera_vez, ultima_vez)
            VALUES (?, ?, {', '.join('?' * len(COLUMNAS))}, ?, ?, ?)
            ON CONFLICT (plataforma, codigo) DO UPDATE SET
                {', '.join(f'{c} = excluded.{c}' for c in COLUMNAS)},
                datos = excluded.datos,
                ultima_vez = excluded.ultima_vez
            """, [plataforma, codigo, *valores, json.dumps(o, ensure_ascii=False), momento, momento])
    con.commit()
    return nuevas


def cerrar_actualizacion(con: sqlite3.Connection, id_act: int, estado: str, total: int = 0, nuevas: int = 0,
                         mensaje: str | None = None, fin: str | None = None) -> None:
    con.execute("UPDATE actualizaciones SET fin = ?, estado = ?, total = ?, nuevas = ?, mensaje = ? WHERE id = ?",
                (fin or ahora(), estado, total, nuevas, mensaje, id_act))
    con.commit()


def registrar(plataforma: str, ofertas: list[dict], estado: str = "ok", inicio: str | None = None,
              mensaje: str | None = None, momento: str | None = None) -> dict:
    """Guarda una descarga completa de una plataforma y deja su registro de actualización.

    momento: fecha de la descarga (por defecto, ahora); al importar un archivo es la fecha del archivo."""
    with conectar() as con:
        id_act = iniciar_actualizacion(con, plataforma, inicio or momento)
        try:
            nuevas = guardar_ofertas(con, plataforma, ofertas, momento)
        except Exception as e:
            cerrar_actualizacion(con, id_act, "error", mensaje=str(e))
            raise
        cerrar_actualizacion(con, id_act, estado, len(ofertas), nuevas, mensaje, fin=momento)
    return {"plataforma": plataforma, "total": len(ofertas), "nuevas": nuevas, "estado": estado}


def horas_desde_ultima(plataforma: str) -> float | None:
    """Horas desde la última actualización terminada (ok o parcial) de la plataforma; None si nunca se actualizó."""
    with conectar() as con:
        fila = con.execute("""SELECT fin FROM actualizaciones WHERE plataforma = ? AND estado IN ('ok', 'parcial')
                              AND fin IS NOT NULL ORDER BY fin DESC LIMIT 1""", (plataforma,)).fetchone()
    if not fila:
        return None
    return (datetime.now() - datetime.fromisoformat(fila["fin"])).total_seconds() / 3600


def estado() -> list[dict]:
    """Última actualización y conteos de cada plataforma."""
    with conectar() as con:
        filas = con.execute("""
            SELECT a.plataforma, a.inicio, a.fin, a.estado, a.total, a.nuevas, a.mensaje,
                   (SELECT COUNT(*) FROM ofertas o WHERE o.plataforma = a.plataforma) AS en_base,
                   (SELECT COUNT(*) FROM ofertas o WHERE o.plataforma = a.plataforma
                        AND o.perfil_ti IN ('TI directo', 'TI afín')) AS de_ti
            FROM actualizaciones a
            WHERE a.id = (SELECT MAX(id) FROM actualizaciones b WHERE b.plataforma = a.plataforma)
            ORDER BY a.plataforma
        """).fetchall()
    return [dict(f) for f in filas]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    imp = sub.add_parser("importar", help="carga una descarga de Encuentra Empleo (JSON de salida/datos)")
    imp.add_argument("archivo", type=Path)
    sub.add_parser("estado", help="muestra la última actualización de cada plataforma")
    args = parser.parse_args()

    if args.comando == "importar":
        ofertas = json.loads(args.archivo.read_text(encoding="utf-8"))
        # La fecha de la descarga es la del archivo, no la de la importación
        momento = datetime.fromtimestamp(args.archivo.stat().st_mtime).isoformat(timespec="seconds")
        r = registrar("Encuentra Empleo", ofertas, momento=momento, mensaje=f"Importado de {args.archivo.name}")
        print(f"{r['plataforma']}: {r['total']} ofertas, {r['nuevas']} nuevas → {RUTA_BDD.relative_to(RAIZ)}")
    else:
        filas = estado()
        if not filas:
            print("La base está vacía: importa una descarga con  python bdd.py importar <archivo.json>")
        for f in filas:
            print(f"{f['plataforma']}: última actualización {f['fin'] or f['inicio']} ({f['estado']}), "
                  f"{f['total']} leídas, {f['nuevas']} nuevas · en la base: {f['en_base']} ({f['de_ti']} de TI)")


if __name__ == "__main__":
    main()
