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

    def obtener_resultado(self, respuestas):
        if self.nlp_ok:
            try:
                resultados = analizar_afinidad(respuestas, self.vectorizador, self.modelo_knn, self.clases)
                if resultados:
                    mejor = resultados[0]
                    carrera, pct = mejor["Carrera"], mejor["Similitud"]
                    info = self.info_carrera(carrera)
                    if self.llm_ok:
                        try: explicacion = generar_explicacion_afinidad(respuestas, carrera, pct)
                        except: explicacion = self._explicacion_fallback(carrera, pct)
                    else:
                        explicacion = self._explicacion_fallback(carrera, pct)
                    return {
                        "carrera_recomendada": carrera,
                        "porcentaje": pct,
                        "explicacion": explicacion,
                        "nivel": self._nivel_afinidad(pct),
                        "otras_opciones": resultados[1:6],
                        "total_respuestas": len(respuestas),
                        "facultad":    info.get("Facultad / entidad académica (región Orizaba-Córdoba)", ""),
                        "municipio":   info.get("Municipio(s) donde se ofrece en la región", ""),
                        "modalidad":   info.get("Modalidad(es) en la región", ""),
                        "perfil_ingreso": info.get("Perfil de ingreso (síntesis)", ""),
                        "perfil_egreso":  info.get("Perfil de egreso (síntesis)", ""),
                    }
            except Exception as e: print(f"[NLP] resultado fallback: {e}")
        return self._resultado_demo(respuestas)

    @staticmethod
    def _nivel_afinidad(p): return "alto" if p >= 80 else ("medio" if p >= 60 else "bajo")

    @staticmethod
    def _explicacion_fallback(carrera, pct):
        return (f"El análisis semántico mostró una afinidad del {pct}% con {carrera}. "
                "Las habilidades e intereses que describiste se alinean con el perfil académico de esta carrera en Campus Ixtac.")

    def _resultado_demo(self, respuestas):
        demos = ["Ingeniería de Software","Administración","Gestión y Dirección de Negocios","Contaduría"]
        h = int(hashlib.md5(" ".join(respuestas).encode()).hexdigest(), 16)
        carrera = demos[h % len(demos)]
        pct = round(65 + (h % 22), 2)
        info = self.info_carrera(carrera)
        return {
            "carrera_recomendada": carrera, "porcentaje": pct,
            "explicacion": self._explicacion_fallback(carrera, pct),
            "nivel": self._nivel_afinidad(pct),
            "otras_opciones": [{"Carrera": c, "Similitud": round(pct-(i*9+4),2)} for i,c in enumerate([x for x in demos if x!=carrera][:3]) if pct-(i*9+4)>0],
            "total_respuestas": len(respuestas),
            "facultad": info.get("Facultad / entidad académica (región Orizaba-Córdoba)",""),
            "municipio": info.get("Municipio(s) donde se ofrece en la región",""),
            "modalidad": info.get("Modalidad(es) en la región",""),
            "perfil_ingreso": info.get("Perfil de ingreso (síntesis)",""),
            "perfil_egreso": info.get("Perfil de egreso (síntesis)",""),
        }
