"""
llm_groq_logic.py — Trayector-IA
LLM logic via Groq API. Compatible con Flask (sin dependencia de Streamlit).
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv, find_dotenv

# ── Inicializar cliente Groq ──────────────────────────────────────────────────
load_dotenv(find_dotenv())

api_key = os.environ.get("GROQ_API_KEY")

print("Llave de Groq detectada:", "SÍ" if api_key else "NO") 

cliente_groq = Groq(api_key=api_key)

# ── 10 Preguntas vocacionales ─────────────────────────────────────────────────
PREGUNTAS = [
    # ── PERFIL DE INGRESO ──────────────────────────────────────────────────────
    "¿Qué actividades o temas disfrutas más cuando estudias o realizas proyectos "
    "en la preparatoria? Describe algunos ejemplos concretos.",

    "Cuando trabajas en equipo para resolver un problema o realizar un proyecto "
    "escolar, ¿qué papel sueles asumir y qué es lo que más te gusta aportar?",

    "Menciona algún problema de tu entorno —en tu escuela, comunidad o ciudad— "
    "que te gustaría ayudar a resolver y explica por qué.",

    "¿Qué habilidades o capacidades consideras que mejor te describen actualmente?",

    "Si tuvieras que elegir tres áreas o temas que te generan mayor curiosidad "
    "o interés, ¿cuáles serían y por qué?",

    # ── PERFIL DE EGRESO ───────────────────────────────────────────────────────
    "Imagina tu vida profesional dentro de 10 años. ¿Qué tipo de trabajo te "
    "gustaría estar realizando?",

    "¿Qué tipo de problemas te gustaría ayudar a resolver en la sociedad o en "
    "las organizaciones?",

    "¿En qué tipo de organizaciones te imaginas trabajando en el futuro? "
    "(empresas, gobierno, hospitales, escuelas, laboratorios, emprendimientos, etc.)",

    "Si pudieras desarrollar o mejorar algo en tu comunidad o en el mundo, "
    "¿qué sería y cómo te gustaría hacerlo?",

    "¿Qué tipo de impacto te gustaría generar con tu trabajo o profesión?",
]

BLOQUES = {
    0: "Bloque 1 — Perfil de ingreso (tu situación actual)",
    5: "Bloque 2 — Proyección profesional (tu futuro)",
}

# ── Saludo inicial ────────────────────────────────────────────────────────────

def obtener_saludo_inicial() -> str:
    """Genera el saludo dinámico con Groq y lanza la primera pregunta."""
    # max_tokens=600: el saludo completo del LLM ronda 250-300 palabras en
    # español (≈ 420-500 tokens). 600 garantiza que ninguna respuesta natural
    # quede truncada a mitad de frase, independientemente de la variación
    # de verbosidad del modelo entre llamadas.
    prompt = (
        "Eres Trayector-IA, un orientador vocacional empático y profesional de la "
        "Universidad Veracruzana, Facultad de Negocios y Tecnologías, Campus Ixtac.\n\n"
        "Saluda al estudiante con entusiasmo y calidez. Explícale brevemente que le "
        "harás 10 preguntas divididas en dos bloques: las primeras 5 exploran su "
        "situación y gustos actuales, y las últimas 5 exploran su visión profesional "
        "a futuro. El sistema usará Inteligencia Artificial para analizar sus respuestas "
        "y encontrar la carrera universitaria que mejor se adapte a su perfil.\n\n"
        "Pídele que responda con detalle y honestidad, ya que la calidad del análisis "
        "depende de la profundidad de sus respuestas.\n\n"
        f"Finalmente, formula esta primera pregunta. "
        f"Escríbela SIEMPRE en negritas usando dobles asteriscos, así: "
        f"**{PREGUNTAS[0]}**\n\n"
        "IMPORTANTE: completa siempre la última oración antes de terminar. "
        "No dejes ningún pensamiento a medias."
    )

    try:
        resp = cliente_groq.chat.completions.create(
            messages=[{"role": "system", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Error en Groq (saludo): {e}")
        return (
            "¡Hola! Me alegra conocerte. Soy **Trayector-IA**, tu orientador vocacional "
            "de la Universidad Veracruzana, Facultad de Negocios y Tecnologías.\n\n"
            "Voy a realizarte **10 preguntas** organizadas en dos bloques: las primeras 5 "
            "explorarán tu situación actual —tus intereses, habilidades y actividades que "
            "disfrutas—, mientras que las últimas 5 explorarán tu visión profesional a "
            "futuro. Con base en tus respuestas, el sistema de Inteligencia Artificial "
            "identificará la carrera universitaria que mejor se adapte a tu perfil.\n\n"
            "Es importante que respondas con detalle y honestidad: cuanto más profundas "
            "sean tus respuestas, más precisa será la recomendación.\n\n"
            f"**{PREGUNTAS[0]}**"
        )

# ── Evaluación de respuesta ───────────────────────────────────────────────────

def evaluar_respuesta_usuario(respuesta_usuario: str, indice_actual: int) -> dict:
    """
    Evalúa si la respuesta es útil y formula la siguiente pregunta.
    """
    pregunta_actual = PREGUNTAS[indice_actual]
    es_ultima = (indice_actual + 1 >= len(PREGUNTAS))
    siguiente_pregunta = "" if es_ultima else PREGUNTAS[indice_actual + 1]

    aviso_bloque = ""
    if not es_ultima and (indice_actual + 1) in BLOQUES:
        aviso_bloque = (
            f"\n\nAntes de formular la siguiente pregunta, indica al estudiante que "
            f"ahora comienza el segundo bloque: '{BLOQUES[indice_actual + 1]}'. "
            f"Explica brevemente que ahora explorarán su proyección profesional futura."
        )

    prompt_buena_ultima = (
        "  → Como es la última pregunta, despídete cálidamente e indícale que "
        "vas a procesar sus resultados con el sistema de IA.\n"
    ) if es_ultima else (
        f"{aviso_bloque}\n"
        f"  → Formula la siguiente pregunta (pregunta {indice_actual + 2}) "
        f"en negritas usando dobles asteriscos, así: **{siguiente_pregunta}**\n"
    )

    prompt_sistema = (
        "Eres Trayector-IA, orientador vocacional de la Universidad Veracruzana.\n\n"
        f"El estudiante respondió a la pregunta {indice_actual + 1} de {len(PREGUNTAS)}:\n"
        f"PREGUNTA: \"{pregunta_actual}\"\n"
        f"RESPUESTA: \"{respuesta_usuario}\"\n\n"
        "Evalúa si la respuesta es útil:\n"
        "- Es MALA si tiene menos de 10 palabras, es ambigua, o no está relacionada con la pregunta.\n"
        "- Es BUENA si el estudiante responde de forma relevante y con suficiente detalle.\n\n"
        "Si la respuesta es MALA:\n"
        "  → Genera un breve mensaje empático pidiendo que elabore más su respuesta.\n"
        f"  → Vuelve a formular EXACTAMENTE esta misma pregunta en negritas: **{pregunta_actual}**\n"
        "  → NO menciones ni adelantes ninguna otra pregunta.\n\n"
        "Si la respuesta es BUENA:\n"
        "  → Haz un breve comentario validando su respuesta.\n"
        f"{prompt_buena_ultima}"
        "\nResponde ESTRICTAMENTE en JSON con dos claves:\n"
        "- \"es_valida\": booleano (true si fue buena, false si fue mala/corta)\n"
        "- \"mensaje\": string (tu respuesta conversacional al estudiante)"
    )

    try:
        resp = cliente_groq.chat.completions.create(
            messages=[{"role": "system", "content": prompt_sistema}],
            model="llama-3.3-70b-versatile",
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}

        data_norm = {k.lower(): v for k, v in data.items()}
        es_valida = (data_norm.get('es_valida') or data_norm.get('esvalida') or data_norm.get('valid') or data_norm.get('is_valid'))
        
        if isinstance(es_valida, str):
            es_valida = es_valida.lower() == 'true'

        mensaje = (data_norm.get('mensaje') or data_norm.get('message') or data_norm.get('respuesta') or data_norm.get('response'))

        if not mensaje:
            mensaje = f"Entendido.\n\n{siguiente_pregunta}" if siguiente_pregunta else "¡Completaste todas las preguntas!"

        return {"es_valida": bool(es_valida), "mensaje": mensaje}

    except Exception as e:
        print(f"Error en Groq (evaluación): {e}")
        # Salvavidas en caso de que Groq falle a mitad del test
        mensaje_rescate = f"Entendido, he guardado tu respuesta.\n\n{siguiente_pregunta}" if siguiente_pregunta else "¡Excelente! He procesado todas tus respuestas."
        return {"es_valida": True, "mensaje": mensaje_rescate}


# ── Explicación de afinidad ───────────────────────────────────────────────────

def generar_explicacion_afinidad(
    respuestas: list,
    carrera_detectada: str,
    porcentaje: float
) -> str:
    """Genera una explicación personalizada de afinidad con la carrera."""

    contexto = "\n".join(
        f"Pregunta {i + 1}: {PREGUNTAS[i]}\nRespuesta: {respuestas[i]}"
        for i in range(len(respuestas))
    )

    prompt = (
        "Eres Trayector-IA, orientador vocacional experto de la Universidad Veracruzana.\n\n"
        f"El modelo de NLP+KNN determinó una afinidad del {porcentaje}% con: {carrera_detectada}.\n\n"
        "Historial de la entrevista:\n"
        f"{contexto}\n\n"
        "Redacta 3-4 oraciones dirigiéndote al estudiante en segunda persona ('tú'). "
        "Explica de forma clara y objetiva por qué su perfil se alinea con "
        f"{carrera_detectada}, mencionando explícitamente detalles de sus respuestas. "
        "No inventes datos que el estudiante no haya mencionado. "
        "Mantén un tono alentador, profesional y motivador."
    )

    try:
        resp = cliente_groq.chat.completions.create(
            messages=[{"role": "system", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.6,
            max_tokens=320,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"Error en Groq (explicación): {e}")
        # Salvavidas si la IA falla al generar el resultado final
        return f"Tus respuestas indican un perfil compatible con {carrera_detectada}. (Nota: La IA conversacional para detalles avanzados está temporalmente inactiva, pero el cálculo matemático es exacto)."