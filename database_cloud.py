import os
import uuid
import bcrypt
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


class DatabaseCloud:
    """
    Capa de datos para agente_vocacional_cloud.

    Diferencias respecto a Database (agente_vocacional):
      - Control de sesiones activas por usuario (max_sesiones).
      - Filtrado de resultados/usuarios por preparatoria o scope global.
      - verificar_acceso devuelve 4 valores: (ok, mensaje, rol, meta)
        donde meta = {session_id, scope, preparatoria} o {} para estudiantes.
    """

    DB_NAME = "agente_vocacional_cloud"

    def __init__(self):
        uri = os.environ.get("MONGO_URI")
        if not uri:
            print("[Error] MONGO_URI no definida en .env")
            self.client = None
            return
        try:
            self.client       = MongoClient(uri)
            self.db           = self.client[self.DB_NAME]
            self.usuarios     = self.db["usuarios_permitidos"]
            self.resultados   = self.db["resultados"]
            self.preparatorias_col = self.db["preparatorias"]
            self.sesiones_col = self.db["sesiones"]
        except Exception as e:
            print(f"[Error] Conexión a MongoDB cloud fallida: {e}")
            self.client = None

    # ── Autenticación y sesiones ───────────────────────────────────────────────

    def verificar_acceso(self, usuario_id: str, password_plano: str = ""):
        """
        Retorna (ok: bool, mensaje: str, rol: str | None, meta: dict | None).

        meta para admins/maestros:
          {session_id, scope, preparatoria}   # preparatoria=None si scope='global'
        meta para estudiantes: {}
        """
        try:
            usuario = self.usuarios.find_one({"usuario_id": usuario_id})

            if not usuario:
                return False, "ID no registrado en el sistema.", None, None

            rol = usuario.get("rol", "estudiante")

            if rol in ["admin", "maestro"]:
                if not password_plano:
                    return False, "Contraseña requerida para acceder al panel.", None, None

                hash_guardado = usuario.get("password", "")
                if not hash_guardado:
                    return False, "Error de credenciales en el servidor.", None, None

                try:
                    pwd_bytes  = password_plano.encode("utf-8")
                    hash_bytes = (
                        hash_guardado
                        if isinstance(hash_guardado, bytes)
                        else hash_guardado.strip().encode("utf-8")
                    )
                    if not bcrypt.checkpw(pwd_bytes, hash_bytes):
                        return False, "Contraseña incorrecta.", None, None
                except ValueError:
                    return False, "Error crítico: hash inválido en MongoDB.", None, None

                # Registrar nueva sesión
                session_id = str(uuid.uuid4())
                self.sesiones_col.insert_one({
                    "session_id": session_id,
                    "usuario_id": usuario_id,
                    "inicio":     datetime.now(timezone.utc),
                    "activa":     True,
                })

                meta = {
                    "session_id":   session_id,
                    "scope":        usuario.get("scope", "local"),
                    "preparatoria": usuario.get("preparatoria"),
                }
                return True, "Acceso concedido.", rol, meta

            # Estudiante: sin control de sesiones
            return True, "Acceso concedido.", rol, {}

        except Exception as e:
            print(f"[cloud] Error en verificar_acceso: {e}")
            return False, "Error interno del servidor.", None, None

    def cerrar_sesion(self, session_id: str) -> bool:
        """Marca la sesión como inactiva (logout)."""
        if not self.client or not session_id:
            return False
        try:
            self.sesiones_col.update_one(
                {"session_id": session_id},
                {"$set": {"activa": False, "fin": datetime.now(timezone.utc)}},
            )
            return True
        except Exception as e:
            print(f"[cloud] Error cerrando sesión: {e}")
            return False

    def sesiones_activas_de(self, usuario_id: str) -> int:
        """Cuenta las sesiones activas de un usuario."""
        try:
            return self.sesiones_col.count_documents(
                {"usuario_id": usuario_id, "activa": True}
            )
        except Exception:
            return 0

    # ── Consultas filtradas por preparatoria ──────────────────────────────────

    def obtener_resultados_filtrados(self, scope: str = "local", preparatoria: str | None = None):
        """Devuelve resultados según el scope del admin."""
        if not self.client:
            return []
        try:
            if scope == "global":
                return list(self.resultados.find({}, {"_id": 0}))

            ids_prepa = [
                u["usuario_id"]
                for u in self.usuarios.find(
                    {"preparatoria": preparatoria}, {"usuario_id": 1, "_id": 0}
                )
            ]
            return list(self.resultados.find(
                {"usuario_id": {"$in": ids_prepa}}, {"_id": 0}
            ))
        except Exception as e:
            print(f"[cloud] Error en obtener_resultados_filtrados: {e}")
            return []

    def obtener_usuarios_filtrados(self, scope: str = "local", preparatoria: str | None = None):
        """Devuelve usuarios según el scope del admin (sin passwords)."""
        if not self.client:
            return []
        try:
            if scope == "global":
                return list(self.usuarios.find({}, {"_id": 0, "password": 0}))
            return list(self.usuarios.find(
                {"preparatoria": preparatoria}, {"_id": 0, "password": 0}
            ))
        except Exception as e:
            print(f"[cloud] Error en obtener_usuarios_filtrados: {e}")
            return []

    def obtener_preparatorias(self) -> list:
        """Lista todas las preparatorias registradas."""
        if not self.client:
            return []
        try:
            return list(self.preparatorias_col.find({}, {"_id": 0}))
        except Exception as e:
            print(f"[cloud] Error en obtener_preparatorias: {e}")
            return []

    # ── Gestión de estudiantes por preparatoria ───────────────────────────────

    def registrar_estudiante(self, preparatoria: str, numero: int) -> dict | None:
        """
        Crea un estudiante asociado a una preparatoria.
        ID generado: <preparatoria>_est_<numero:03d>  (ej. cpo_est_001)
        Retorna el documento creado o None si ya existe.
        """
        if not self.client:
            return None
        uid = f"{preparatoria}_est_{numero:03d}"
        if self.usuarios.find_one({"usuario_id": uid}):
            return None
        doc = {
            "usuario_id":   uid,
            "rol":          "estudiante",
            "preparatoria": preparatoria,
            "test_completado": False,
        }
        self.usuarios.insert_one(doc)
        doc.pop("_id", None)
        return doc

    def registrar_estudiantes_lote(self, preparatoria: str, cantidad: int, inicio: int = 1) -> list:
        """
        Registra 'cantidad' estudiantes a partir del número 'inicio'.
        Retorna la lista de documentos insertados.
        """
        creados = []
        for n in range(inicio, inicio + cantidad):
            doc = self.registrar_estudiante(preparatoria, n)
            if doc:
                creados.append(doc)
        return creados

    def obtener_siguiente_numero_estudiante(self, preparatoria: str) -> int:
        """Devuelve el siguiente número disponible para nuevos estudiantes de una preparatoria."""
        prefijo = f"{preparatoria}_est_"
        existentes = self.usuarios.find(
            {"usuario_id": {"$regex": f"^{prefijo}"}},
            {"usuario_id": 1, "_id": 0}
        )
        numeros = []
        for u in existentes:
            try:
                n = int(u["usuario_id"].replace(prefijo, ""))
                numeros.append(n)
            except ValueError:
                pass
        return (max(numeros) + 1) if numeros else 1

    # ── Métodos equivalentes a Database original ──────────────────────────────

    def ya_realizo_prueba(self, usuario_id: str) -> bool:
        try:
            return self.resultados.find_one({"usuario_id": usuario_id}) is not None
        except Exception:
            return False

    def guardar_progreso(self, usuario_id: str, respuestas: list, indice: int) -> bool:
        if not self.client:
            return False
        try:
            self.db["progreso_en_curso"].update_one(
                {"usuario_id": usuario_id},
                {"$set": {
                    "usuario_id": usuario_id,
                    "respuestas": respuestas,
                    "indice":     indice,
                    "updated_at": datetime.now(timezone.utc),
                }},
                upsert=True,
            )
            return True
        except Exception as e:
            print(f"[cloud][progreso] Error guardando: {e}")
            return False

    def obtener_progreso(self, usuario_id: str) -> dict | None:
        if not self.client:
            return None
        try:
            return self.db["progreso_en_curso"].find_one(
                {"usuario_id": usuario_id}, {"_id": 0}
            )
        except Exception as e:
            print(f"[cloud][progreso] Error leyendo: {e}")
            return None

    def limpiar_progreso(self, usuario_id: str) -> bool:
        if not self.client:
            return False
        try:
            self.db["progreso_en_curso"].delete_one({"usuario_id": usuario_id})
            return True
        except Exception as e:
            print(f"[cloud][progreso] Error limpiando: {e}")
            return False

    def guardar_resultado(self, usuario_id: str, resultado_dict: dict, respuestas: list = None) -> bool:
        if not self.client:
            return False
        try:
            doc = {"usuario_id": usuario_id, "resultado": resultado_dict}
            if respuestas is not None:
                doc["respuestas"] = respuestas
            self.resultados.insert_one(doc)
            return True
        except Exception as e:
            print(f"[cloud] Error guardando resultado: {e}")
            return False

    def obtener_resultado_por_id(self, usuario_id: str) -> dict | None:
        if not self.client:
            return None
        try:
            return self.resultados.find_one({"usuario_id": usuario_id}, {"_id": 0})
        except Exception as e:
            print(f"[cloud] Error buscando resultado {usuario_id}: {e}")
            return None

    def eliminar_resultado(self, usuario_id: str, scope: str = "local", preparatoria: str | None = None) -> bool:
        """Elimina el resultado de un alumno respetando el scope del admin."""
        if not self.client:
            return False
        try:
            if scope == "local":
                ids_prepa = [
                    u["usuario_id"]
                    for u in self.usuarios.find({"preparatoria": preparatoria}, {"usuario_id": 1, "_id": 0})
                ]
                if usuario_id not in ids_prepa:
                    return False
            res = self.resultados.delete_one({"usuario_id": usuario_id})
            return res.deleted_count > 0
        except Exception as e:
            print(f"[cloud] Error eliminando resultado {usuario_id}: {e}")
            return False

    def obtener_todos_resultados(self) -> list:
        """Devuelve todos los resultados sin filtro (equivalente global)."""
        return self.obtener_resultados_filtrados("global")

    def obtener_todos_usuarios(self) -> list:
        """Devuelve todos los usuarios sin filtro (equivalente global)."""
        return self.obtener_usuarios_filtrados("global")

    def eliminar_usuario(self, usuario_id: str, scope: str = "local", preparatoria: str | None = None) -> bool:
        """Elimina un usuario respetando el scope del admin. No permite eliminar otros admins."""
        if not self.client:
            return False
        try:
            filtro = {"usuario_id": usuario_id, "rol": {"$ne": "admin"}}
            if scope == "local":
                filtro["preparatoria"] = preparatoria
            res = self.usuarios.delete_one(filtro)
            return res.deleted_count > 0
        except Exception as e:
            print(f"[cloud] Error eliminando usuario {usuario_id}: {e}")
            return False


db_cloud = DatabaseCloud()
