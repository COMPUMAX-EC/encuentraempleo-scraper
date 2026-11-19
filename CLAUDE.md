# Encuentra Empleo scraper: quick guide for Claude

Goal: download listings from encuentraempleo.trabajo.gob.ec (Ecuador). The main interest is listings an IT
professional can apply to. **Do not explore the site again**: everything needed is here and in the README.

## Rules
- Never log in or type credentials. The user opens Chrome with `abrir_chrome.ps1` (port 9222) and logs in by
  hand. The scripts connect with `connect_over_cdp`.
- Never click "Aplicar" or "Postular" (Apply). Only read data and download PDFs.
- Do not shorten the pauses (`PAUSA_*` in scraper.py) or remove the 12 h rule (`--forzar`): the portal blocks IPs
  with many requests.
- Launch long downloads with `run_in_background` and do not poll. When done, read the log with
  `tr '\r' '\n' < log | grep -v 'pág\.'`.
- Before scraping the portal, check whether `plataformas.py concursos` is enough (JSON collected by the
  Opportunities site): it makes no requests to the portal.
- Commits go under the user's name, without a co-author trailer.

## Commands (from this folder, with `.venv/Scripts/python.exe -u`)
| What | Command | Time |
|---|---|---|
| Private, daily (new only, one search, stops after 2 known pages) | `scraper.py nuevas` | a few minutes |
| Private by area (weekly; fills in the declared area) | `scraper.py buscar` | 25–35 min, resumes |
| Private with requirements | `scraper.py buscar --detalle` | over 1 h, resumes |
| Rebuild the Excel without Chrome | `scraper.py clasificar salida/datos/ofertas_X.json` | seconds |
| Public competitions + rules PDFs | `publicas.py` | about 20 min (session lasts about 20 min) |
| Only institutions with vacancies (without walking all 175 pages) | `publicas.py vacantes` | about 5 min |
| Rebuild the public-competitions Excel | `publicas.py excel` | seconds |
| Frequency of IT vacancies per institution | `historial.py` (or `historial.py excel` without logging a run) | seconds |
| Weekly run (task "Encuentra Empleo - concursos semanal", Monday 9:00) | `semanal.ps1` | about 20 min, asks you to log in |
| Database status | `bdd.py estado` | |
| Other platforms | `plataformas.py todas` | no Chrome |
| Daily run of the other platforms (task "Encuentra Empleo - plataformas diaria", 20:30; log in `salida/datos/log_diaria.txt`) | `diaria.cmd` | about 5 min |
| Daily series from the git history of the site (`../student`) and BecasChamba → `observaciones` table | `historico.py` (or `--desde YYYY-MM-DD`) | seconds, no duplicates |
| Portals needing a real browser or account (El Rosado, CACPECO/Laburo) | `portales_navegador.py` | 1 min, El Rosado session |
| CACPECO only with its own Chrome (Laburo only loads with the window in front: on demand or in semanal.ps1) | `portales_navegador.py --fuente cacpeco --chrome-propio` | seconds, opens a window |
| Publish to the site (IT and entry-level listings, IT and entry-level competitions with rules, platform status) | `publicar_sitio.py` | PR + merge |
| Dashboard with buttons | `panel.py` (or `Actualizar ofertas.bat`) | |

Output: `salida/*.xlsx` and `salida/ofertas.db` (tables `ofertas`, `observaciones` = one row per listing and day
it was published, and `actualizaciones`). Intermediate JSON goes in `salida/datos/` and the rules PDFs in
`salida/bases/`.

## Site quirks (JSF / PrimeFaces 6.2)
- **The session lasts about 20 min.** When it expires, the AJAX POST returns 302 but the tab still shows
  "Bienvenido" with stale data. `esperar_ajax` raises `SesionCaducada`. scraper.py resumes by area
  (`progreso.json`, `cache_detalle.json`) and publicas.py does not repeat PDFs already downloaded. Ask the user to
  log in again and relaunch the same command.
- Private (`busquedaOferta.jsf`): the dropdowns are hidden `select` elements (`FormSearch:areaLaboral_input`). Set
  `.value` and click the magnifier (`#FormSearch a:has(img[src*='busca.png'])`). Pagination:
  `formBuscaOferta:pagina_input` + a `change` event. 5 listings per page.
- If the total is a multiple of 5, the site announces an extra page that arrives empty: not an error. Areas with no
  listings have no paginator.
- Private listing detail: click the card, read `#formVerOferta` (disabled dropdowns hold the selected option) and
  close with `PF('VerOfertaDialog').hide()`.
- Public (`busquedaOfertaPublica.jsf`): about 1,400 institutions, 8 per page (`formBuscaPublica:itemsTable`).
  - "Nuevas vacantes" (2nd column) opens `PF('vacAplDgl')` / `vacantesAplMpForm:vacantesTableMp`: competitions
    accepting applications, with `data-countdown` = closing date.
  - "Puesto en concurso" is the history (void, deserted, winners; hundreds of thousands of rows). **Do not walk
    it.**
  - "Ver bases del concurso" is a non-AJAX submit that returns `BasesDelConcurso.pdf`; capture it with
    `expect_download`.
  - The PDF contains `AREA DEL CONOCIMIENTO: ... TITULO:`, which says which degrees it accepts.
- The job area each listing declares is often wrong. IT relevance is computed from content in `sectores.py`. Single
  words give false positives ("software contable", "servidores públicos", "soldadura TIC"), so direct IT requires an
  IT job title, IT activities or the field of study Informática.
