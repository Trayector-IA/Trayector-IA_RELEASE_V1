"""
api/orientador.py — Trayector-IA
Facade que integra LLM (Groq) + NLP (KNN) con el CSV institucional completo.
"""

import os
import sys
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from api.llm_groq_logic import (
        obtener_saludo_inicial,
        evaluar_respuesta_usuario,
        generar_explicacion_afinidad,
        PREGUNTAS,
        BLOQUES,
    )
    LLM_AVAILABLE = True
except Exception as e:
    print(f"[ERROR FATAL LLM] No se pudo importar: {e}")
    LLM_AVAILABLE = False

try:
    from api.nlp_knn_logic import (
        entrenar_modelo_knn,
        analizar_afinidad,
        obtener_lista_carreras,
        obtener_info_carrera,
    )
    NLP_AVAILABLE = True
except Exception as e:
    print(f"[ERROR FATAL NLP] No se pudo importar: {e}")
    NLP_AVAILABLE = False

PREGUNTAS_FALLBACK = [
    "¿Qué actividades o temas disfrutas más cuando estudias o realizas proyectos en la preparatoria? Describe algunos ejemplos concretos.",
    "Cuando trabajas en equipo para resolver un problema o realizar un proyecto escolar, ¿qué papel sueles asumir y qué es lo que más te gusta aportar?",
    "Menciona algún problema de tu entorno —en tu escuela, comunidad o ciudad— que te gustaría ayudar a resolver y explica por qué.",
    "¿Qué habilidades o capacidades consideras que mejor te describen actualmente?",
    "Si tuvieras que elegir tres áreas o temas que te generan mayor curiosidad o interés, ¿cuáles serían y por qué?",
    "Imagina tu vida profesional dentro de 10 años. ¿Qué tipo de trabajo te gustaría estar realizando?",
    "¿Qué tipo de problemas te gustaría ayudar a resolver en la sociedad o en las organizaciones?",
    "¿En qué tipo de organizaciones te imaginas trabajando en el futuro? (empresas, gobierno, hospitales, escuelas, laboratorios, emprendimientos, etc.)",
    "Si pudieras desarrollar o mejorar algo en tu comunidad o en el mundo, ¿qué sería y cómo te gustaría hacerlo?",
    "¿Qué tipo de impacto te gustaría generar con tu trabajo o profesión?",
]

BLOQUES_FALLBACK = {
    0: "📚 Bloque 1 — Perfil de ingreso (tu situación actual)",
    5: "🔭 Bloque 2 — Proyección profesional (tu futuro)",
}

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "perfil_academico.csv")


