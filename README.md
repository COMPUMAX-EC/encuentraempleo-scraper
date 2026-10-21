# Encuentra Empleo Scraper

Descarga las ofertas de [Encuentra Empleo](https://encuentraempleo.trabajo.gob.ec), el portal de empleo del
Ministerio del Trabajo de Ecuador, las clasifica por sector y te dice **a cuáles puedes postular desde tu perfil**
(pensado para profesionales de TI, pero sirve para cualquier área). Todo queda en un Excel y en una base de datos
local con el registro de cada actualización.

> Hecho en Ecuador por [Geovanny Basantes](https://github.com/COMPUMAX-EC). Uso personal y responsable: ver
> [Uso responsable](#uso-responsable).

## Qué hace

- Recorre las **áreas laborales** del portal (todas o las que elijas), con filtros por provincia y palabras clave.
- Abre cada oferta para leer sus **requisitos**: instrucción, área de estudios, experiencia, conocimientos.
- **Clasifica por sector** (ciberseguridad, desarrollo de software y datos, soporte TI, redes, etc.) a partir del
  contenido, porque el área declarada en el portal muchas veces no coincide.
- Marca las ofertas de **TI directo / TI afín** y si son **postulables** desde un perfil de TI, o qué piden en su
  lugar (ventas, contabilidad, ingeniería...).
- Señala las ofertas de la **región amazónica** y las que exigen residencia amazónica.
- Guarda un **Excel** (Resumen, TI directo, TI afín, Todas, Requisitos) y una **base SQLite** (`salida/ofertas.db`)
  con cada oferta, cuándo apareció por primera vez y el **registro de actualizaciones**.
- Si la sesión del portal caduca (dura unos 20 minutos), **reanuda** desde el área donde se quedó.

## Requisitos

- Windows con Google Chrome (los scripts de ayuda son para PowerShell; en Linux o macOS basta abrir Chrome con
  `--remote-debugging-port=9222`).
- Python 3.11 o superior.
- Una cuenta de **aspirante** en Encuentra Empleo (es gratuita).

## Instalación

```powershell
git clone https://github.com/COMPUMAX-EC/encuentraempleo-scraper.git
cd encuentraempleo-scraper
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Uso rápido: el panel

Doble clic en **`Actualizar ofertas.bat`** (o `python panel.py`). Se abre en tu navegador un panel local
(`http://127.0.0.1:8765`, solo accesible desde tu computador) con:

- la **última actualización** de cada plataforma (fecha, estado, ofertas leídas, nuevas y de TI en la base);
- **Abrir Chrome**, para iniciar sesión en Encuentra Empleo;
- **Actualizar** (rápido, o con requisitos), con el avance en vivo y la opción de detener;
- **Actualizar todas** las demás plataformas (no necesitan Chrome: INEC, CNT, concursos públicos, Petroecuador,
  CELEC, bancos y cooperativas, empresas de software y empresas remotas), o cada una con su botón;
- **Publicar en la página** y el **historial** de actualizaciones.

Al terminar cada actualización, las ofertas de TI se publican solas en la
[página de Oportunidades de Computación UPEC](https://v0-student-orcin.vercel.app/oportunidades) (ver
[Publicar en una página web](#publicar-en-una-página-web)).

## Uso por comandos

1. **Abre Chrome para el scraper** (usa un perfil aparte, no toca tu Chrome normal):

   ```powershell
   .\abrir_chrome.ps1
   ```

2. En esa ventana **inicia sesión a mano** en Encuentra Empleo y entra a la búsqueda de ofertas. El scraper nunca
   pide ni guarda tu usuario ni tu contraseña: usa la sesión que tú abres (el portal tiene verificación anti-bots).

3. **Descarga las ofertas**:

   ```powershell
   python scraper.py areas                                     # lista las áreas laborales
   python scraper.py buscar --detalle                           # todas las áreas, con requisitos
   python scraper.py buscar --areas informatica --detalle       # solo áreas que contengan "informatica"
   python scraper.py buscar --palabras python datos --provincia pichincha
   python scraper.py buscar --forzar                            # aunque la última descarga sea de hace < 12 h
   ```

   Si el portal deja de cargar desde tu conexión, probablemente limitó tu IP por exceso de peticiones: espera unas
   horas sin usar el scraper.

   El resultado queda en `salida/ofertas_AAAAMMDD_HHMM.xlsx`, y cada descarga se guarda sola en la base
   `salida/ofertas.db` con su registro de actualización (estado `ok`, o `parcial` si se cortó).

4. **Última actualización y conteos**:

   ```powershell
   python bdd.py estado                                              # última actualización y conteos
   python bdd.py importar salida/datos/ofertas_AAAAMMDD_HHMM.json   # carga una descarga anterior en la base
   ```

5. **Reclasificar** una descarga sin volver a entrar al portal (por ejemplo, después de mejorar las reglas de
   `sectores.py`):

   ```powershell
   python scraper.py clasificar salida/datos/ofertas_AAAAMMDD_HHMM.json
   ```

## Otras plataformas en la misma base

`plataformas.py` guarda en `salida/ofertas.db`, con su registro de actualización, las ofertas de:

| Plataforma | De dónde salen |
|---|---|
| INEC, CNT EP, concursos públicos (Encuentra Empleo), EP Petroecuador, CELEC EP, bancos y cooperativas, empresas de software (Workable) | JSON públicos que recolecta a diario el [sitio de Oportunidades de Computación UPEC](https://github.com/Computacion-UPEC/student) |
| Empresas remotas (Get on Board, Workable, Greenhouse, Lever) | El buscador `scripts/buscar-ofertas.mjs` de una carpeta vecina `BecasChamba` (variable `BECASCHAMBA_REPO`); si no lo tienes, esa plataforma marca error y las demás siguen |

```powershell
python plataformas.py lista      # plataformas disponibles
python plataformas.py inec cnt   # actualiza las indicadas
python plataformas.py todas      # actualiza todas
```

## Publicar en una página web

`publicar_sitio.py` exporta un **resumen** de las ofertas *TI directo* (cargo, empresa, ubicación, remuneración,
cierre, sector y código; los requisitos completos se quedan en tu base) al JSON
`lib/data/encuentra-empleo-jobs.json` de un repositorio de Next.js, abre un pull request y lo fusiona cuando pasa el
check de Vercel. Si las ofertas no cambiaron, no hace nada.

```powershell
python publicar_sitio.py                  # exporta y publica (necesita git y la CLI de GitHub, gh)
python publicar_sitio.py --solo-exportar  # solo escribe el JSON
```

El repositorio del sitio se indica con la variable `SITIO_REPO` (por defecto `../student`). Para tu propio sitio,
cambia `DESTINO` y la forma del JSON en `exportar()`.

## Adapta la clasificación a tu perfil

Las reglas están en [`sectores.py`](sectores.py): expresiones regulares sobre el texto normalizado (sin tildes, en
minúsculas). Para otra profesión, cambia `SECTORES` y las funciones `perfil_ti` y `postulable_ti`. Se agradecen pull
requests con reglas para otras áreas.

## Uso responsable

- Úsalo con **tu propia cuenta** y para tu búsqueda de empleo. Si publicas ofertas, publica solo un resumen con el
  código y envía a la gente a postular en el portal oficial, como hace `publicar_sitio.py`.
- El scraper hace **pausas aleatorias largas** (3-6 s entre peticiones, 20-40 s cada 10-20 ofertas, 15-30 s entre
  áreas) y **no descarga si la última descarga fue hace menos de 12 horas** (salvo `--forzar`, o el panel te pide
  confirmar). El portal limita o bloquea temporalmente las IP con muchas peticiones: no quites estas protecciones.
- Usa el modo **rápido** (sin `--detalle`) para el día a día: `--detalle` abre cada oferta nueva y hace muchas más
  peticiones.
- Las ofertas pertenecen al portal y a los empleadores; verifica siempre la información y postula en el sitio oficial.
- Este proyecto no está afiliado al Ministerio del Trabajo.

## Estructura

| Archivo | Para qué sirve |
|---|---|
| `scraper.py` | Navega el portal con Playwright (conectado al Chrome abierto) y descarga las ofertas |
| `sectores.py` | Clasificación por sector, perfil TI, postulabilidad y región amazónica |
| `excel.py` | Genera el Excel con resumen y hojas por perfil |
| `bdd.py` | Base SQLite con todas las ofertas y el registro de actualizaciones |
| `panel.py`, `panel.html` | Panel local con el botón de actualizar y la última actualización |
| `plataformas.py` | Las demás plataformas de empleo, en la misma base |
| `publicar_sitio.py` | Publica el resumen de ofertas de TI en un sitio web (PR con fusión automática) |
| `Actualizar ofertas.bat` | Abre el panel con doble clic |
| `abrir_chrome.ps1` | Abre Chrome con un perfil propio y el puerto de depuración 9222 |

## Hoja de ruta

- [x] Descarga por áreas con reanudación
- [x] Clasificación por sector y perfil TI
- [x] Base de datos con registro de la última actualización
- [x] Guardar en la base automáticamente al terminar cada descarga
- [x] Botón para actualizar con un clic
- [x] Publicación automática en la página de Oportunidades
- [x] Otras plataformas en la misma base (INEC, CNT, concursos públicos, Petroecuador, CELEC, bancos, empresas de software y remotas)

## Licencia

[MIT](LICENSE)
