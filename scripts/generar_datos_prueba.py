#!/usr/bin/env python3
"""
scripts/generar_datos_prueba.py
Genera pacientes SINTÉTICOS y los envía por el bus (HSB), igual que lo harían los
sistemas legados de cada sede. Así los datos llegan a FHIR (HAPI) y a la base de su sede
(PostgreSQL o MongoDB) pasando por traducción, validación, idempotencia y auditoría.

    python3 scripts/generar_datos_prueba.py                 # 60 pacientes, semilla 2026
    python3 scripts/generar_datos_prueba.py --pacientes 120 --semilla 7
    python3 scripts/generar_datos_prueba.py --url http://192.168.1.94:8001

- Sede 1 (Sincelejo, PostgreSQL): HL7 v2 ADT^A03 completos (segmentos Z, NK1, IN1, RXE, AL1) y ORU^R01.
- Sede 2 (Cartagena, MongoDB):   HL7 v2 ADT^A01 / ADT^A03 y ORU^R01.
- Sede 3 (Corozal, PostgreSQL):  CSV legado extendido con columnas de los 57 campos.
- ~25 % de los pacientes se atienden en una segunda sede y ~10 % en las tres.
- ~7 % de mensajes llevan errores a propósito (documento, sexo o diagnóstico) -> RECHAZADO.
- ~5 % se reenvían -> DUPLICADO.
Es determinista: con la misma semilla genera los mismos mensajes, así que volver a
ejecutarlo no crea copias (el bus responde "duplicado").
Solo usa la biblioteca estándar de Python. Todos los datos son ficticios.
"""

import argparse
import base64
import json
import os
import ssl
import random
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

NOMBRES_F = ["Ana", "Laura", "Camila", "Valentina", "Daniela", "Mariana", "Sofía", "Isabella", "Paula", "Juliana",
             "Natalia", "Carolina", "Andrea", "Luisa", "Gabriela", "Diana", "Paola", "Sara", "Adriana", "Mónica"]
NOMBRES_M = ["Carlos", "Andrés", "Juan", "Luis", "Jorge", "Miguel", "Santiago", "Sebastián", "Diego", "Felipe",
             "Alejandro", "Mateo", "David", "Daniel", "Óscar", "Ricardo", "Javier", "Fernando", "Esteban", "Camilo"]
APELLIDOS = ["Pérez", "Gómez", "Rodríguez", "Martínez", "García", "López", "Hernández", "Díaz", "Torres", "Ramírez",
             "Vargas", "Romero", "Mendoza", "Castro", "Ortiz", "Rojas", "Suárez", "Blanco", "Mercado", "Payares",
             "Montes", "Salgado", "Arrieta", "Banquez", "Julio", "Cassiani", "Herazo", "Monterrosa", "Pacheco", "Villalba"]
MUNICIPIOS = {1: ["70001", "70708", "70215"], 2: ["13001", "13430", "13836"], 3: ["70215", "70001", "70670"]}
CIUDAD = {"70001": "Sincelejo", "70708": "San Marcos", "70215": "Corozal", "13001": "Cartagena",
          "13430": "Magangué", "13836": "Turbaco", "70670": "Sampués"}
EPS = ["Nueva EPS", "Coosalud EPS", "Sanitas EPS", "Salud Total", "Mutual Ser", "Famisanar", "Sura EPS"]
OCUPACIONES = ["Docente", "Comerciante", "Agricultor", "Enfermera", "Estudiante", "Conductor", "Ama de casa",
               "Ingeniero", "Pescador", "Mecánico", "Contadora", "Vendedor ambulante", "Pensionado"]
PROFESIONALES = {1: [("MED-01", "Vega", "Laura"), ("MED-04", "Bermejo", "Alfonso")],
                 2: [("MED-02", "Ruiz", "Mateo"), ("MED-05", "Gomez", "Patricia")],
                 3: [("MED-03", "Orozco", "Camilo"), ("MED-01", "Vega", "Laura")]}
