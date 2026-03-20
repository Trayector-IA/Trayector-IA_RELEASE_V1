import json
import csv
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem.snowball import SnowballStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import KNeighborsClassifier

# Descargas necesarias de NLTK (ejecutar una sola vez)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')

# Inicializar herramientas NLTK
stemmer = SnowballStemmer('spanish')
stop_words = set(stopwords.words('spanish'))

def preprocesar_texto(texto):
    """Realiza la limpieza, normalización, eliminación de stopwords, tokenización y stemming."""
    if not texto:
        return ""
    # 1. Limpieza y Normalización (Minúsculas y eliminar caracteres especiales)
    texto = texto.lower()
    texto = re.sub(r'[^\w\s]', '', texto)
    
    # 2. Tokenización
    tokens = word_tokenize(texto, language='spanish')
    
    # 3 & 4. Eliminación de stopwords y Stemming (Lematización aproximada)
    tokens_limpios = [stemmer.stem(word) for word in tokens if word not in stop_words]
    
    return " ".join(tokens_limpios)

def entrenar_modelo_knn(ruta_csv):
    """Carga el CSV, extrae perfiles de ingreso/egreso y entrena el modelo KNN con TF-IDF."""
    textos_entrenamiento = []
    etiquetas = []
    
    # Abrimos el archivo CSV
    with open(ruta_csv, mode='r', encoding='utf-8') as archivo:
        lector = csv.DictReader(archivo)
        
        for fila in lector:
            carrera = fila['Programa educativo']
            perfil_ingreso = fila['Perfil de ingreso (síntesis)']
            perfil_egreso = fila['Perfil de egreso (síntesis)']
            
            # Agregamos el perfil de ingreso como un vector de texto (vecino)
            if perfil_ingreso:
                textos_entrenamiento.append(preprocesar_texto(perfil_ingreso))
                etiquetas.append(carrera)
                
            # Agregamos el perfil de egreso como un segundo vector de texto (vecino)
            if perfil_egreso:
                textos_entrenamiento.append(preprocesar_texto(perfil_egreso))
                etiquetas.append(carrera)
                
    # Vectorización TF-IDF
    vectorizador = TfidfVectorizer()
    X_entrenamiento = vectorizador.fit_transform(textos_entrenamiento)
    
    # Configuramos KNN usando ponderación por distancia
    # n_neighbors=3 asegura que considere una buena muestra del entorno sin diluir precisión
    knn = KNeighborsClassifier(n_neighbors=3, weights='distance', metric='cosine')
    knn.fit(X_entrenamiento, etiquetas)
    
    return vectorizador, knn, knn.classes_

def analizar_afinidad(respuestas_alumno, vectorizador, modelo_knn, clases):
    """Procesa las respuestas y calcula el porcentaje de similitud por carrera."""
    # Unificamos y preprocesamos las respuestas del estudiante
    perfil_crudo = " ".join(respuestas_alumno)
    perfil_procesado = preprocesar_texto(perfil_crudo)
    
    # Vectorizamos el perfil del alumno
    vector_alumno = vectorizador.transform([perfil_procesado])
    
    # predict_proba devuelve las probabilidades basadas en la cercanía y peso de los vecinos
    probabilidades = modelo_knn.predict_proba(vector_alumno)[0]
    
    resultados = []
    for idx, prob in enumerate(probabilidades):
        if prob > 0: # Solo mostramos si hay alguna afinidad
            resultados.append({
                "Carrera": clases[idx],
                "Similitud": round(prob * 100, 2)
            })
            
    # Ordenar por mayor afinidad
    return sorted(resultados, key=lambda x: x["Similitud"], reverse=True)

def obtener_lista_carreras(ruta_csv):
    """Devuelve una lista única de todas las carreras en el CSV."""
    carreras = set()
    with open(ruta_csv, mode='r', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            carreras.add(fila['Programa educativo'])
    return sorted(list(carreras))

def obtener_info_carrera(ruta_csv, nombre_carrera):
    """Devuelve el registro completo de una carrera específica."""
    with open(ruta_csv, mode='r', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            if fila['Programa educativo'] == nombre_carrera:
                return fila
    return {}