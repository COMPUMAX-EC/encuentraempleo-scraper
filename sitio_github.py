"""Ejecuta a pedido los recolectores del sitio de Oportunidades en GitHub Actions y espera a que terminen.

Usa la sesión de la CLI de GitHub (gh) de este computador: no hace falta ningún token en el sitio. El workflow
"Recolectar convocatorias" revisa INEC, concursos públicos, Petroecuador, CELEC, bancos, empresas de software y
empresas privadas, y si hay cambios hace commit de los datos (el sitio se vuelve a publicar solo).

Uso:  python sitio_github.py
Repositorio: variable de entorno SITIO_GITHUB (por defecto Computacion-UPEC/student).
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

REPO = os.environ.get("SITIO_GITHUB", "Computacion-UPEC/student")
WORKFLOW = "petroecuador.yml"


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout


def corridas() -> list[dict]:
    return json.loads(gh("run", "list", "--workflow", WORKFLOW, "--limit", "5",
                         "--json", "databaseId,createdAt,status,conclusion,event,url"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        en_curso = [c for c in corridas() if c["status"] != "completed"]
        if en_curso:
            print(f"Ya hay una recolección en curso: {en_curso[0]['url']}. Se espera a que termine.")
            corrida = en_curso[0]
        else:
            inicio = datetime.now(timezone.utc)
            gh("workflow", "run", WORKFLOW, "--ref", "main")
            print("Recolección pedida en GitHub Actions; esperando a que empiece…", flush=True)
            corrida = None
            for _ in range(30):  # GitHub tarda unos segundos en registrar la corrida
                time.sleep(4)
                nuevas = [c for c in corridas() if c["event"] == "workflow_dispatch"
                          and datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00")) >= inicio.replace(microsecond=0)]
                if nuevas:
                    corrida = nuevas[0]
                    break
            if not corrida:
                sys.exit("GitHub no registró la corrida a tiempo: revisa la pestaña Actions del repositorio.")
        print(f"Corrida: {corrida['url']}", flush=True)
        anterior = None
        while True:
            datos = json.loads(gh("run", "view", str(corrida["databaseId"]), "--json", "status,conclusion,jobs"))
            pasos = [p for j in datos.get("jobs", []) for p in j.get("steps", [])]
            actual = next((p["name"] for p in pasos if p.get("status") == "in_progress"), None)
            if actual and actual != anterior:
                print(f"  {actual}…", flush=True)
                anterior = actual
            if datos["status"] == "completed":
                break
            time.sleep(10)
        fallidos = [p["name"] for p in pasos if p.get("conclusion") == "failure"]
        if fallidos:
            # Los recolectores tienen continue-on-error: si uno falla, los demás igual guardan sus datos
            print("Pasos con errores (los demás guardaron sus datos): " + ", ".join(fallidos))
        print(f"Recolección terminada: {datos['conclusion']}. El sitio se vuelve a publicar en unos minutos si hubo cambios.")
        sys.exit(0 if datos["conclusion"] == "success" else 1)
    except RuntimeError as e:
        sys.exit(f"No se pudo usar GitHub ({e}). ¿Está instalada la CLI gh y con sesión iniciada? (gh auth status)")


if __name__ == "__main__":
    main()
