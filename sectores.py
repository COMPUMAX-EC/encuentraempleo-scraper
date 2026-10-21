"""Clasificación de ofertas por sector (para preparar un perfil por sector).

Reglas por palabras clave sobre el texto normalizado (sin tildes, minúsculas). Se prueba primero
el cargo y, si no coincide nada, las actividades. El orden importa: gana la primera regla que coincide.
"""

import re
import unicodedata
from collections import Counter

SECTORES: list[tuple[str, str]] = [
    ("Ciberseguridad", r"ciberseguridad|seguridad(es)? informatica|vulnerabilidad"),
    ("Desarrollo de software y datos",
     r"\bsoftware\b(?! (contable|de ventas|de gestion|de control|educativo))|desarroll\w* de (plataformas|sistemas|aplicaciones)"
     r"|programador|cubos de informacion|analista de datos|registros administrativos"),
    ("Soporte TI y mesa de ayuda", r"soporte tecnico|mesa de ayuda|\btics?\b|tecnologias de la informacion|servicio tecnico"),
    ("Redes y telecomunicaciones",
     r"telecomunic|fibra optica|\bredes de datos|wireless|inalambric|otdr|cableado estructurado"),
    ("Electrónica y seguridad electrónica",
     r"electronic|camaras|alarma|programad[oa]\b|instalacion y programacion|celulares"),
    # Sectores de oficios y servicios: se reconocen sobre todo por el cargo.
    ("Educación y docencia",
     r"docente|profesor|tutor|educador|parvulari|inicial|maestr[oa] de|catedratic|instructor|rector\b|ingles"),
    ("Salud",
     r"fisioterap|enfermer|medic[oa]\b|medicina|odontolog|psicolog|terapeut|farmac|nutricion|obstetri|fonoaudiolog"
     r"|laboratorista clinic|tecnologo medico|paramedic|auxiliar de enfermeria|quimico farmaceutico|cosmetolog|optometr"
     r"|psiquiatr|ginecolog|pediatr|enfermedades|promocion de la salud|belleza"),
    ("Hotelería, cocina y turismo",
     r"cocin|chef|meser|salonero|bartender|barista|hotel|camarer|ama de llaves|panader|pasteler|recepcionista de hotel|turis"),
    ("Transporte y conducción",
     r"chofer|conductor|motorizado|operador de (volqueta|maquinaria|camion|excavadora|retroexcavadora|tractor|cargadora|grua)"
     r"|licencia tipo|repartidor|mensajer|marinero|timonel|maquinista"),
    ("Seguridad física", r"guardia|vigilante|guardian|agente de seguridad"),
    ("Limpieza y servicios generales", r"limpieza|conserje|servicios generales|jardiner|auxiliar de servicios|obrer|estibador"),
    ("Contabilidad y finanzas",
     r"contad[oa]r|contable|contabilidad|cartera|credito|cobranz|financier|tesorer|cajer|auditor|tribut|costos|facturad"
     r"|recaudador|\bcpa\b"),
    ("Talento humano", r"talento humano|recursos humanos|nomina|seleccion de personal|reclutamiento"),
    ("Legal", r"abogad|juridic|legal|notari"),
    ("Marketing, diseño y comunicación",
     r"marketing|disenador|diseno grafico|community|publicid|comunicacion|periodist|fotograf|audiovisual|rotulista"),
    ("Petróleo, gas y minería",
     r"wireline|completacion|well testing|bombeo hidraulico|\bmtu\b|tubulares|petroler|\bminas\b|minero|fluidos de estimulacion"
     r"|cunero|encuellador|vacuum|rigger|campamentero"),
    ("Eléctrica, instrumentación y automatización",
     r"electric|instrument|automatizacion|\bplc\b|generador|fotovoltaic|liniero|alta tension|central"),
    ("Seguridad, salud ocupacional y ambiente",
     r"seguridad y salud|salud ocupacional|\bqhse\b|\bssa\b|\bhse\b|ambiental|seguridad vial|contra incendios"
     r"|seguridad industrial|supervisor de seguridad|emergencias"),
    ("Construcción y obra civil",
     r"civil|\bobra\b|construcc|topograf|suelos|hidrolog|vial|avaluador|valoracion|izaje|fiscalizacion|gestion tecnica"
     r"|albanil|\bpeon\b|capataz|pulidor|montajista|arquitect|vidrio"),
    ("Mecánica, soldadura y mantenimiento",
     r"mecanic|mantenimiento|tornero|torno|sold|suelda|tubero|hvac|refrigeracion|cnc|plegadora|montacargas"
     r"|pintura industrial|enderezado|polifuncional"),
    ("Calidad, laboratorio y producción",
     r"calidad|laboratori|produccion|inspecci|inspector|ensayos no destructivos|calibracion|sistemas? de gestion|planta"),
    ("Ventas y atención al cliente",
     r"vendedor|ventas|comercializ|asesor de servicio|atencion al cliente|comecial|comercial|negocios|preventa|despachador"),
    ("Logística, compras y bodega", r"compras|bodeg|logistic|aduaner"),
    ("Proyectos y planificación", r"proyecto|planificacion"),
    ("Administrativo", r"administrativ|asistente|auxiliar|secretari|recepcionista|archivo|oficinista|digitador"),
]
OTROS = "Otros"

