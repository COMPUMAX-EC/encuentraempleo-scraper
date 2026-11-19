# Encuentra Empleo Ecuador Scraper

**Scraper de ofertas de empleo de [Encuentra Empleo](https://encuentraempleo.trabajo.gob.ec)**, el portal de empleo
del Ministerio del Trabajo de Ecuador. Descarga las **ofertas privadas** y los **concursos públicos de méritos y
oposición** (con el PDF de las **bases del concurso**), las clasifica por sector y te dice **a cuáles puedes
postular desde tu perfil**. Está pensado para profesionales de TI, pero las reglas se adaptan a cualquier carrera.

Todo queda en **Excel** y en una **base de datos SQLite** local con el registro de cada actualización.

> Hecho en Ecuador por [Geovanny Basantes](https://github.com/COMPUMAX-EC). Úsalo de forma personal y responsable:
> ver [Uso responsable](#uso-responsable). No está afiliado al Ministerio del Trabajo.

## ¿Por qué?

Buscar trabajo en Encuentra Empleo a mano es lento. Las ofertas se ven de 5 en 5, el **área laboral declarada
muchas veces no coincide** con el puesto (hay ofertas de soporte técnico publicadas en "Administración"), y los
requisitos solo aparecen al abrir cada oferta. Para los concursos públicos hay que entrar institución por
institución y descargar las bases una a una. Esta herramienta lo hace por ti y te deja un Excel filtrable.

## Qué hace

**Ofertas privadas** (`scraper.py`)
- Recorre todas las **áreas laborales** del portal, o las que elijas, con filtros por provincia y palabras clave.
- Abre cada oferta y lee sus **requisitos**: instrucción, área de estudios, experiencia, conocimientos del cargo,
  tipo de contrato, jornada, vacantes y fechas de publicación y cierre.
- **Clasifica por sector** a partir del contenido de la oferta, no del área declarada. Hay 26 sectores:
  ciberseguridad, desarrollo de software y datos, soporte TI, redes y telecomunicaciones, salud, educación,
  contabilidad, construcción, petróleo y minería, entre otros.
- Marca las ofertas **TI directo** y **TI afín**, y si son **postulables desde TI** según el área de estudios que exigen.
- Señala la **región amazónica** y las ofertas que **exigen residencia amazónica** (Ley Amazónica).

**Concursos públicos** (`publicas.py`)
- Recorre las ~1400 instituciones públicas y encuentra las que tienen **vacantes abiertas** en postulación.
- Descarga el **PDF de las bases del concurso** de cada vacante a `salida/bases/`.
- Lee del PDF el **área del conocimiento**, la instrucción y la experiencia que exige el puesto, y marca las
  vacantes **postulables desde TI**.
- Genera un Excel con la fecha de cierre, la RMU, la institución, el contacto y un enlace a cada PDF.

**Otras plataformas** (`plataformas.py`)
- INEC, CNT EP, EP Petroecuador, CELEC EP, bancos y cooperativas, empresas de software y remotas, y grandes
  empresas privadas, en la misma base de datos.

**Panel local** (`panel.py`)
- Un botón para actualizar, el avance en vivo, la última actualización de cada plataforma y la publicación de las
  ofertas de TI en una página web.

## Cómo funciona

El portal exige una **cuenta de aspirante** y tiene una verificación anti-bots (Cloudflare Turnstile), así que la
herramienta **no inicia sesión ni guarda tu contraseña**. Abres un Chrome aparte, inicias sesión tú, y los scripts
usan esa sesión con [Playwright](https://playwright.dev/python/) (`connect_over_cdp`). Nunca pulsan "Aplicar": solo
leen ofertas y descargan las bases.

## Requisitos

- Windows con Google Chrome. En Linux o macOS basta con abrir Chrome con `--remote-debugging-port=9222`.
- Python 3.11 o superior.
- Una cuenta de aspirante en Encuentra Empleo (gratuita).

## Instalación

```powershell
git clone https://github.com/COMPUMAX-EC/encuentraempleo-ecuador-scraper.git
cd encuentraempleo-ecuador-scraper
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso rápido: el panel

Doble clic en **`Actualizar ofertas.bat`** (o `python panel.py`). Se abre un panel local en
`http://127.0.0.1:8765`, accesible solo desde tu computador. Desde ahí puedes:
- abrir Chrome para iniciar sesión;
- actualizar en modo rápido o con requisitos, con avance en vivo y la opción de detener;
- elegir qué plataformas actualizar;
- ver el historial de actualizaciones y publicar las ofertas de TI en la página web.

## Uso por comandos

1. **Abre Chrome para el scraper**. Usa un perfil aparte y no toca tu Chrome normal:

   ```powershell
   .\abrir_chrome.ps1
   ```

2. En esa ventana **inicia sesión a mano** en Encuentra Empleo.

3. **Ofertas privadas**:

   ```powershell
   python scraper.py areas                                  # lista las áreas laborales
   python scraper.py nuevas                                 # diaria: solo ofertas nuevas (unos minutos)
   python scraper.py buscar                                 # semanal: todas las áreas, con el área declarada
   python scraper.py buscar --detalle                       # con requisitos de cada oferta
   python scraper.py buscar --areas informatica --detalle   # solo áreas que contengan "informatica"
   python scraper.py buscar --palabras python datos --provincia pichincha
   python scraper.py buscar --forzar                        # aunque la última descarga sea de hace menos de 12 h
   ```

   Resultado: `salida/ofertas_AAAAMMDD_HHMM.xlsx`, con las hojas Resumen, Postulables desde TI,
   TI - revisar requisitos, Todas y Requisitos por sector. Además, la base `salida/ofertas.db`.

4. **Concursos públicos y bases del concurso**:

   ```powershell
   python publicas.py         # vacantes abiertas + PDF de bases -> salida/publicas_AAAAMMDD_HHMM.xlsx
   python publicas.py vacantes  # solo las instituciones con vacantes (más rápido)
   python publicas.py excel   # rehace el Excel con lo ya descargado, sin entrar al portal
   ```

5. **Base de datos y reclasificación**, sin volver a entrar al portal:

   ```powershell
   python bdd.py estado                                             # última actualización y conteos
   python bdd.py importar salida/datos/ofertas_AAAAMMDD_HHMM.json   # carga una descarga anterior
   python scraper.py clasificar salida/datos/ofertas_AAAAMMDD_HHMM.json   # tras cambiar sectores.py
   ```

6. **Otras plataformas** (no necesitan Chrome):

   ```powershell
   python plataformas.py lista      # plataformas disponibles
   python plataformas.py inec cnt   # actualiza las indicadas
   python plataformas.py todas
   ```

   Salen de los JSON públicos que recolecta a diario el
   [sitio de Oportunidades de Computación UPEC](https://github.com/Computacion-UPEC/student). Las empresas remotas
   usan el buscador de la carpeta vecina `BecasChamba` (variable `BECASCHAMBA_REPO`); sin ella, esa plataforma
   marca error y las demás siguen.

7. **Serie histórica diaria** (tabla `observaciones` de `salida/ofertas.db`: una fila por oferta y día en que
   estuvo publicada):

   ```powershell
   python historico.py                     # carga todo el historial disponible (se puede repetir, no duplica)
   python historico.py --desde 2026-10-16
   ```

   El sitio de Oportunidades recolecta a diario y solo hace commit de cada JSON cuando cambian sus ofertas, así
   que las ofertas publicadas un día son las del último commit hasta ese día. `historico.py` recorre ese
   historial (carpeta vecina `student`, variable `STUDENT_REPO`) y el de `fuentes/candidatas.json` de BecasChamba
   (solo los días con commit). Desde ahí en adelante, la tarea programada **"Encuentra Empleo - plataformas
   diaria"** corre `diaria.cmd` (`plataformas.py todas`) todos los días a las 20:30, o al encender el PC si
   estaba apagado, y deja el registro en `salida/datos/log_diaria.txt`. Encuentra Empleo no entra en la serie
   diaria porque exige iniciar sesión: sus observaciones salen de cada corrida a mano o semanal.

## Sesión de 20 minutos y reanudación

La sesión del portal caduca a los ~20 minutos. Cuando eso pasa, el scraper se detiene y guarda lo descargado. Para
seguir, vuelve a iniciar sesión y repite el mismo comando:
- `scraper.py buscar` continúa desde el área donde se quedó y no vuelve a pedir los requisitos ya leídos;
- `publicas.py` no repite los PDF ya descargados.

## Publicar en una página web

`publicar_sitio.py` exporta un **resumen** de las ofertas TI directo (cargo, empresa, ubicación, remuneración,
cierre, sector y código) al JSON `lib/data/encuentra-empleo-jobs.json` de un repositorio de Next.js. Después abre un
pull request y lo fusiona cuando pasa el check de Vercel. Si las ofertas no cambiaron, no hace nada. Los requisitos
completos se quedan en tu base.

```powershell
python publicar_sitio.py                  # exporta y publica (necesita git y la CLI de GitHub, gh)
python publicar_sitio.py --solo-exportar  # solo escribe el JSON
```

El repositorio del sitio se indica con la variable `SITIO_REPO` (por defecto `../student`).

## Adapta la clasificación a tu carrera

Las reglas están en [`sectores.py`](sectores.py). Son expresiones regulares sobre el texto normalizado, sin tildes
y en minúsculas. Para otra profesión, cambia `SECTORES` y las funciones `perfil_ti` y `postulable_ti`. Para los
concursos públicos, cambia `AREA_TI` en [`publicas.py`](publicas.py). Se agradecen pull requests con reglas para
otras carreras.

## Uso responsable

- Úsalo con **tu propia cuenta** y para tu búsqueda de empleo. Si publicas ofertas, publica solo un resumen con el
  código y envía a la gente a postular en el portal oficial.
- El scraper hace **pausas aleatorias largas**: 3-6 s entre peticiones, 20-40 s cada 10-20 ofertas y 15-30 s entre
  áreas. Además, **no descarga si la última descarga fue hace menos de 12 horas** (salvo con `--forzar`). El portal
  limita o bloquea temporalmente las IP con muchas peticiones: no quites estas protecciones.
- Para el día a día usa `scraper.py nuevas`: una sola búsqueda que se detiene al llegar a ofertas ya conocidas.
  Una vez por semana, `scraper.py buscar` recorre todas las áreas y completa el área declarada.
- Las ofertas pertenecen al portal y a los empleadores. Verifica siempre la información y postula en el sitio oficial.

## Estructura

| Archivo | Para qué sirve |
|---|---|
| `scraper.py` | Ofertas privadas: navega el portal con Playwright conectado a tu Chrome |
| `publicas.py` | Concursos públicos: vacantes abiertas y PDF de las bases del concurso |
| `sectores.py` | Clasificación por sector, perfil TI, postulabilidad y región amazónica |
| `excel.py` | Excel de ofertas privadas con resumen y hojas por perfil |
| `bdd.py` | Base SQLite con todas las ofertas, la serie diaria (`observaciones`) y el registro de actualizaciones |
| `plataformas.py` | Otras plataformas de empleo en la misma base |
| `historico.py` | Carga la serie diaria desde el historial de git del sitio de Oportunidades y de BecasChamba |
| `diaria.cmd` | Corrida diaria de `plataformas.py todas` (tarea programada, 20:30) |
| `panel.py`, `panel.html` | Panel local con botones y avance en vivo |
| `sitio_github.py` | Corre a pedido los recolectores del sitio en GitHub Actions (con `gh`) |
| `publicar_sitio.py` | Publica el resumen de ofertas de TI en un sitio web |
| `abrir_chrome.ps1` | Abre Chrome con un perfil propio y el puerto de depuración 9222 |
| `Actualizar ofertas.bat` | Abre el panel con doble clic |
| `CLAUDE.md` | Notas técnicas del portal para trabajar con Claude Code sin volver a explorarlo |

## Hoja de ruta

- [x] Ofertas privadas por área, con reanudación
- [x] Clasificación por sector y perfil TI
- [x] Base de datos con el registro de actualizaciones
- [x] Panel con un botón para actualizar
- [x] Publicación automática en la página de Oportunidades
- [x] Otras plataformas en la misma base
- [x] Concursos públicos con descarga de las bases del concurso
- [ ] Avisos de ofertas nuevas de TI

## Licencia

[MIT](LICENSE)
