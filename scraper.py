"""Scraper de ofertas de Encuentra Empleo (encuentraempleo.trabajo.gob.ec) por área laboral.

Usa la sesión que el usuario inicia a mano en el Chrome abierto con abrir_chrome.ps1
(puerto de depuración 9222). No maneja credenciales.

Uso:
    python scraper.py areas                                   # lista las áreas disponibles
    python scraper.py buscar                                  # todas las áreas
    python scraper.py buscar --areas informática ingeniería   # áreas que contengan esos textos
    python scraper.py buscar --areas informática --palabras python datos --provincia pichincha
    python scraper.py clasificar salida/datos/ofertas_XXXX.json  # rehace el Excel de una descarga

Cada búsqueda guarda en salida/ un Excel (Resumen, Postulables desde TI, TI - revisar, Todas, Requisitos).
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

import bdd
from excel import exportar_excel
from sectores import amazonia, clasificar, normalizar, perfil_ti, postulable_ti

BASE = "https://encuentraempleo.trabajo.gob.ec/socioEmpleo-war/paginas"
URL_BUSQUEDA = f"{BASE}/aspirante/busquedaOferta.jsf"
CDP = "http://127.0.0.1:9222"

RAIZ = Path(__file__).parent
SALIDA = RAIZ / "salida"
DATOS = SALIDA / "datos"  # JSON intermedios (reanudación, reclasificar)
CACHE_DETALLE = DATOS / "cache_detalle.json"  # detalle por código de oferta, para reanudar sin repetir
PROGRESO = DATOS / "progreso.json"  # áreas terminadas y ofertas de una descarga interrumpida

# Pausas aleatorias (segundos): tras cada petición, cada cierto número de ofertas y entre áreas.
PAUSA_PETICION = (1.0, 2.5)
PAUSA_LARGA = (8.0, 15.0)
OFERTAS_ENTRE_PAUSAS_LARGAS = (15, 30)
PAUSA_ENTRE_AREAS = (5.0, 10.0)

SEL_AREA = "FormSearch:areaLaboral_input"
SEL_PROVINCIA = "FormSearch:provincia_input"
SEL_PAGINA = "formBuscaOferta:pagina_input"
LUPA = "#FormSearch a:has(img[src*='busca.png'])"

# Extrae las tarjetas de la página de resultados actual. La estructura de tablas varía entre
# ofertas, así que se reconoce cada dato por su contenido y no por su posición.
JS_OFERTAS = r"""() => [...document.querySelectorAll("a[id^='formBuscaOferta:listResult:']")]
  .filter(a => a.querySelector('fieldset'))
  .map(a => {
    const fs = a.querySelector('fieldset');
    const lineas = fs.querySelector('.ui-fieldset-content').innerText.split('\n').map(l => l.trim()).filter(Boolean);
    const buscar = re => lineas.find(l => re.test(l)) || '';
    const ubic = buscar(/HACE:/).match(/^(.*?)\s*HACE:\s*(.*)$/);
    return {
      empresa: fs.querySelector('legend')?.innerText.trim() || '',
      cargo: fs.querySelector('.subTitle')?.innerText.trim() || '',
      codigo: (fs.innerText.match(/OFERTA-\d+-\d+/) || [''])[0],
      remuneracion: buscar(/^Remuneraci.n:/).replace(/^Remuneraci.n:\s*/, ''),
      ubicacion: ubic ? ubic[1].trim() : '',
      publicado_hace: ubic ? ubic[2].trim() : '',
      actividades: [...fs.querySelectorAll('.ui-datalist-item')].map(li => li.innerText.trim()).join(' | '),
      descripcion_enlace: a.getAttribute('aria-label') || '',
    };
  })"""


# Lee el cuadro "Oferta Laboral" (formVerOferta): pares etiqueta → valor. Los combos están
# deshabilitados, así que se toma la opción seleccionada.
JS_DETALLE = r"""() => {
  const f = document.getElementById('formVerOferta'); const out = {};
  for (const td of f.querySelectorAll('td')) {
    const etq = td.innerText.trim();
    if (!etq.endsWith(':') || etq.length > 45 || td.querySelector('td')) continue;
    const v = td.nextElementSibling; if (!v) continue;
    const sel = v.querySelector('select');
    const val = sel ? [...sel.selectedOptions].map(o => o.text.trim()).join(', ')
      : (v.querySelector('textarea')?.value ?? v.querySelector('input:not([type=hidden])')?.value ?? v.innerText);
    out[etq.replace(/^\*/, '').replace(/:$/, '').trim()] = (val || '').trim();
  }
  out['tipo_empleador'] = [...f.querySelectorAll('li')].map(li => li.innerText.trim())
    .find(t => /^Sector (P[uú]blico|Privado)/i.test(t)) || '';
  return out;
}"""

# Etiqueta del cuadro de detalle (normalizada) → columna de salida.
CAMPOS_DETALLE = {
    "tipo contrato": "tipo_contrato",
    "ciudad": "ciudad",
    "parroquia": "parroquia",
    "sector": "zona",
    "fecha inicio publicacion": "fecha_inicio",
    "fecha finalizacion": "fecha_fin",
    "instruccion": "instruccion",
    "area de estudios": "area_estudios",
    "experiencia": "experiencia",
    "conocimientos del cargo": "conocimientos",
    "actividades a desempenar": "actividades",  # versión completa: reemplaza la de la tarjeta
    "capacitaciones / certificaciones": "capacitacion",
    "jornadas de trabajo": "jornada",
    "informacion adicional": "info_adicional",
    "numero de cargos solicitados": "vacantes",
    "tipo_empleador": "tipo_empleador",
}


def leer_detalle(page: Page, indice: int, cargo: str) -> dict:
    """Abre el detalle de la tarjeta `indice` de la página actual, lo lee y lo cierra.

    Solo se cierra el cuadro con PF(...).hide(): nunca se pulsa "Aplicar".
    Comprueba que el cargo del detalle sea el de la tarjeta para no mezclar ofertas.
    """
    tarjeta = page.locator("a[id^='formBuscaOferta:listResult:']:has(fieldset)").nth(indice)
    for _ in range(2):
        esperar_ajax(page, lambda: tarjeta.evaluate("a => a.click()"))
        crudo = page.evaluate(JS_DETALLE)
        page.evaluate("PF('VerOfertaDialog').hide()")
        if normalizar(crudo.get("Cargo solicitado", "")).strip() == normalizar(cargo).strip():
            break
    else:
        raise RuntimeError("el detalle no corresponde a la tarjeta")
    detalle = {col: "" for col in CAMPOS_DETALLE.values()}
    for etiqueta, valor in crudo.items():
        col = CAMPOS_DETALLE.get(normalizar(etiqueta))
        if col:
            detalle[col] = valor.strip().strip('"')
    return detalle


def pestana_encuentra_empleo(p) -> Page:
    """Se conecta al Chrome del usuario y devuelve la pestaña de Encuentra Empleo con sesión."""
    try:
        navegador = p.chromium.connect_over_cdp(CDP, timeout=30_000)
    except Exception as e:
        if "ECONNREFUSED" in str(e):
            sys.exit("No encuentro Chrome en el puerto 9222. Ábrelo con: .\\abrir_chrome.ps1")
        sys.exit("Chrome no respondió a tiempo. Cierra menús o diálogos abiertos en esa ventana y reintenta.")
    ctx = navegador.contexts[0]
    sin_sesion = (
        "No hay sesión activa o caducó: en la ventana de Chrome entra a Encuentra Empleo, "
        "inicia sesión como aspirante, abre la búsqueda de ofertas y vuelve a ejecutar."
    )

    # Siempre se recarga la búsqueda: una pestaña vieja puede mostrar "Bienvenido" con la sesión
    # ya caducada. La web a veces da un 500 puntual, por eso hay un reintento.
    page = next((pg for pg in ctx.pages if "trabajo.gob.ec" in pg.url), None) or ctx.new_page()
    for intento in range(2):
        try:
            page.goto(URL_BUSQUEDA, wait_until="networkidle")
            break
        except Exception:
            if intento:
                sys.exit(sin_sesion)
            time.sleep(3)
    if "busquedaOferta" not in page.url or not page.locator(f"[id='{SEL_AREA}']").count():
        sys.exit(sin_sesion)
    return page


def opciones(page: Page, select_id: str) -> list[tuple[str, str]]:
    return page.evaluate(
        "id => [...document.getElementById(id).options].map(o => [o.value, o.text.trim()])", select_id
    )


def pausa(minimo: float, maximo: float) -> None:
    """Espera aleatoria para no saturar el servidor ni parecer un patrón fijo."""
    time.sleep(random.uniform(minimo, maximo))


class SesionCaducada(Exception):
    pass


def esperar_ajax(page: Page, accion) -> None:
    """Ejecuta una acción que dispara un POST AJAX de PrimeFaces y espera la respuesta.

    Si el servidor responde con una redirección, la sesión caducó: la página sigue mostrando
    resultados viejos, así que hay que detenerse en vez de seguir leyendo datos repetidos.
    """
    with page.expect_response(
        lambda r: "busquedaOferta" in r.url and r.request.method == "POST", timeout=60_000
    ) as info:
        accion()
    r = info.value
    if 300 <= r.status < 400 or (r.ok and "<redirect" in r.text()[:500]):
        raise SesionCaducada()
    pausa(*PAUSA_PETICION)


def total_paginas(page: Page) -> int:
    if not page.locator(f"[id='{SEL_PAGINA}']").count():  # área sin ofertas
        return 0
    return len(opciones(page, SEL_PAGINA))


def total_registros(page: Page) -> int:
    """Lee el 'Total: N registros' que muestra la web bajo los resultados."""
    texto = page.evaluate(f"document.getElementById('{SEL_PAGINA}')?.closest('tr')?.innerText || ''")
    m = re.search(r"Total:\s*(\d+)\s*registros", texto)
    return int(m.group(1)) if m else 0  # sin paginador = área sin ofertas


def buscar_area(page: Page, area_id: str, provincia_id: str) -> None:
    page.evaluate(
        "([a, aid, p, pid]) => { document.getElementById(a).value = aid; document.getElementById(p).value = pid; }",
        [SEL_AREA, area_id, SEL_PROVINCIA, provincia_id],
    )
    esperar_ajax(page, lambda: page.locator(LUPA).evaluate("a => a.click()"))


def ir_a_pagina(page: Page, n: int) -> None:
    esperar_ajax(
        page,
        lambda: page.evaluate(
            "([id, n]) => { const s = document.getElementById(id); s.value = String(n);"
            " s.dispatchEvent(new Event('change')); }",
            [SEL_PAGINA, n],
        ),
    )


def cargar_pagina(page: Page, area_id: str, provincia_id: str, n: int, ya_cargada: bool = False,
                  ultima: bool = False) -> list[dict]:
    """Devuelve las tarjetas de la página n. Si la lista desaparece (la web a veces reinicia
    la vista de resultados), repite la búsqueda del área y vuelve a la página n.

    Ojo: cuando el total es múltiplo de 5, la web anuncia una página de más que llega vacía;
    una última página vacía es normal y no un error.
    """
    for intento in range(4):
        try:
            if intento or not ya_cargada:
                if intento or not page.locator(f"[id='{SEL_PAGINA}']").count():
                    buscar_area(page, area_id, provincia_id)
                if n > 1:
                    ir_a_pagina(page, n)
            tarjetas = page.evaluate(JS_OFERTAS)
            if tarjetas or ultima:
                return tarjetas
        except SesionCaducada:
            raise
        except Exception:
            pass
        page.wait_for_timeout(3000 * (intento + 1))
    raise RuntimeError(f"no se pudo cargar la página {n} tras varios intentos")


def detalle_con_reintento(page: Page, area_id: str, provincia_id: str, n: int, i: int,
                          oferta: dict, cache: dict) -> dict:
    if oferta["codigo"] in cache:
        return cache[oferta["codigo"]]
    for intento in range(2):
        try:
            detalle = leer_detalle(page, i, oferta["cargo"])
            cache[oferta["codigo"]] = detalle
            return detalle
        except SesionCaducada:
            raise
        except Exception as e:
            if intento:
                print(f"\n  ! sin detalle {oferta['codigo']}: {e.__class__.__name__}")
            else:  # probablemente se perdió la lista: recargar la página y reintentar
                cargar_pagina(page, area_id, provincia_id, n)
    return {}


def cargar_cache() -> dict:
    try:
        return json.loads(CACHE_DETALLE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar_cache(cache: dict) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    CACHE_DETALLE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def cargar_progreso(filtros: dict) -> dict:
    vacio = {"areas_completas": [], "ofertas": {}}
    try:
        datos = json.loads(PROGRESO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return vacio
    return datos if datos.get("filtros") == filtros else vacio


def guardar_progreso(filtros: dict, hechas: list[str], vistas: dict) -> None:
    datos = {"filtros": filtros, "areas_completas": hechas, "ofertas": vistas}
    PROGRESO.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def elegir(disponibles: list[tuple[str, str]], filtros: list[str] | None) -> list[tuple[str, str]]:
    reales = [(v, t) for v, t in disponibles if v != "-1"]
    if not filtros:
        return reales
    claves = [normalizar(f) for f in filtros]
    return [(v, t) for v, t in reales if any(c in normalizar(t) for c in claves)]


def coincide(oferta: dict, palabras: list[str] | None) -> bool:
    if not palabras:
        return True
    campos = ("cargo", "actividades", "descripcion_enlace", "conocimientos", "info_adicional")
    texto = normalizar(" ".join(oferta.get(c, "") for c in campos))
    return any(normalizar(p) in texto for p in palabras)


def guardar(ofertas: list[dict], base: str | None = None) -> None:
    orden_ti = {"TI directo": 0, "TI afín": 1, "": 2}
    for o in ofertas:
        o["sector"] = clasificar(o)
        o["perfil_ti"] = perfil_ti(o)
        o.update(amazonia(o))
        o["postulable_ti"] = postulable_ti(o)
    ofertas.sort(key=lambda o: (o["postulable_ti"] != "Sí", orden_ti[o["perfil_ti"]], o["sector"], o["cargo"]))

    # Resultado para el usuario: un Excel en salida/. El JSON queda en salida/datos/ porque lo usan
    # la reanudación y el comando "clasificar".
    DATOS.mkdir(parents=True, exist_ok=True)
    base = base or f"ofertas_{datetime.now().strftime('%Y%m%d_%H%M')}"
    (DATOS / f"{base}.json").write_text(json.dumps(ofertas, ensure_ascii=False, indent=2), encoding="utf-8")
    ruta_xlsx = SALIDA / f"{base}.xlsx"
    exportar_excel(ofertas, ruta_xlsx)
    print(f"\n{len(ofertas)} ofertas guardadas en salida/{ruta_xlsx.name}")


def registrar_descarga(ofertas: list[dict], filtros: dict, completo: bool, inicio: str,
                       areas_hechas: int, areas_total: int) -> None:
    """Guarda la descarga en la base (salida/ofertas.db) y deja el registro de la actualización.

    Si la base falla, el Excel y el JSON ya están guardados: solo se avisa."""
    usados = {k: v for k, v in filtros.items() if v}
    mensaje = f"Áreas {areas_hechas}/{areas_total}" + (f" · filtros: {usados}" if usados else "")
    try:
        r = bdd.registrar("Encuentra Empleo", ofertas, estado="ok" if completo else "parcial",
                          inicio=inicio, mensaje=mensaje)
        print(f"Base de datos: {r['total']} ofertas, {r['nuevas']} nuevas · actualización {r['estado']} registrada")
    except Exception as e:  # noqa: BLE001 - la descarga ya quedó en disco
        print(f"No se pudo guardar en la base ({e}); el Excel y el JSON sí se guardaron.")


def cmd_areas(page: Page) -> None:
    for v, t in elegir(opciones(page, SEL_AREA), None):
        print(f"{v:>10}  {t}")


def cmd_buscar(page: Page, args) -> None:
    areas = elegir(opciones(page, SEL_AREA), args.areas)
    if not areas:
        sys.exit("Ninguna área coincide con --areas. Usa 'python scraper.py areas' para ver la lista.")

    provincia_id = "-1"
    if args.provincia:
        provs = elegir(opciones(page, SEL_PROVINCIA), [args.provincia])
        if not provs:
            sys.exit(f"Provincia no encontrada: {args.provincia}")
        provincia_id = provs[0][0]
        print(f"Provincia: {provs[0][1]}")

    inicio = bdd.ahora()
    cache = cargar_cache()
    # Reanudación: si una ejecución anterior con los mismos filtros se cortó (p. ej. por sesión
    # caducada), se recuperan sus ofertas y se saltan las áreas que ya terminó.
    filtros = {"areas": args.areas, "palabras": args.palabras, "provincia": args.provincia, "detalle": args.detalle}
    progreso = cargar_progreso(filtros)
    vistas: dict[str, dict] = progreso["ofertas"]
    hechas: list[str] = progreso["areas_completas"]
    if hechas:
        print(f"Reanudando: {len(hechas)} área(s) ya completas, {len(vistas)} ofertas recuperadas.")
    completo = False
    hasta_pausa = random.randint(*OFERTAS_ENTRE_PAUSAS_LARGAS)
    try:
        pendientes = [(a, n) for a, n in areas if n not in hechas]
        for k, (area_id, area_nombre) in enumerate(pendientes):
            if k:
                pausa(*PAUSA_ENTRE_AREAS)
            buscar_area(page, area_id, provincia_id)
            paginas, registros = total_paginas(page), total_registros(page)
            en_area: set[str] = set()
            for n in range(1, paginas + 1):
                tarjetas = cargar_pagina(page, area_id, provincia_id, n, ya_cargada=(n == 1), ultima=(n == paginas))
                for i, oferta in enumerate(tarjetas):
                    en_area.add(oferta["codigo"])
                    if oferta["codigo"] in vistas:
                        continue
                    if args.detalle:
                        nuevo = oferta["codigo"] not in cache
                        oferta.update(detalle_con_reintento(page, area_id, provincia_id, n, i, oferta, cache))
                        hasta_pausa -= nuevo
                        if hasta_pausa <= 0:
                            pausa(*PAUSA_LARGA)
                            hasta_pausa = random.randint(*OFERTAS_ENTRE_PAUSAS_LARGAS)
                    if not coincide(oferta, args.palabras):
                        continue
                    oferta["area_laboral"] = area_nombre
                    vistas[oferta["codigo"]] = oferta
                print(f"  [{area_nombre}] pág. {n}/{paginas}", end="\r")
            aviso = "" if len(en_area) >= registros else f"  <-- faltan {registros - len(en_area)}"
            print(f"[{area_nombre}] web: {registros} registros, leídas: {len(en_area)}{aviso}".ljust(70))
            hechas.append(area_nombre)
            guardar_cache(cache)
            guardar_progreso(filtros, hechas, vistas)
        completo = True
    finally:
        guardar_cache(cache)
        if completo:
            PROGRESO.unlink(missing_ok=True)
        else:
            print("\n¡Interrumpido! Se guarda lo descargado; al repetir el comando continúa donde se quedó.")
        ofertas = list(vistas.values())
        guardar(ofertas, base=None if completo else f"ofertas_{datetime.now():%Y%m%d_%H%M}_parcial")
        registrar_descarga(ofertas, filtros, completo, inicio, len(hechas), len(areas))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("areas", help="lista las áreas laborales")
    b = sub.add_parser("buscar", help="descarga las ofertas por área")
    b.add_argument("--areas", nargs="+", help="textos para elegir áreas (sin tildes vale); por defecto todas")
    b.add_argument("--palabras", nargs="+", help="solo ofertas cuyo cargo/actividades contengan alguna")
    b.add_argument("--provincia", help="nombre de provincia, ej. pichincha")
    b.add_argument("--detalle", action="store_true",
                   help="abre cada oferta para leer requisitos (instrucción, experiencia, conocimientos...); más lento")
    c =sub.add_parser("clasificar", help="reclasifica por sector un JSON ya descargado (no necesita Chrome)")
    c.add_argument("archivo", type=Path)
    args = parser.parse_args()

    if args.comando == "clasificar":
        guardar(json.loads(args.archivo.read_text(encoding="utf-8")), base=args.archivo.stem)
        return

    # La sesión caducada se maneja fuera del bloque de Playwright para que cierre limpio.
    try:
        with sync_playwright() as p:
            page = pestana_encuentra_empleo(p)
            if args.comando == "areas":
                cmd_areas(page)
            else:
                cmd_buscar(page, args)
    except SesionCaducada:
        sys.exit("\nLa sesión de Encuentra Empleo caducó. Vuelve a iniciar sesión en la ventana de Chrome, "
                 "abre la búsqueda de ofertas y ejecuta el mismo comando: continúa desde el área donde se quedó.")


if __name__ == "__main__":
    main()
