"""
Script de configuración: agente_vocacional → agente_vocacional_cloud

Ejecutar una sola vez:
    python setup_cloud_db.py

Crea:
  - Duplicado completo de agente_vocacional en agente_vocacional_cloud
  - Colección 'preparatorias' con cpo, isecf, bc
  - 5 admins locales por preparatoria (cpo_001 … cpo_005, etc.)
  - 3 admins globales (admin_global_001 … admin_global_003)
  - Colección 'sesiones' para controlar el límite de 2 sesiones activas
"""

import os
import bcrypt
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# ── Configuración ──────────────────────────────────────────────────────────────

PREPARATORIAS = [
    {"preparatoria_id": "cpo",   "nombre": "CPO"},
    {"preparatoria_id": "isecf", "nombre": "ISECF"},
    {"preparatoria_id": "bc",    "nombre": "BC"},
]

ADMINS_POR_PREPA = 5
ADMINS_GLOBALES  = 3
MAX_SESIONES     = 2

# Grupos CPO serie 400: 5 grupos de 60 alumnos cada uno (401-460)
CPO_GRUPOS_400 = {
    "a": range(401, 461),  # cpo_a_401 … cpo_a_460
    "b": range(401, 461),  # cpo_b_401 … cpo_b_460
    "c": range(401, 461),  # cpo_c_401 … cpo_c_460
    "d": range(401, 461),  # cpo_d_401 … cpo_d_460
    "e": range(401, 461),  # cpo_e_401 … cpo_e_460
}

# Grupos CPO serie 600: 5 grupos de 60 alumnos cada uno (601-660)
CPO_GRUPOS_600 = {
    "a": range(601, 661),  # cpo_a_601 … cpo_a_660
    "b": range(601, 661),  # cpo_b_601 … cpo_b_660
    "c": range(601, 661),  # cpo_c_601 … cpo_c_660
    "d": range(601, 661),  # cpo_d_601 … cpo_d_660
    "e": range(601, 661),  # cpo_e_601 … cpo_e_660
}

ORIGEN  = "agente_vocacional"
DESTINO = "agente_vocacional_cloud"


