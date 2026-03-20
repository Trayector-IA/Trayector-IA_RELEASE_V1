import os
import bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class Database:
    def __init__(self):
        uri = os.environ.get("MONGO_URI")
        if not uri:
            print("[Error] MONGO_URI no definida en .env")
            self.client = None
            return
        
        try:
            self.client = MongoClient(uri)
            self.db = self.client["agente_vocacional"]
            self.usuarios = self.db["usuarios_permitidos"]
            self.resultados = self.db["resultados"]
        except Exception as e:
            print(f"[Error] Conexión a MongoDB fallida: {e}")
            self.client = None

    def verificar_acceso(self, usuario_id, password_plano=""):
        try:
            usuario = self.usuarios.find_one({"usuario_id": usuario_id})
            
            if not usuario:
                return False, "ID no registrado en el sistema.", None
            
            rol = usuario.get("rol", "estudiante")
            
            if rol == "admin":
                hash_guardado = usuario.get("password", "")
                
                if not password_plano:
                    return False, "Contraseña requerida para acceder al panel.", None
                
                if not hash_guardado:
                    return False, "Error de credenciales en el servidor.", None
                
                try:
                    pwd_bytes = password_plano.encode('utf-8')
                    if isinstance(hash_guardado, bytes):
                        hash_bytes = hash_guardado
                    else:
                        hash_bytes = hash_guardado.strip().encode('utf-8')
                    
                    if bcrypt.checkpw(pwd_bytes, hash_bytes):
                        return True, "Acceso concedido.", rol
                    else:
                        return False, "Contraseña incorrecta.", None
                except ValueError:
                    return False, "Error crítico: El hash en MongoDB es inválido.", None
            
            return True, "Acceso concedido.", rol

        except Exception as e:
            print(f"[DEBUG] Error real en verificar_acceso: {e}")
            return False, "Error interno del servidor.", None

    # --- FUNCIÓN NUEVA AGREGADA AQUÍ ---
    def ya_realizo_prueba(self, usuario_id):
        try:
            resultado = self.resultados.find_one({"usuario_id": usuario_id})
            return resultado is not None
        except Exception as e:
            print(f"[DEBUG] Error al buscar resultado previo: {e}")
            return False
    # -----------------------------------

    def guardar_resultado(self, usuario_id, resultado_dict):
        if not self.client: 
            return False
        
        documento = {
            "usuario_id": usuario_id,
            "resultado": resultado_dict
        }
        self.resultados.insert_one(documento)
        return True
    
    def obtener_todos_usuarios(self):
        try:
            return list(self.usuarios.find({}, {"_id": 0, "password": 0}))
        except Exception as e:
            print(f"Error al obtener usuarios: {e}")
            return []

    def obtener_todos_resultados(self):
        try:
            return list(self.resultados.find({}, {"_id": 0}))
        except Exception as e:
            print(f"Error al obtener resultados: {e}")
            return []

db_client = Database()