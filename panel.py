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
from scraper import PROGRESO, muy_pronto
import plataformas

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
                       "ayuda": "Recomendado: solo las tarjetas de las ofertas, con pausas largas. Una vez cada 12 horas como máximo."},
            "completo": {"etiqueta": "Actualizar con requisitos (lento)", "comando": ["scraper.py", "buscar", "--detalle"],
                         "ayuda": "Abre cada oferta nueva para leer requisitos: muchas más peticiones al portal. Úsalo poco; reanuda si la sesión caduca."},
        },
    },
}

# Las demás plataformas (plataformas.py): no necesitan Chrome; se actualizan una por una o todas juntas
for _clave, (_nombre, _) in plataformas.PLATAFORMAS.items():
    PLATAFORMAS[_nombre] = {
        "descripcion": "Datos del buscador de BecasChamba (Get on Board, Workable, Greenhouse, Lever)." if _clave == "remotas"
                       else "Datos que recolecta a diario el sitio de Oportunidades de Computación UPEC.",
        "necesita_chrome": False,
        "modos": {"actualizar": {"etiqueta": "Actualizar", "comando": ["plataformas.py", _clave], "ayuda": "Unos segundos."}},
    }

# Después de actualizar Encuentra Empleo, las ofertas de TI se publican en el sitio de Oportunidades
PUBLICAR = "Publicar en la página"
COMANDO_PUBLICAR = ["publicar_sitio.py"]

# Tarea en curso: una lista de pasos (uno por plataforma), cada uno con su estado para mostrar el avance
estado_tarea = {"plataforma": None, "hilo": None, "proceso": None, "codigo": None, "cancelada": False, "pasos": []}
registro = deque(maxlen=400)  # últimas líneas de la tarea en curso
candado = threading.Lock()


