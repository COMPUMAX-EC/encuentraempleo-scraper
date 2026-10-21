"""Panel local para actualizar la base de ofertas con un clic y ver la última actualización.

Abre http://127.0.0.1:8765 (solo accesible desde tu computador). Cada plataforma tiene su botón
"Actualizar"; el panel ejecuta su recolector, muestra el avance en vivo, la base guarda el registro y
las ofertas de TI se publican en el sitio de Oportunidades (publicar_sitio.py).

Uso:  python panel.py            (o doble clic en "Actualizar ofertas.bat")
"""

import json
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import bdd

RAIZ = Path(__file__).parent
PUERTO = 8765
CDP = "http://127.0.0.1:9222/json/version"

# Plataformas que el panel sabe actualizar. Para agregar una nueva: su comando y si necesita el Chrome con sesión.
PLATAFORMAS = {
    "Encuentra Empleo": {
        "descripcion": "Portal del Ministerio del Trabajo. Necesita tu sesión iniciada en el Chrome del scraper.",
        "necesita_chrome": True,
        "publicar": True,
        "modos": {
            "rapido": {"etiqueta": "Actualizar (rápido)", "comando": ["scraper.py", "buscar"],
                       "ayuda": "Solo las tarjetas de las ofertas: unos minutos."},
            "completo": {"etiqueta": "Actualizar con requisitos", "comando": ["scraper.py", "buscar", "--detalle"],
                         "ayuda": "Abre cada oferta para leer requisitos: puede tardar más de una hora y reanuda si la sesión caduca."},
        },
    },
}

# Después de actualizar, las ofertas de TI se publican en el sitio de Oportunidades (publicar_sitio.py)
PUBLICAR = ("Publicar en la página", ["publicar_sitio.py"])

estado_tarea = {"plataforma": None, "hilo": None, "proceso": None, "codigo": None, "cancelada": False}
registro = deque(maxlen=400)  # últimas líneas de la tarea en curso
candado = threading.Lock()


def chrome_listo() -> bool:
    try:
        with urllib.request.urlopen(CDP, timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def en_curso() -> bool:
    hilo = estado_tarea["hilo"]
    return bool(hilo and hilo.is_alive())


def leer_salida(proceso: subprocess.Popen) -> int:
    linea = ""
    for car in iter(lambda: proceso.stdout.read(1), ""):
        if car in "\r\n":
            if linea.strip():
                # El scraper reescribe la línea de avance con \r: se reemplaza en vez de acumular
                if car == "\r" and registro and registro[-1].startswith("  ["):
                    registro[-1] = linea
                else:
                    registro.append(linea)
            linea = ""
        else:
            linea += car
    if linea.strip():
        registro.append(linea)
    return proceso.wait()


def ejecutar(pasos: list[tuple[str, list[str]]]) -> None:
    """Ejecuta los pasos en orden; si uno falla, no sigue con los demás."""
    codigo = 0
    for etiqueta, comando in pasos:
        if estado_tarea["cancelada"]:
            break
        registro.append(f"▶ {etiqueta}")
        proceso = subprocess.Popen(
            [sys.executable, "-u", *comando], cwd=RAIZ,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        estado_tarea["proceso"] = proceso
        codigo = leer_salida(proceso)
        if codigo != 0:
            if not estado_tarea["cancelada"]:
                registro.append(f"✖ «{etiqueta}» terminó con errores (código {codigo}).")
                if etiqueta != PUBLICAR[0]:
                    registro.append("Lo descargado ya quedó en la base: puedes publicarlo con «Publicar en la página».")
            break
        registro.append(f"✔ {etiqueta}: listo.")
    estado_tarea["codigo"] = codigo


def iniciar(plataforma: str, pasos: list[tuple[str, list[str]]]) -> None:
    registro.clear()
    estado_tarea.update(plataforma=plataforma, proceso=None, codigo=None, cancelada=False)
    hilo = threading.Thread(target=ejecutar, args=(pasos,), daemon=True)
    estado_tarea["hilo"] = hilo
    hilo.start()


def actualizar(plataforma: str, modo: str) -> tuple[bool, str]:
    conf = PLATAFORMAS.get(plataforma)
    if not conf or modo not in conf["modos"]:
        return False, "Plataforma o modo desconocido."
    with candado:
        if en_curso():
            return False, f"Ya hay una tarea en curso: {estado_tarea['plataforma']}."
        if conf["necesita_chrome"] and not chrome_listo():
            return False, "No encuentro el Chrome del scraper. Pulsa «Abrir Chrome», inicia sesión en Encuentra Empleo y vuelve a intentarlo."
        m = conf["modos"][modo]
        pasos = [(f"{plataforma}: {m['etiqueta']}", m["comando"])]
        if conf.get("publicar"):
            pasos.append(PUBLICAR)
        iniciar(plataforma, pasos)
    return True, "Actualización iniciada" + (": al terminar se publica en la página." if conf.get("publicar") else ".")


def publicar() -> tuple[bool, str]:
    with candado:
        if en_curso():
            return False, f"Ya hay una tarea en curso: {estado_tarea['plataforma']}."
        iniciar("Publicación", [PUBLICAR])
    return True, "Publicando en la página: crea un PR y lo fusiona cuando pasa el check de Vercel."


def detener() -> tuple[bool, str]:
    proceso = estado_tarea["proceso"]
    if not en_curso():
        return False, "No hay ninguna tarea en curso."
    estado_tarea["cancelada"] = True
    if proceso and proceso.poll() is None:
        proceso.terminate()
    registro.append("■ Detenida por el usuario. Al volver a actualizar, continúa donde se quedó.")
    return True, "Detenida."


def abrir_chrome() -> tuple[bool, str]:
    if chrome_listo():
        return True, "El Chrome del scraper ya está abierto."
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RAIZ / "abrir_chrome.ps1")],
                     cwd=RAIZ, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True, "Abriendo Chrome: inicia sesión en Encuentra Empleo y entra a la búsqueda de ofertas."


