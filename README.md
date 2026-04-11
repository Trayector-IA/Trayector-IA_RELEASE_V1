# Trayector-IA — Sistema de Orientación Vocacional con IA

Plataforma web de orientación vocacional basada en NLP + KNN + LLM (Groq).

## Estructura del proyecto

```
/trayector-ia
├── app.py                  ← Flask app principal
├── requirements.txt
├── perfil_academico.csv    ← (debes agregar tu CSV aquí)
├── llm_groq_logic.py       ← (copia desde tu proyecto Streamlit)
├── nlp_knn_logic.py        ← (copia desde tu proyecto Streamlit)
│
├── /api
│   ├── __init__.py
│   └── orientador.py       ← Facade del pipeline ML
│
├── /templates
│   ├── base.html
│   ├── index.html
│   ├── orientador.html
│   ├── resultados.html
│   └── sobre-nosotros.html
│
├── /static
│   ├── /css
│   │   ├── global.css
│   │   ├── index.css
│   │   ├── orientador.css
│   │   ├── resultados.css
│   │   └── sobre.css
│   └── /js
│       ├── theme.js
│       └── chat.js
```

## Instalación

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Descargar recursos NLTK (solo la primera vez)
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"

# 3. Configurar variable de entorno
export GROQ_API_KEY="tu_api_key_de_groq"
# En Windows: set GROQ_API_KEY=tu_api_key_de_groq

# 4. Copiar archivos de lógica desde proyecto Streamlit
#    - llm_groq_logic.py  →  raíz del proyecto (quitar `st.secrets`, usar os.environ)
#    - nlp_knn_logic.py   →  raíz del proyecto
#    - perfil_academico.csv → raíz del proyecto

# 5. Ejecutar
python app.py
```

Abre `http://localhost:5000` en tu navegador.

## Adaptación de llm_groq_logic.py

En `llm_groq_logic.py`, cambia:
```python
# Antes (Streamlit)
cliente_groq = Groq(api_key=st.secrets["GROQ_API_KEY"])

# Después (Flask)
cliente_groq = Groq(api_key=os.environ.get("GROQ_API_KEY"))
```

## API Endpoints

| Método | Ruta          | Descripción                         |
|--------|---------------|-------------------------------------|
| POST   | /api/start    | Inicia sesión, retorna saludo inicial|
| GET    | /api/question | Obtiene la pregunta actual           |
| POST   | /api/answer   | Envía respuesta del usuario          |
| POST   | /api/result   | Procesa y retorna resultado final    |
| POST   | /api/reset    | Reinicia la sesión                   |

## Rutas de páginas

| Ruta              | Descripción                  |
|-------------------|------------------------------|
| /                 | Landing page                 |
| /orientador       | Chat de entrevista           |
| /resultados       | Resultado vocacional         |
| /sobre-nosotros   | Sobre el proyecto            |