# Relevancia para un profesional TI, mirando el contenido de la oferta y no el área declarada
# (que a veces está mal puesta). Palabras sueltas como "software", "base de datos", "servidores"
# o "programación" dan muchos falsos positivos ("software contable", "servidores públicos",
# "programación diaria"), así que se exige un cargo TI o una actividad TI concreta.
TI_CARGO = (
    r"informatic|software|ciberseguridad|\btics?\b|tecnologias? de (la )?informacion|soporte tecnico|mesa de ayuda"
    r"|help ?desk|programador|desarrollador (de software|web|full|front|back|movil)|analista de sistemas"
    r"|ingenier\w* (en )?sistemas|administrador de (redes|sistemas|bases? de datos)|redes y|telecomunic"
    r"|base(s)? de datos|\bdba\b|devops|\bcloud\b|ciencia de datos|analista de datos|cientifico de datos"
    r"|desarrollo web|\bweb\b|\bti\b|\bit\b"
)
TI_ACTIVIDAD = (
    r"desarrollo de (software|aplicaciones|sistemas|plataformas informaticas)|programacion de (software|aplicaciones|sistemas)"
    r"|administra\w* (de )?(servidores|redes|bases? de datos|infraestructura (it|tecnologica))"
    r"|soporte (tecnico )?(informatico|a usuarios|de primer nivel)|mesa de ayuda|ciberseguridad"
    r"|seguridad(es)? informatica|vulnerabilidades|fibra optica|aplicativos informaticos|cableado estructurado"
)
TI_AFIN = (
    r"power ?bi|analisis de datos|analista de datos|\bscada\b|\bplc\b|automatizacion|\bcrm\b|\berp\b"
    r"|\bsap (r3|b1|s/?4|hana)|manejo de sap|en sap\b|marketing digital|community manager|redes sociales"
    r"|e-?commerce|comercio electronico|tienda (en linea|online)|sitios? web|paginas? web|cctv"
    r"|camaras de (seguridad|vigilancia)|seguridad electronica|alarmas|scrum|metodologias agiles"
    r"|inteligencia artificial|microsoft project"
)
TI_AFIN_CARGO = r"electronic|estadistic|digital|online"


PROVINCIAS_AMAZONICAS = ("sucumbios", "orellana", "napo", "pastaza", "morona santiago", "zamora chinchipe")
# Ley Orgánica de la Circunscripción Territorial Especial Amazónica: prioriza a residentes amazónicos.
REQUISITO_AMAZONICO = r"amazon|circunscripcion|\bctea\b"


def amazonia(oferta: dict) -> dict:
    """Dos datos distintos: si la oferta está en la Amazonía y si exige ser residente amazónico."""
    ubicacion = normalizar(oferta.get("ubicacion", ""))
    campos = ("cargo", "actividades", "conocimientos", "info_adicional", "descripcion_enlace")
    texto = normalizar(" ".join(oferta.get(c, "") for c in campos))
    return {
        "region_amazonica": "Sí" if ubicacion.startswith(PROVINCIAS_AMAZONICAS) else "",
        "requisito_amazonico": "Sí" if re.search(REQUISITO_AMAZONICO, texto) else "",
    }


AREAS_ESTUDIO_TI = ("informatica", "internet", "sin area")


def postulable_ti(oferta: dict) -> str:
    """¿Puede postular un profesional TI? Depende del área de estudios que exige la oferta."""
    if not oferta.get("perfil_ti"):
        return ""
    if oferta.get("requisito_amazonico") == "Sí":
        return "Solo residentes amazónicos"
    area = normalizar(oferta.get("area_estudios", ""))
    if oferta["perfil_ti"] == "TI directo" or not area or area.startswith(AREAS_ESTUDIO_TI):
        return "Sí"
    return f"Revisar: pide {oferta['area_estudios']}"