# CIE-10 (con su texto local para el CSV legado de la sede 3, tabla ejemplos/05_ref_terminologia.csv)
DIAGNOSTICOS = [("J45.9", "Asma", "ASMA"), ("I10", "Hipertensión esencial", "HIPERTENSION"),
                ("E11.9", "Diabetes mellitus tipo 2", "DIABETES"), ("A09", "Diarrea y gastroenteritis", "DIARREA"),
                ("N39.0", "Infección de vías urinarias", "INFECCION URINARIA"), ("M54.5", "Lumbago", "LUMBAGO"),
                ("J18.9", "Neumonía", "NEUMONIA"), ("R51", "Cefalea", "CEFALEA")]
RELACIONADOS = [("E78.5", "Hiperlipidemia"), ("E66.9", "Obesidad"), ("K29.7", "Gastritis"), ("F41.9", "Ansiedad"),
                ("D64.9", "Anemia"), ("J30.4", "Rinitis alérgica")]
CAUSAS = {"J45.9": "Dificultad respiratoria y sibilancias", "I10": "Cifras tensionales elevadas y cefalea",
          "E11.9": "Control de glicemia y polidipsia", "A09": "Deposiciones líquidas y vómito",
          "N39.0": "Disuria y fiebre", "M54.5": "Dolor lumbar tras esfuerzo", "J18.9": "Fiebre, tos y dolor torácico",
          "R51": "Cefalea intensa de 2 días"}
LABS = [("718-7", "Hemoglobina", "g/dL", 9.5, 16.5), ("2345-7", "Glucosa en suero", "mg/dL", 70, 260),
        ("2160-0", "Creatinina en suero", "mg/dL", 0.5, 2.1), ("8480-6", "Presión arterial sistólica", "mm[Hg]", 95, 175),
        ("6690-2", "Leucocitos en sangre", "10*3/uL", 4, 18), ("1988-5", "Proteína C reactiva", "mg/L", 0.5, 90)]
MEDICAMENTOS = {"J45.9": ("Salbutamol 100 mcg inhalador", "2", "inh", "IH", "Cada 6 horas", 10, 1),
                "I10": ("Losartán 50 mg tableta", "50", "mg", "PO", "Cada 12 horas", 30, 60),
                "E11.9": ("Metformina 850 mg tableta", "850", "mg", "PO", "Cada 12 horas", 30, 60),
                "A09": ("Sales de rehidratación oral sobre", "1", "sobre", "PO", "Después de cada deposición", 3, 6),
                "N39.0": ("Nitrofurantoína 100 mg cápsula", "100", "mg", "PO", "Cada 6 horas", 7, 28),
                "M54.5": ("Naproxeno 250 mg tableta", "250", "mg", "PO", "Cada 12 horas", 5, 10),
                "J18.9": ("Amoxicilina 500 mg cápsula", "500", "mg", "PO", "Cada 8 horas", 7, 21),
                "R51": ("Acetaminofén 500 mg tableta", "500", "mg", "PO", "Cada 8 horas", 3, 9)}
ALERGIAS = ["Penicilina", "AINES", "Sulfas", "Mariscos", "Látex"]


def seg(nombre, campos):
    n = max(campos)
    partes = [nombre] + [""] * n
    for k, v in campos.items():
        partes[k] = str(v)
    return "|".join(partes)