def hashear(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main():
    uri = os.environ.get("MONGO_URI")
    if not uri:
        print("[ERROR] MONGO_URI no definida en .env")
        return

    client = MongoClient(uri)
    origen  = client[ORIGEN]
    destino = client[DESTINO]

    # ── 1. Duplicar todas las colecciones ─────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Duplicando '{ORIGEN}' -> '{DESTINO}'")
    print(f"{'='*60}")

    for col_name in origen.list_collection_names():
        docs = list(origen[col_name].find({}))
        destino[col_name].drop()
        if docs:
            destino[col_name].insert_many(docs)
            print(f"  ✓ {col_name:<25} {len(docs)} documentos")
        else:
            print(f"  - {col_name:<25} vacía (omitida)")

    # ── 2. Colección preparatorias ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  Creando colección 'preparatorias'")
    print(f"{'='*60}")

    destino["preparatorias"].drop()
    for p in PREPARATORIAS:
        destino["preparatorias"].insert_one({
            "preparatoria_id": p["preparatoria_id"],
            "nombre":          p["nombre"],
            "activa":          True,
            "created_at":      datetime.now(timezone.utc),
        })
        print(f"  ✓ {p['nombre']} ({p['preparatoria_id']})")

    # ── 3. Colección sesiones (control de acceso concurrente) ─────────────────
    destino["sesiones"].drop()
    destino["sesiones"].create_index([("session_id",  ASCENDING)], unique=True)
    destino["sesiones"].create_index([("usuario_id",  ASCENDING)])
    destino["sesiones"].create_index([("activa",      ASCENDING)])
    print("\n  ✓ Colección 'sesiones' inicializada con índices")

    # ── 4. Admins por preparatoria ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  Creando administradores locales")
    print(f"{'='*60}")

    usuarios_col = destino["usuarios_permitidos"]
    credenciales = []

    for prepa in PREPARATORIAS:
        pid      = prepa["preparatoria_id"]
        password = f"{pid.upper()}_Admin2024!"

        for i in range(1, ADMINS_POR_PREPA + 1):
            uid = f"{pid}_{i:03d}"
            usuarios_col.delete_one({"usuario_id": uid})
            usuarios_col.insert_one({
                "usuario_id":   uid,
                "rol":          "admin",
                "status":       "activo",
                "preparatoria": pid,
                "scope":        "local",
                "max_sesiones": MAX_SESIONES,
                "password":     hashear(password),
                "created_at":   datetime.now(timezone.utc),
            })
            credenciales.append({
                "usuario":      uid,
                "password":     password,
                "preparatoria": pid,
                "scope":        "local",
            })

        print(f"  ✓ {ADMINS_POR_PREPA} admins creados  →  {pid}_001 … {pid}_{ADMINS_POR_PREPA:03d}")

    # ── 5. Admins globales ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  Creando administradores globales")
    print(f"{'='*60}")

    password_global = "GlobalAdmin2024!"
    for i in range(1, ADMINS_GLOBALES + 1):
        uid = f"admin_global_{i:03d}"
        usuarios_col.delete_one({"usuario_id": uid})
        usuarios_col.insert_one({
            "usuario_id":   uid,
            "rol":          "admin",
            "status":       "activo",
            "scope":        "global",
            "max_sesiones": MAX_SESIONES,
            "password":     hashear(password_global),
            "created_at":   datetime.now(timezone.utc),
        })
        credenciales.append({
            "usuario":      uid,
            "password":     password_global,
            "preparatoria": "TODAS",
            "scope":        "global",
        })
        print(f"  ✓ {uid}")

    # ── 6. Índices en usuarios_permitidos ─────────────────────────────────────
    usuarios_col.create_index([("usuario_id",   ASCENDING)], background=True)
    usuarios_col.create_index([("preparatoria", ASCENDING)], background=True)
    usuarios_col.create_index([("scope",        ASCENDING)], background=True)
    print("\n  ✓ Índices creados en 'usuarios_permitidos'")

    # ── 7. Resumen de credenciales ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  CREDENCIALES GENERADAS")
    print(f"{'='*60}")
    print(f"  {'Usuario':<22} {'Contraseña':<22} {'Prepa':<8} Scope")
    print(f"  {'-'*60}")
    for c in credenciales:
        print(f"  {c['usuario']:<22} {c['password']:<22} {c['preparatoria']:<8} {c['scope']}")

    total_admins = len(credenciales)
    print(f"\n  Total admins creados: {total_admins}")

    # ── 8. Estudiantes CPO serie 400 (cpo_a_401 … cpo_e_460) ─────────────────
    print(f"\n{'='*60}")
    print("  Registrando estudiantes CPO (series 400, grupos A-E)")
    print(f"{'='*60}")

    total_estudiantes = 0
    for grupo, numeros in CPO_GRUPOS_400.items():
        for num in numeros:
            uid = f"cpo_{grupo}_{num}"
            usuarios_col.delete_one({"usuario_id": uid})
            usuarios_col.insert_one({
                "usuario_id":      uid,
                "rol":             "estudiante",
                "preparatoria":    "cpo",
                "grupo":           grupo.upper(),
                "test_completado": False,
            })
            total_estudiantes += 1
        rango = list(numeros)
        print(f"  ✓ Grupo {grupo.upper()}: cpo_{grupo}_{rango[0]} … cpo_{grupo}_{rango[-1]}  ({len(rango)} alumnos)")

    # ── 9. Estudiantes CPO serie 600 (cpo_a_601 … cpo_e_660) ─────────────────
    print(f"\n{'='*60}")
    print("  Registrando estudiantes CPO (series 600, grupos A-E)")
    print(f"{'='*60}")

    for grupo, numeros in CPO_GRUPOS_600.items():
        for num in numeros:
            uid = f"cpo_{grupo}_{num}"
            usuarios_col.delete_one({"usuario_id": uid})
            usuarios_col.insert_one({
                "usuario_id":      uid,
                "rol":             "estudiante",
                "preparatoria":    "cpo",
                "grupo":           grupo.upper(),
                "test_completado": False,
            })
            total_estudiantes += 1
        rango = list(numeros)
        print(f"  ✓ Grupo {grupo.upper()}: cpo_{grupo}_{rango[0]} … cpo_{grupo}_{rango[-1]}  ({len(rango)} alumnos)")

    print(f"\n  Total estudiantes CPO registrados: {total_estudiantes}")
    print(f"  Base de datos '{DESTINO}' configurada exitosamente.\n")

    client.close()


if __name__ == "__main__":
    main()