def perfil_ti(oferta: dict) -> str:
    cargo = normalizar(oferta.get("cargo", ""))
    texto = normalizar(" ".join(oferta.get(c, "") for c in ("actividades", "conocimientos", "info_adicional")))
    if (re.search(TI_CARGO, cargo) or re.search(TI_ACTIVIDAD, texto)
            or "informatica" in normalizar(oferta.get("area_estudios", ""))):
        return "TI directo"
    if re.search(TI_AFIN_CARGO, cargo) or re.search(TI_AFIN, f"{cargo} {texto}"):
        return "TI afín"
    return ""

# Palabras que no aportan al resumen de habilidades.
VACIAS = set("""
de la el los las en y a con para del al por o u e un una su sus se que como lo le es son segun
entre sobre sin desde hasta mas cada otros otras etc tipo forma area areas cargo funciones actividades
realizar ejecutar apoyar apoyo asegurar garantizar cumplir cumplimiento control controlar gestion gestionar
experiencia minimo anos ano trabajo trabajos empresa cliente clientes equipos equipo sistemas sistema
procesos proceso elaboracion elaborar informes informe seguimiento mantener nivel acuerdo puesto
""".split())


def normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def clasificar(oferta: dict) -> str:
    for campo in ("cargo", "actividades"):
        texto = normalizar(oferta.get(campo, ""))
        for sector, patron in SECTORES:
            if re.search(patron, texto):
                return sector
    return OTROS


def palabras_frecuentes(ofertas: list[dict], n: int = 15) -> list[tuple[str, int]]:
    """Términos más repetidos en cargo y actividades: guía de qué destacar en el perfil."""
    conteo: Counter = Counter()
    for o in ofertas:
        texto = normalizar(f"{o['cargo']} {o['actividades']} {o.get('conocimientos', '')}")
        # Una vez por oferta, para que una oferta larga no domine el resumen.
        conteo.update({p for p in re.findall(r"[a-z]{4,}", texto) if p not in VACIAS})
    return conteo.most_common(n)


def resumen_markdown(ofertas: list[dict]) -> str:
    por_sector: dict[str, list[dict]] = {}
    for o in ofertas:
        por_sector.setdefault(o["sector"], []).append(o)

    lineas = ["# Ofertas por sector", "", f"Total: {len(ofertas)} ofertas", ""]
    lineas += ["| Sector | Ofertas | TI directo | TI afín |", "|---|---|---|---|"]
    orden = sorted(por_sector.items(), key=lambda kv: -len(kv[1]))
    for s, os in orden:
        d = sum(o["perfil_ti"] == "TI directo" for o in os)
        a = sum(o["perfil_ti"] == "TI afín" for o in os)
        lineas.append(f"| {s} | {len(os)} | {d} | {a} |")

    for nivel in ("TI directo", "TI afín"):
        ti = [o for o in ofertas if o["perfil_ti"] == nivel]
        lineas += ["", f"## Para perfil TI: {nivel} ({len(ti)})", ""]
        lineas += ["| Código | Cargo | Área declarada | Sector | Ubicación | Remuneración | Exige residente amazónico |",
                   "|---|---|---|---|---|---|---|"]
        lineas += [
            f"| {o['codigo']} | {o['cargo']} | {o.get('area_laboral', '')} | {o['sector']} | {o['ubicacion']} "
            f"| {o['remuneracion']} | {o.get('requisito_amazonico', '')} |"
            for o in ti
        ]

    for sector, os in orden:
        lineas += ["", f"## {sector} ({len(os)})", ""]
        sueldos = Counter(o["remuneracion"] for o in os).most_common()
        lineas.append("**Remuneraciones:** " + ", ".join(f"{r} ({c})" for r, c in sueldos))
        lineas.append("")
        # Requisitos agregados (solo si se descargó con --detalle).
        for campo, titulo in (("instruccion", "Instrucción"), ("experiencia", "Experiencia"),
                              ("area_estudios", "Área de estudios"), ("tipo_contrato", "Contrato"),
                              ("tipo_empleador", "Empleador")):
            valores = Counter(o[campo] for o in os if o.get(campo)).most_common(6)
            if valores:
                lineas.append(f"**{titulo}:** " + ", ".join(f"{v} ({c})" for v, c in valores))
                lineas.append("")
        lineas.append("**Términos más pedidos:** " + ", ".join(f"{p} ({c})" for p, c in palabras_frecuentes(os)))
        lineas += ["", "| Código | Cargo | Empresa | Ubicación | Remuneración | Publicado |", "|---|---|---|---|---|---|"]
        for o in os:
            lineas.append(
                f"| {o['codigo']} | {o['cargo']} | {o['empresa']} | {o['ubicacion']} | {o['remuneracion']} | hace {o['publicado_hace']} |"
            )
    return "\n".join(lineas) + "\n"