def chrome_listo() -> bool:
    try:
        with urllib.request.urlopen(CDP, timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def scraper_progreso_pendiente() -> bool:
    """Hay una descarga interrumpida que se puede reanudar (no cuenta como descarga nueva)."""
    return PROGRESO.exists()


def en_curso() -> bool:
    hilo = estado_tarea["hilo"]
    return bool(hilo and hilo.is_alive())


def leer_salida(proceso: subprocess.Popen, paso: dict) -> int:
    linea = ""
    for car in iter(lambda: proceso.stdout.read(1), ""):
        if car in "\r\n":
            if linea.strip():
                # El scraper reescribe la línea de avance con \r: se reemplaza en vez de acumular
                if car == "\r" and registro and registro[-1].startswith("  ["):
                    registro[-1] = linea
                else:
                    registro.append(linea)
                paso["detalle"] = linea.strip()[:160]
            linea = ""
        else:
            linea += car
    if linea.strip():
        registro.append(linea)
        paso["detalle"] = linea.strip()[:160]
    return proceso.wait()


def nuevo_paso(nombre: str, etiqueta: str, comando: list[str], seguir_si_falla: bool) -> dict:
    return {"nombre": nombre, "etiqueta": etiqueta, "comando": comando, "seguir_si_falla": seguir_si_falla,
            "estado": "pendiente", "inicio": None, "fin": None, "detalle": ""}


def ejecutar(pasos: list[dict]) -> None:
    """Ejecuta los pasos en orden. Si uno falla, sigue con los demás solo si ese paso lo permite."""
    codigo_final = 0
    for i, paso in enumerate(pasos):
        if estado_tarea["cancelada"]:
            for resto in pasos[i:]:
                resto["estado"] = "cancelado"
            break
        paso.update(estado="en curso", inicio=bdd.ahora())
        registro.append(f"▶ {paso['etiqueta']}")
        proceso = subprocess.Popen(
            [sys.executable, "-u", *paso["comando"]], cwd=RAIZ,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        estado_tarea["proceso"] = proceso
        codigo = leer_salida(proceso, paso)
        paso["fin"] = bdd.ahora()
        if estado_tarea["cancelada"]:
            paso["estado"] = "cancelado"
            continue
        if codigo == 0:
            paso["estado"] = "listo"
            registro.append(f"✔ {paso['etiqueta']}: listo.")
            continue
        paso["estado"] = "error"
        codigo_final = codigo
        registro.append(f"✖ «{paso['etiqueta']}» terminó con errores (código {codigo}).")
        if not paso["seguir_si_falla"]:
            # p. ej. si Encuentra Empleo falla, no se publica; lo descargado igual quedó en la base
            for resto in pasos[i + 1:]:
                resto["estado"] = "omitido"
            if paso["nombre"] != PUBLICAR:
                registro.append("Lo descargado ya quedó en la base: puedes publicarlo con «Publicar en la página».")
            break
    estado_tarea["codigo"] = codigo_final


def iniciar(titulo: str, pasos: list[dict]) -> None:
    registro.clear()
    estado_tarea.update(plataforma=titulo, proceso=None, codigo=None, cancelada=False, pasos=pasos)
    hilo = threading.Thread(target=ejecutar, args=(pasos,), daemon=True)
    estado_tarea["hilo"] = hilo
    hilo.start()


def armar_pasos(nombres: list[str], modo_ee: str, forzar: bool) -> tuple[list[dict] | None, str, bool]:
    """Pasos para actualizar las plataformas elegidas (en el orden del panel), o (None, aviso, pedir_confirmación)."""
    elegidas = [n for n in PLATAFORMAS if n in nombres]
    if not elegidas:
        return None, "Elige al menos una plataforma.", False
    pasos = []
    for nombre in elegidas:
        conf = PLATAFORMAS[nombre]
        if conf["necesita_chrome"]:
            if not chrome_listo():
                return None, "No encuentro el Chrome del scraper. Pulsa «Abrir Chrome», inicia sesión en Encuentra Empleo y vuelve a intentarlo.", False
            m = conf["modos"].get(modo_ee) or conf["modos"]["rapido"]
            comando = list(m["comando"])
            # Encuentra Empleo bloquea IP con muchas peticiones: se pide confirmar si la última descarga es reciente
            aviso = None if scraper_progreso_pendiente() else muy_pronto()
            if aviso and not forzar:
                return None, aviso + " ¿Actualizar de todas formas?", True
            if aviso:
                comando.append("--forzar")
            pasos.append(nuevo_paso(nombre, f"{nombre}: {m['etiqueta']}", comando, seguir_si_falla=False))
        else:
            m = next(iter(conf["modos"].values()))
            pasos.append(nuevo_paso(nombre, nombre, list(m["comando"]), seguir_si_falla=True))
    if any(PLATAFORMAS[n].get("publicar") for n in elegidas):
        pasos.append(nuevo_paso(PUBLICAR, PUBLICAR, COMANDO_PUBLICAR, seguir_si_falla=True))
    # Si falla una plataforma sin Chrome, se sigue con las demás; si falla Encuentra Empleo, no se publica
    return pasos, "", False


def actualizar_seleccion(nombres: list[str], modo_ee: str = "rapido", forzar: bool = False):
    with candado:
        if en_curso():
            return False, f"Ya hay una tarea en curso: {estado_tarea['plataforma']}."
        pasos, aviso, confirmar = armar_pasos(nombres, modo_ee, forzar)
        if pasos is None:
            return (False, aviso, True) if confirmar else (False, aviso)
        titulo = pasos[0]["nombre"] if len(pasos) == 1 or (len(pasos) == 2 and pasos[1]["nombre"] == PUBLICAR) \
            else f"{sum(p['nombre'] != PUBLICAR for p in pasos)} plataformas"
        iniciar(titulo, pasos)
    publica = any(p["nombre"] == PUBLICAR for p in pasos)
    return True, f"Actualizando {titulo}" + (": al terminar se publica en la página." if publica else ".")


def actualizar(plataforma: str, modo: str, forzar: bool = False):
    if plataforma not in PLATAFORMAS:
        return False, "Plataforma desconocida."
    return actualizar_seleccion([plataforma], modo, forzar)


def actualizar_otras():
    return actualizar_seleccion([n for n, c in PLATAFORMAS.items() if not c["necesita_chrome"]])


# Fuentes que recolecta el sitio en GitHub (CNT no: su portal rechaza GitHub y se recolecta de noche en este equipo)
FUENTES_SITIO = ["inec", "concursos", "petroecuador", "celec", "bancos", "software", "privadas"]


def actualizar_sitio():
    """Corre los recolectores del sitio en GitHub (con la sesión gh de este equipo) y trae lo nuevo a la base."""
    with candado:
        if en_curso():
            return False, f"Ya hay una tarea en curso: {estado_tarea['plataforma']}."
        iniciar("Sitio de Oportunidades (GitHub)", [
            nuevo_paso("Recolectar en GitHub", "Recolectar en GitHub (sitio de Oportunidades)", ["sitio_github.py"], seguir_si_falla=False),
            # raw.githubusercontent.com tarda unos minutos en servir el commit nuevo: si aún no aparece, «Actualizar» luego
            nuevo_paso("Traer a la base", "Traer las ofertas nuevas a la base", ["plataformas.py", *FUENTES_SITIO], seguir_si_falla=True),
        ])
    return True, "Recolección pedida en GitHub: tarda unos minutos; el sitio se vuelve a publicar solo si hay cambios."


def publicar():
    with candado:
        if en_curso():
            return False, f"Ya hay una tarea en curso: {estado_tarea['plataforma']}."
        iniciar(PUBLICAR, [nuevo_paso(PUBLICAR, PUBLICAR, COMANDO_PUBLICAR, seguir_si_falla=True)])
    return True, "Publicando en la página: crea un PR y lo fusiona cuando pasa el check de Vercel."


def detener():
    proceso = estado_tarea["proceso"]
    if not en_curso():
        return False, "No hay ninguna tarea en curso."
    estado_tarea["cancelada"] = True
    if proceso and proceso.poll() is None:
        proceso.terminate()
    registro.append("■ Detenida por el usuario. Al volver a actualizar, Encuentra Empleo continúa donde se quedó.")
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
        "tarea": {"plataforma": estado_tarea["plataforma"], "codigo": estado_tarea["codigo"],
                  "pasos": [{k: p[k] for k in ("nombre", "etiqueta", "estado", "inicio", "fin", "detalle")}
                            for p in estado_tarea["pasos"]]},
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
            "/api/actualizar": lambda: actualizar(datos.get("plataforma", ""), datos.get("modo", "rapido"),
                                                  bool(datos.get("forzar"))),
            "/api/detener": detener,
            "/api/publicar": publicar,
            "/api/actualizar-sitio": actualizar_sitio,
            "/api/actualizar-otras": actualizar_otras,
            "/api/actualizar-seleccion": lambda: actualizar_seleccion(list(datos.get("plataformas") or []),
                                                                      datos.get("modo", "rapido"), bool(datos.get("forzar"))),
            "/api/abrir-chrome": abrir_chrome,
        }
        if self.path not in acciones:
            self._json({"ok": False, "mensaje": "No encontrado"}, 404)
            return
        ok, mensaje, *confirmar = acciones[self.path]()
        self._json({"ok": ok, "mensaje": mensaje, "confirmar": bool(confirmar and confirmar[0])}, 200 if ok else 409)

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