def resumen() -> dict:
    with bdd.conectar() as con:
        historial = [dict(f) for f in con.execute(
            "SELECT plataforma, inicio, fin, estado, total, nuevas, mensaje FROM actualizaciones ORDER BY id DESC LIMIT 10")]
    ultimas = {f["plataforma"]: f for f in bdd.estado()}
    return {
        "plataformas": [{"nombre": n, "descripcion": c["descripcion"], "necesita_chrome": c["necesita_chrome"],
                         "modos": [{"id": k, **{x: m[x] for x in ("etiqueta", "ayuda")}} for k, m in c["modos"].items()],
                         "ultima": ultimas.get(n)} for n, c in PLATAFORMAS.items()],
        "historial": historial,
        "chrome": chrome_listo(),
        "en_curso": en_curso(),
        "tarea": {"plataforma": estado_tarea["plataforma"], "codigo": estado_tarea["codigo"]},
        "registro": list(registro)[-60:],
    }


HTML = (RAIZ / "panel.html").read_text(encoding="utf-8") if (RAIZ / "panel.html").exists() else ""


class Manejador(BaseHTTPRequestHandler):
    def _json(self, datos: dict, codigo: int = 200) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self) -> None:
        if self.path == "/":
            cuerpo = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        elif self.path == "/api/estado":
            self._json(resumen())
        else:
            self._json({"error": "No encontrado"}, 404)

    def do_POST(self) -> None:
        # Solo se aceptan peticiones del propio panel (evita que otra página web dispare acciones)
        if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PUERTO}", f"http://localhost:{PUERTO}"):
            self._json({"ok": False, "mensaje": "Origen no permitido."}, 403)
            return
        largo = int(self.headers.get("Content-Length") or 0)
        datos = json.loads(self.rfile.read(largo) or b"{}")
        acciones = {
            "/api/actualizar": lambda: actualizar(datos.get("plataforma", ""), datos.get("modo", "rapido")),
            "/api/detener": detener,
            "/api/publicar": publicar,
            "/api/abrir-chrome": abrir_chrome,
        }
        if self.path not in acciones:
            self._json({"ok": False, "mensaje": "No encontrado"}, 404)
            return
        ok, mensaje = acciones[self.path]()
        self._json({"ok": ok, "mensaje": mensaje}, 200 if ok else 409)

    def log_message(self, *args) -> None:  # silencioso
        pass


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"Panel de ofertas en {url}  (Ctrl+C para cerrar)")
    if "--sin-navegador" not in sys.argv:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        detener()
        print("\nPanel cerrado.")


if __name__ == "__main__":
    main()