class Generador:
    def __init__(self, semilla):
        self.r = random.Random(semilla)
        self.semilla = semilla
        self.n = 0

    def persona(self, i):
        r = self.r
        sexo = r.choice("MF")
        nombre = r.choice(NOMBRES_F if sexo == "F" else NOMBRES_M)
        if r.random() < 0.35:
            nombre += " " + r.choice(NOMBRES_F if sexo == "F" else NOMBRES_M)
        apellidos = f"{r.choice(APELLIDOS)} {r.choice(APELLIDOS)}"
        nac = datetime(1940, 1, 1) + timedelta(days=r.randint(0, 365 * 82))
        sede = r.choice([1, 2, 3])
        muni = r.choice(MUNICIPIOS[sede])
        return {"doc": str(r.randint(10_000_000, 1_299_999_999)), "sexo": sexo, "nombres": nombre, "apellidos": apellidos,
                "nac": nac.strftime("%Y%m%d"), "sede": sede, "muni": muni,
                "tipo_doc": "TI" if nac.year > 2008 else "CC", "zona": r.choice(["01", "01", "01", "02"]),
                "dir": f"Calle {r.randint(1, 80)} # {r.randint(1, 60)}-{r.randint(1, 99)}, {CIUDAD[muni]}",
                "tel": f"3{r.randint(0, 2)}{r.randint(0, 9)}{r.randint(1000000, 9999999)}",
                "correo": f"{nombre.split()[0].lower()}.{apellidos.split()[0].lower()}{i}@correo.test"
                          .replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u"),
                "eps": r.choice(EPS), "ocupacion": r.choice(OCUPACIONES), "etnia": r.choice(["06"] * 6 + ["05", "01"]),
                "genero": "02" if sexo == "F" else "01",
                "resp": (f"{r.choice(NOMBRES_F + NOMBRES_M)} {apellidos.split()[0]}", r.choice(["01", "03", "04", "02"]),
                         f"3{r.randint(0, 2)}{r.randint(10000000, 99999999)}")}

    def atencion(self, p, sede):
        r = self.r
        self.n += 1
        ingreso = datetime(2026, 1, 5, 7, 0) + timedelta(days=r.randint(0, 305), minutes=r.randint(0, 720))
        dx = r.choice(DIAGNOSTICOS)
        clase = r.choice(["E", "E", "O", "O", "I"])
        return {"n": self.n, "sede": sede, "ingreso": ingreso, "dx": dx, "clase": clase,
                "triage": r.choice(["2", "3", "3", "4", "5"]) if clase == "E" else "",
                "egreso": r.random() < 0.7, "salida": ingreso + timedelta(hours=r.randint(2, 96)),
                "prof": r.choice(PROFESIONALES[sede]), "lab": r.random() < 0.6, "med": r.random() < 0.65,
                "rel": [r.choice(RELACIONADOS) for _ in range(r.choice([0, 0, 1, 2]))],
                "alergia": r.choice(ALERGIAS) if r.random() < 0.2 else None,
                "error": r.choice(["doc", "sexo", "dx"]) if r.random() < 0.07 else None,
                "visita": f"V-S{sede}-G{self.semilla}-{self.n:04d}"}

    # ── HL7 ──────────────────────────────────────────────────────────────
    def hl7(self, p, a):
        doc = "AB" + p["doc"][2:] if a["error"] == "doc" else p["doc"]
        sexo = "X" if a["error"] == "sexo" else p["sexo"]
        tipo = "ADT^A03" if a["egreso"] else "ADT^A01"
        f = lambda d: d.strftime("%Y%m%d%H%M")
        cod, prof_ap, prof_nom = a["prof"]
        lineas = [f"MSH|^~\\&|HIS_SEDE{a['sede']}|SEDE{a['sede']}|HSB|CENTRAL|{f(a['ingreso'])}||{tipo}|GEN-{self.semilla}-{a['n']:04d}|P|2.5",
                  seg("PID", {1: "1", 3: f"{doc}^^^HIS^{p['tipo_doc']}", 5: f"{p['apellidos']}^{p['nombres']}",
                              7: p["nac"], 8: sexo, 11: f"{p['dir']}^^{CIUDAD[p['muni']]}^^^CO^^^{p['muni']}",
                              13: f"{p['tel']}^^^{p['correo']}", 22: p["etnia"], 28: "CO"}),
                  seg("NK1", {1: "1", 2: "^".join(reversed(p["resp"][0].split(" ", 1))), 3: p["resp"][1], 5: p["resp"][2]}),
                  seg("PV1", {1: "1", 2: a["clase"], 7: f"{cod}^{prof_ap}^{prof_nom}", 14: self.r.choice(["01", "01", "02"]),
                              19: a["visita"], 36: "01" if a["egreso"] else "", 44: f(a["ingreso"]),
                              45: f(a["salida"]) if a["egreso"] else ""}),
                  seg("PV2", {3: "^" + CAUSAS[a["dx"][0]]}),
                  seg("IN1", {1: "1", 4: p["eps"]}),
                  seg("ZPI", {1: p["genero"], 2: p["ocupacion"], 3: "N", 4: "08", 7: p["zona"]}),
                  seg("ZPV", {1: "01", 2: f(a["ingreso"] + timedelta(minutes=5)) if a["triage"] else "", 3: a["triage"]})]
        dx_cod, dx_desc = (a["dx"][2], a["dx"][1]) if a["error"] == "dx" else (a["dx"][0], a["dx"][1])
        sistema = "L" if a["error"] == "dx" else "I10"
        fecha_dx = a["ingreso"].strftime("%Y%m%d")
        lineas.append(seg("DG1", {1: "1", 3: f"{dx_cod}^{dx_desc}^{sistema}", 5: fecha_dx, 6: "A", 15: "1"}))
        if a["egreso"]:
            lineas.append(seg("DG1", {1: "2", 3: f"{dx_cod}^{dx_desc}^{sistema}", 5: fecha_dx, 6: "F", 15: "1"}))
            for i, (c, d) in enumerate(a["rel"], start=2):
                lineas.append(seg("DG1", {1: str(i + 1), 3: f"{c}^{d}^I10", 5: fecha_dx, 6: "F", 15: str(i)}))
        if a["med"]:
            desc, cant, uni, via, frec, dias, unidades = MEDICAMENTOS[a["dx"][0]]
            lineas += [seg("ORC", {1: "NW", 12: cod}),
                       seg("RXE", {1: f"^{frec}^D{dias}", 2: f"^{desc}", 3: cant, 5: uni, 10: unidades}),
                       seg("RXR", {1: via}), seg("ZRX", {1: "01"})]
        if a["alergia"]:
            lineas.append(seg("AL1", {1: "1", 2: "DA", 3: f"^{a['alergia']}"}))
        if a["egreso"]:
            dias_inc = self.r.choice([0, 0, 1, 2, 3, 5])
            lineas.append(seg("ZEG", {2: "01" if dias_inc else "", 3: dias_inc if dias_inc else "",
                                      5: self.r.choice(["Padre con hipertensión", "Madre con diabetes", "Sin antecedentes relevantes"]),
                                      6: self.r.choice(["Exposición solar", "Ninguno", "Esfuerzo físico", "Ruido"]),
                                      7: f"Dr(a). {prof_nom} {prof_ap}"}))
        return "\r".join(lineas) + "\r"

    def oru(self, p, a):
        loinc, nombre, unidad, lo, hi = self.r.choice(LABS)
        valor = round(self.r.uniform(lo, hi), 1)
        f = lambda d: d.strftime("%Y%m%d%H%M")
        toma = a["ingreso"] + timedelta(minutes=40)
        cod, ap, nom = a["prof"]
        return "\r".join([
            f"MSH|^~\\&|LAB_SEDE{a['sede']}|SEDE{a['sede']}|HSB|CENTRAL|{f(toma)}||ORU^R01|GEN-{self.semilla}-{a['n']:04d}-LAB|P|2.5",
            seg("PID", {1: "1", 3: f"{p['doc']}^^^HIS^{p['tipo_doc']}", 5: f"{p['apellidos']}^{p['nombres']}",
                        7: p["nac"], 8: p["sexo"]}),
            seg("PV1", {1: "1", 2: a["clase"], 7: f"{cod}^{ap}^{nom}", 19: a["visita"], 44: f(a["ingreso"])}),
            seg("OBR", {1: "1", 4: f"{loinc}^{nombre}^LN"}),
            seg("OBX", {1: "1", 2: "NM", 3: f"{loinc}^{nombre}^LN", 5: valor, 6: unidad, 11: "F", 14: f(toma)})]) + "\r"

    # ── CSV legado extendido (sede 3) ────────────────────────────────────
    COLUMNAS = ["documento", "tipo_documento", "nombre", "sexo", "nacimiento", "dx_local", "fecha", "triage", "profesional",
                "entidad_salud", "causa_atencion", "municipio_residencia", "pais_residencia", "pais_nacionalidad",
                "zona_residencia", "direccion", "telefono", "ocupacion", "modalidad_entrega", "via_ingreso"]

    def fila_csv(self, p, a):
        doc = p["doc"][:2] if a["error"] == "doc" else p["doc"]
        sexo = "X" if a["error"] == "sexo" else p["sexo"]
        dx = "DOLOR RARO" if a["error"] == "dx" else a["dx"][2]
        nac = datetime.strptime(p["nac"], "%Y%m%d").strftime("%Y-%m-%d")
        valores = [doc, p["tipo_doc"], f"{p['nombres']} {p['apellidos']}", sexo, nac, dx,
                   a["ingreso"].strftime("%Y-%m-%dT%H:%M"), a["triage"], a["prof"][0], p["eps"], CAUSAS[a["dx"][0]],
                   p["muni"], "CO", "CO", p["zona"], p["dir"], p["tel"], p["ocupacion"], "01", "01"]
        return ";".join(str(v).replace(";", ",") for v in valores)


