# Encuentra Empleo scraper: guía rápida para Claude

Objetivo: descargar ofertas de encuentraempleo.trabajo.gob.ec (Ecuador). Interesan sobre todo las que
un profesional TI puede postular. **No explores el sitio de nuevo**: todo lo necesario está aquí y en
el README.

## Reglas
- Nunca inicies sesión ni escribas credenciales. El usuario abre Chrome con `abrir_chrome.ps1`
  (puerto 9222) e inicia sesión a mano. Los scripts se conectan con `connect_over_cdp`.
- Nunca pulses "Aplicar" ni "Postular". Solo se leen datos y se descargan PDF.
- No reduzcas las pausas (`PAUSA_*` en scraper.py) ni quites la regla de 12 h (`--forzar`): el
  portal bloquea las IP con muchas peticiones.
- Lanza las descargas largas con `run_in_background` y no hagas polling. Al terminar, lee el log con
  `tr '\r' '\n' < log | grep -v 'pág\.'`.
- Antes de raspar el portal, mira si ya basta con `plataformas.py concursos` (JSON que recoge el sitio
  de Oportunidades): no hace ninguna petición al portal.
- Los commits van a nombre del usuario, sin trailer de coautoría.

## Comandos (desde esta carpeta, con `.venv/Scripts/python.exe -u`)
| Qué | Comando | Tiempo |
|---|---|---|
| Privadas, diaria (solo nuevas, una búsqueda, para tras 2 páginas conocidas) | `scraper.py nuevas` | unos minutos |
| Privadas por área (semanal; completa el área declarada) | `scraper.py buscar` | 25-35 min, reanuda |
| Privadas con requisitos | `scraper.py buscar --detalle` | más de 1 h, reanuda |
| Rehacer el Excel sin Chrome | `scraper.py clasificar salida/datos/ofertas_X.json` | segundos |
| Concursos públicos + PDF de bases | `publicas.py` | unos 20 min (sesión de unos 20 min) |
| Solo instituciones con vacantes (sin recorrer las 175 páginas) | `publicas.py vacantes` | unos 5 min |
| Rehacer el Excel de públicos | `publicas.py excel` | segundos |
| Frecuencia de vacantes TI por institución | `historial.py` (o `historial.py excel` sin registrar corrida) | segundos |
| Corrida semanal (tarea "Encuentra Empleo - concursos semanal", lunes 9:00) | `semanal.ps1` | unos 20 min, pide iniciar sesión |
| Estado de la base | `bdd.py estado` | |
| Otras plataformas | `plataformas.py todas` | sin Chrome |
| Portales con navegador real o cuenta (El Rosado, CACPECO/Laburo) | `portales_navegador.py` | 1 min, sesión en El Rosado |
| Publicar en el sitio (ofertas TI, concursos TI con bases, estado de plataformas) | `publicar_sitio.py` | PR + fusión |
| Panel con botones | `panel.py` (o `Actualizar ofertas.bat`) | |

Salida: `salida/*.xlsx` y `salida/ofertas.db`. Los JSON intermedios van en `salida/datos/` y los PDF
de bases en `salida/bases/`.

## Particularidades del sitio (JSF / PrimeFaces 6.2)
- **La sesión dura unos 20 min.** Al caducar, el POST AJAX devuelve 302 pero la pestaña sigue
  mostrando "Bienvenido" con datos viejos. `esperar_ajax` lanza `SesionCaducada`. scraper.py reanuda
  por área (`progreso.json`, `cache_detalle.json`) y publicas.py no repite los PDF ya bajados.
  Pídele al usuario que vuelva a iniciar sesión y relanza el mismo comando.
- Privadas (`busquedaOferta.jsf`): los combos son `select` ocultos (`FormSearch:areaLaboral_input`).
  Pon `.value` y pulsa la lupa (`#FormSearch a:has(img[src*='busca.png'])`). Paginación:
  `formBuscaOferta:pagina_input` + evento `change`. 5 ofertas por página.
- Si el total es múltiplo de 5, la web anuncia una página extra que llega vacía: no es un error.
  Las áreas sin ofertas no tienen paginador.
- Detalle de una oferta privada: clic en la tarjeta, leer `#formVerOferta` (los combos deshabilitados
  tienen la opción seleccionada) y cerrar con `PF('VerOfertaDialog').hide()`.
- Públicas (`busquedaOfertaPublica.jsf`): unas 1400 instituciones, 8 por página (`formBuscaPublica:itemsTable`).
  - "Nuevas vacantes" (2.ª columna) abre `PF('vacAplDgl')` / `vacantesAplMpForm:vacantesTableMp`:
    concursos en postulación, con `data-countdown` = fecha de cierre.
  - "Puesto en concurso" es el histórico (nulos, desiertos, ganadores; cientos de miles de filas).
    **No lo recorras.**
  - "Ver bases del concurso" es un submit no AJAX que devuelve `BasesDelConcurso.pdf`; captúralo con
    `expect_download`.
  - El PDF trae `AREA DEL CONOCIMIENTO: ... TITULO:`, que dice qué carreras acepta.
- El área laboral que declara cada oferta suele estar mal. La relevancia TI se calcula por contenido
  en `sectores.py`. Las palabras sueltas dan falsos positivos ("software contable", "servidores
  públicos", "soldadura TIC"), por eso TI directo exige un cargo TI, actividades TI o el área de
  estudios Informática.