class OrientadorAPI:
    def __init__(self):
        self.llm_ok    = LLM_AVAILABLE and bool(os.environ.get("GROQ_API_KEY"))
        self.nlp_ok    = False
        self.preguntas = PREGUNTAS if LLM_AVAILABLE else PREGUNTAS_FALLBACK
        self.bloques   = BLOQUES   if LLM_AVAILABLE else BLOQUES_FALLBACK
        self.vectorizador = None
        self.modelo_knn   = None
        self.clases       = None
        self._csv_path    = CSV_PATH
        self._cargar_modelo()

    def _cargar_modelo(self):
        if NLP_AVAILABLE and os.path.exists(self._csv_path):
            try:
                self.vectorizador, self.modelo_knn, self.clases = entrenar_modelo_knn(self._csv_path)
                self.nlp_ok = True
            except Exception as e:
                print(f"[OrientadorAPI] Error cargando modelo: {e}")

    def total_preguntas(self): return len(self.preguntas)
    def obtener_pregunta(self, i): return self.preguntas[i] if 0 <= i < len(self.preguntas) else ""
    def es_inicio_bloque(self, i): return i in self.bloques
    def nombre_bloque(self, i): return self.bloques.get(i, "")

    def lista_carreras(self):
        if NLP_AVAILABLE and os.path.exists(self._csv_path):
            try: return obtener_lista_carreras(self._csv_path)
            except: pass
        return []

    def info_carrera(self, nombre):
        if NLP_AVAILABLE and os.path.exists(self._csv_path):
            try: return obtener_info_carrera(self._csv_path, nombre)
            except: pass
        return {}

    def obtener_saludo_inicial(self):
        if self.llm_ok:
            try: return obtener_saludo_inicial()
            except Exception as e: print(f"[LLM] saludo fallback: {e}")
        return (
            "¡Hola! Soy **Trayector-IA**, tu orientador vocacional de la Universidad Veracruzana 🎓\n\n"
            "Realizaré **10 preguntas** en dos bloques:\n"
            "**Bloque 1 (1–5):** Tus gustos e intereses actuales.\n"
            "**Bloque 2 (6–10):** Tu visión profesional futura.\n\n"
            f"Comenzamos:\n\n**{self.preguntas[0]}**"
        )

    def evaluar_respuesta(self, respuesta, indice):
        if self.llm_ok:
            try: return evaluar_respuesta_usuario(respuesta, indice)
            except Exception as e: print(f"[LLM] evaluar fallback: {e}")
        siguiente = self.preguntas[indice + 1] if indice + 1 < len(self.preguntas) else None
        if siguiente:
            aviso = ""
            if (indice + 1) in self.bloques:
                aviso = f"\n\n---\n**{self.bloques[indice+1]}**\nAhora exploraremos tu visión profesional a futuro.\n\n"
            return {"es_valida": True, "mensaje": f"¡Gracias!{aviso}\n\n**{siguiente}**"}
        return {"es_valida": True, "mensaje": "¡Completaste las 10 preguntas! Procesando tu perfil con IA..."}

    def obtener_resultado(self, respuestas, skip_llm=False):
            # 1. Verificación inicial: ¿El modelo cargó correctamente al iniciar el servidor?
            if not self.nlp_ok:
                return self._resultado_error("modelo")

            try:
                # 2. Ejecución del motor KNN
                resultados = analizar_afinidad(respuestas, self.vectorizador, self.modelo_knn, self.clases)
                
                # 3. Verificación de contenido: ¿Hubo coincidencias con el perfil?
                if not resultados:
                    return self._resultado_error("vacio")

                # Si llegamos aquí, el algoritmo encontró coincidencias
                mejor = resultados[0]
                carrera, pct = mejor["Carrera"], mejor["Similitud"]
                info = self.info_carrera(carrera)

                # 4. Generación de la explicación (IA vs Fallback)
                if self.llm_ok and not skip_llm: # Añadimos la condición 'not skip_llm'
                        try: 
                            explicacion = generar_explicacion_afinidad(respuestas, carrera, pct)
                        except Exception as e:
                            print(f"[LLM] Error en explicación dinámica: {e}")
                            explicacion = self._explicacion_fallback(carrera, pct)
                else:
                        # Si skip_llm es True, usamos el fallback rápido sin gastar tokens
                    explicacion = self._explicacion_fallback(carrera, pct)

                # 5. Retorno de éxito
                return {
                    "error": False,
                    "carrera_recomendada": carrera,
                    "es_uv": bool(info),
                    "porcentaje": pct,
                    "explicacion": explicacion,
                    "nivel": self._nivel_afinidad(pct),
                    "total_respuestas": len(respuestas),
                    "facultad":    info.get("Facultad / entidad académica (región Orizaba-Córdoba)", "No disponible"),
                    "municipio":   info.get("Municipio(s) donde se ofrece en la región", "No disponible"),
                    "modalidad":   info.get("Modalidad(es) en la región", "No disponible"),
                    "perfil_ingreso": info.get("Perfil de Ingreso (Expandido)", "Consulta el portal oficial."),
                    "perfil_egreso":  info.get("Perfil de Egreso (Expandido)", "Consulta el portal oficial."),
                    "url_oficial": info.get("consulta_web", "#"),
                    "otras_opciones": [
                        {
                            "Carrera": op["Carrera"],
                            "es_uv": bool(self.info_carrera(op["Carrera"])),
                            "url_oficial": self.info_carrera(op["Carrera"]).get("consulta_web", "#")
                        } for op in resultados[1:6]
                    ]
                }

            except Exception as e:
                # 6. Captura de errores críticos durante el análisis
                print(f"[CRÍTICO] Fallo en obtener_resultado: {e}")
                return self._resultado_error("nlp")
        
    @staticmethod
    def _nivel_afinidad(p): return "alto" if p >= 80 else ("medio" if p >= 60 else "bajo")

    @staticmethod
    def _explicacion_fallback(carrera, pct):
        return (f"El análisis semántico mostró una afinidad del {pct}% con {carrera}. "
                "Las habilidades e intereses que describiste se alinean con el perfil académico de esta carrera en Campus Ixtac.")

    def _resultado_error(self, tipo_error="desconocido"):
            """Devuelve un objeto de resultado que la interfaz reconoce como un fallo técnico."""
            mensajes = {
                "modelo": "No pudimos cargar el catálogo de carreras. Por favor, contacta al administrador.",
                "nlp": "Hubo un problema al procesar tus respuestas. ¿Podrías intentarlo de nuevo?",
                "vacio": "No logramos encontrar una coincidencia clara con tu perfil. Intenta ser más descriptivo en tus respuestas.",
                "desconocido": "Algo salió mal en nuestro servidor. Estamos trabajando para solucionarlo."
            }
            
            return {
                "error": True,
                "tipo": tipo_error,
                "carrera_recomendada": "Error de Procesamiento",
                "explicacion": mensajes.get(tipo_error, mensajes["desconocido"]),
                "porcentaje": 0,
                "nivel": "n/a",
                "otras_opciones": []
            }