CTX = None          # contexto TLS con la CA de la plataforma
TOKEN = None        # token OAuth 2.0 del cliente herramientas_qa


def obtener_token(api, cliente, secreto):
    """OAuth 2.0 client_credentials: el bus solo acepta mensajes con un token válido."""
    req = urllib.request.Request(f"{api}/oauth/token", data=b"grant_type=client_credentials", method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Authorization": "Basic " + base64.b64encode(f"{cliente}:{secreto}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
        return json.loads(resp.read())["access_token"]


def enviar(url, ruta, cuerpo):
    cab = {"Content-Type": "text/plain; charset=utf-8"}
    if TOKEN:
        cab["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url + ruta, data=cuerpo.encode("utf-8"), method="POST", headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"estado": f"http_{e.code}"}
    except Exception as e:
        return {"estado": "error", "motivo": str(e)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8001", help="URL del HSB")
    ap.add_argument("--pacientes", type=int, default=60)
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--api", default=None, help="URL de la API para pedir el token OAuth 2.0 (si el bus lo exige)")
    ap.add_argument("--ca", default="certs/ca.pem", help="CA de la plataforma para HTTPS")
    ap.add_argument("--cliente", default="herramientas_qa")
    ap.add_argument("--secreto", default=os.getenv("OAUTH_SECRETO_QA", "qa_secreto_2026"))
    args = ap.parse_args()
    global CTX, TOKEN
    CTX = ssl.create_default_context(cafile=args.ca) if os.path.exists(args.ca) else None
    if args.api:
        TOKEN = obtener_token(args.api, args.cliente, args.secreto)

    g = Generador(args.semilla)
    hl7, filas_csv = [], []
    for i in range(args.pacientes):
        p = g.persona(i)
        sedes = [p["sede"]]
        if g.r.random() < 0.25:
            sedes.append(g.r.choice([s for s in (1, 2, 3) if s != p["sede"]]))
        if g.r.random() < 0.10:
            sedes = [1, 2, 3]
        for sede in sedes:
            for _ in range(g.r.choice([1, 1, 1, 2])):
                a = g.atencion(p, sede)
                if sede == 3:
                    filas_csv.append(g.fila_csv(p, a))
                else:
                    hl7.append(g.hl7(p, a))
                    if a["lab"] and not a["error"]:
                        hl7.append(g.oru(p, a))
    reenvios = g.r.sample(hl7, k=max(1, len(hl7) // 20))

    print(f"Enviando {len(hl7)} mensajes HL7 (+{len(reenvios)} reenvíos) y {len(filas_csv)} filas CSV a {args.url} ...")
    cuenta = Counter()
    with ThreadPoolExecutor(max_workers=args.hilos) as pool:
        for r in pool.map(lambda m: enviar(args.url, "/hsb/hl7", m), hl7):
            cuenta[r.get("estado", "?")] += 1
    for m in reenvios:
        cuenta[enviar(args.url, "/hsb/hl7", m).get("estado", "?")] += 1
    encabezado = ";".join(Generador.COLUMNAS)
    for i in range(0, len(filas_csv), 25):          # lotes de 25 filas, como un archivo diario
        r = enviar(args.url, "/hsb/csv?sede=3", encabezado + "\n" + "\n".join(filas_csv[i:i + 25]))
        for clave in ("entregados", "rechazados", "duplicados", "reintentando", "muertos"):
            cuenta[clave.rstrip("s").replace("ado", "ado")] += r.get(f"total_{clave}", 0)
    total = sum(cuenta.values())
    print(f"Listo: {total} mensajes procesados")
    for estado, n in sorted(cuenta.items(), key=lambda x: -x[1]):
        print(f"  {estado:<14} {n}")


if __name__ == "__main__":
    main()
