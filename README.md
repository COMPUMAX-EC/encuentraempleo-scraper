# Encuentra Empleo Ecuador Scraper

🇬🇧 **English** · 🇪🇨 [Español](README.es.md)

**Job-listing scraper for [Encuentra Empleo](https://encuentraempleo.trabajo.gob.ec)**, the job portal of Ecuador's
Ministry of Labour. It downloads **private-sector listings** and **public merit-based competitions** (with the PDF of
the **competition rules**, *bases del concurso*), classifies them by sector and tells you **which ones you can apply
to with your profile**. It is designed for IT professionals, but the rules can be adapted to any field.

Everything ends up in **Excel** and in a local **SQLite database** with a record of every update.

> Made in Ecuador by [Geovanny Basantes](https://github.com/COMPUMAX-EC). Use it personally and responsibly: see
> [Responsible use](#responsible-use). It is not affiliated with the Ministry of Labour.

## Why?

Searching Encuentra Empleo by hand is slow. Listings are shown 5 at a time, the **declared job area often does not
match** the position (there are tech-support listings filed under "Administration"), and the requirements only appear
when you open each listing. For public competitions you have to go institution by institution and download the rules
one by one. This tool does it for you and leaves you a filterable Excel file.

## What it does

**Private listings** (`scraper.py`)
- Walks every **job area** on the portal, or the ones you choose, with filters by province and keywords.
- Opens each listing and reads its **requirements**: education, field of study, experience, job knowledge, contract
  type, working hours, number of openings, and publication and closing dates.
- **Classifies by sector** from the listing's content, not the declared area. There are 26 sectors: cybersecurity,
  software development and data, IT support, networks and telecom, health, education, accounting, construction, oil
  and mining, among others.
- Flags **direct IT** and **IT-related** listings, and whether they are **open to IT graduates** based on the field
  of study they require.
- Marks the **Amazon region** and listings that **require Amazon residency** (Amazon Law).

**Public competitions** (`publicas.py`)
- Walks the ~1,400 public institutions and finds those with **open vacancies** accepting applications.
- Downloads the **competition-rules PDF** for each vacancy to `salida/bases/`.
- Reads from the PDF the **field of knowledge**, education and experience the position requires, and flags vacancies
  **open to IT graduates**.
- Produces an Excel file with closing date, monthly salary (RMU), institution, contact and a link to each PDF.

**Other platforms** (`plataformas.py`)
- INEC, CNT EP, EP Petroecuador, CELEC EP, banks and cooperatives, software and remote companies, and large private
  companies, in the same database.

**Local dashboard** (`panel.py`)
- One button to update, live progress, the last update of each platform and publishing the IT listings to a web page.

## How it works

The portal requires a **job-seeker account** and has an anti-bot check (Cloudflare Turnstile), so the tool **does not
log in or store your password**. You open a separate Chrome, log in yourself, and the scripts use that session with
[Playwright](https://playwright.dev/python/) (`connect_over_cdp`). They never click "Apply": they only read listings
and download the rules.

## Requirements

- Windows with Google Chrome. On Linux or macOS, just open Chrome with `--remote-debugging-port=9222`.
- Python 3.11 or later.
- A job-seeker account on Encuentra Empleo (free).

## Installation

```powershell
git clone https://github.com/COMPUMAX-EC/encuentraempleo-ecuador-scraper.git
cd encuentraempleo-ecuador-scraper
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Quick start: the dashboard

Double-click **`Actualizar ofertas.bat`** (or run `python panel.py`). A local dashboard opens at
`http://127.0.0.1:8765`, reachable only from your computer. From there you can:
- open Chrome to log in;
- update in quick mode or with requirements, with live progress and a stop option;
- choose which platforms to update;
- see the update history and publish the IT listings to the web page.

## Command-line use

1. **Open Chrome for the scraper.** It uses a separate profile and does not touch your normal Chrome:

   ```powershell
   .\abrir_chrome.ps1
   ```

2. In that window **log in by hand** to Encuentra Empleo.

3. **Private listings**:

   ```powershell
   python scraper.py areas                                  # list the job areas
   python scraper.py nuevas                                 # daily: new listings only (a few minutes)
   python scraper.py buscar                                 # weekly: all areas, with the declared area
   python scraper.py buscar --detalle                       # with each listing's requirements
   python scraper.py buscar --areas informatica --detalle   # only areas containing "informatica"
   python scraper.py buscar --palabras python datos --provincia pichincha
   python scraper.py buscar --forzar                        # even if the last download is less than 12 h old
   ```

   Output: `salida/ofertas_YYYYMMDD_HHMM.xlsx`, with the sheets Resumen, Postulables desde TI,
   TI - revisar requisitos, Todas and Requisitos por sector. Plus the database `salida/ofertas.db`.

4. **Public competitions and their rules**:

   ```powershell
   python publicas.py           # open vacancies + rules PDF -> salida/publicas_YYYYMMDD_HHMM.xlsx
   python publicas.py vacantes  # only institutions with vacancies (faster)
   python publicas.py excel     # rebuild the Excel from what is already downloaded, without visiting the portal
   ```

5. **Database and reclassification**, without going back to the portal:

   ```powershell
   python bdd.py estado                                             # last update and counts
   python bdd.py importar salida/datos/ofertas_YYYYMMDD_HHMM.json   # load an earlier download
   python scraper.py clasificar salida/datos/ofertas_YYYYMMDD_HHMM.json   # after changing sectores.py
   ```

6. **Other platforms** (no Chrome needed):

   ```powershell
   python plataformas.py lista      # available platforms
   python plataformas.py inec cnt   # update the ones listed
   python plataformas.py todas
   ```

   They come from the public JSON files collected daily by the
   [Computación UPEC Opportunities site](https://github.com/Computacion-UPEC/student). Remote companies use the
   search tool in the sibling folder `BecasChamba` (variable `BECASCHAMBA_REPO`); without it, that platform reports an
   error and the others continue.

## 20-minute session and resuming

The portal session expires after ~20 minutes. When that happens, the scraper stops and saves what it downloaded. To
continue, log in again and repeat the same command:
- `scraper.py buscar` continues from the area where it stopped and does not re-request requirements already read;
- `publicas.py` does not repeat PDFs already downloaded.

## Publishing to a web page

`publicar_sitio.py` exports a **summary** of the direct-IT listings (position, company, location, salary, closing
date, sector and code) to the JSON file `lib/data/encuentra-empleo-jobs.json` in a Next.js repository. Then it opens a
pull request and merges it when the Vercel check passes. If the listings did not change, it does nothing. The full
requirements stay in your database.

```powershell
python publicar_sitio.py                  # export and publish (needs git and the GitHub CLI, gh)
python publicar_sitio.py --solo-exportar  # only write the JSON
```

The site repository is set with the `SITIO_REPO` variable (default `../student`).

## Adapt the classification to your field

The rules are in [`sectores.py`](sectores.py). They are regular expressions over normalized text, without accents
and in lowercase (so the patterns match Spanish text). For another profession, change `SECTORES` and the functions
`perfil_ti` and `postulable_ti`. For public competitions, change `AREA_TI` in [`publicas.py`](publicas.py). Pull
requests with rules for other fields are welcome.

## Responsible use

- Use it with **your own account** and for your own job search. If you publish listings, publish only a summary with
  the code and send people to apply on the official portal.
- The scraper takes **long random pauses**: 3–6 s between requests, 20–40 s every 10–20 listings and 15–30 s between
  areas. It also **does not download if the last download was less than 12 hours ago** (unless `--forzar`). The
  portal throttles or temporarily blocks IPs with many requests: do not remove these protections.
- Day to day, use `scraper.py nuevas`: a single search that stops when it reaches listings it already knows. Once a
  week, `scraper.py buscar` walks every area and fills in the declared area.
- The listings belong to the portal and the employers. Always verify the information and apply on the official site.

## Structure

| File | Purpose |
|---|---|
| `scraper.py` | Private listings: browses the portal with Playwright connected to your Chrome |
| `publicas.py` | Public competitions: open vacancies and the competition-rules PDF |
| `sectores.py` | Sector classification, IT profile, eligibility and Amazon region |
| `excel.py` | Private-listings Excel with a summary and per-profile sheets |
| `bdd.py` | SQLite database with every listing and the update log |
| `plataformas.py` | Other job platforms in the same database |
| `panel.py`, `panel.html` | Local dashboard with buttons and live progress |
| `sitio_github.py` | Runs the site's collectors on GitHub Actions on demand (with `gh`) |
| `publicar_sitio.py` | Publishes the IT-listings summary to a website |
| `abrir_chrome.ps1` | Opens Chrome with its own profile and debugging port 9222 |
| `Actualizar ofertas.bat` | Opens the dashboard with a double-click |
| `CLAUDE.md` | Technical notes on the portal for working with Claude Code without re-exploring it |

Script, command and output names are in Spanish, matching the portal.

## Roadmap

- [x] Private listings by area, with resume
- [x] Classification by sector and IT profile
- [x] Database with the update log
- [x] Dashboard with an update button
- [x] Automatic publishing to the Opportunities page
- [x] Other platforms in the same database
- [x] Public competitions with download of the competition rules
- [ ] Alerts for new IT listings

## License

[MIT](LICENSE)
