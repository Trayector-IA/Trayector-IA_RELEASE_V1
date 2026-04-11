import csv
import re
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem.snowball import SnowballStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import KNeighborsClassifier

# Descargas necesarias de NLTK
# Descargas necesarias de NLTK (Actualizado para la nube)
try:
    nltk.download('punkt_tab', quiet=True) 
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
except Exception as e:
    print(f"[NLTK] Advertencia al descargar recursos: {e}")

stemmer = SnowballStemmer('spanish')
stop_words_base = set(stopwords.words('spanish'))

# 1. EL FILTRO: Lista negra de palabras burocráticas universitarias
palabras_basura = {
    "profesional", "capacidad", "conocimientos", "habilidades",
    "desarrollo", "gestión", "gestionar", "analizar", "liderar",
    "aplicar", "evaluar", "diseñar", "implementar", "participar",
    "formación", "egresado", "aspirante", "alumno", "estudiante",
    "aptitud", "actitud", "ética", "visión", "competencias", "programa",
    "educativo", "disciplina", "campo", "laboral", "social", "tecnológico",
    "capaz", "resolver", "problemas", "equipo", "trabajo"
}
# Unimos las stopwords tradicionales con nuestra lista negra
stop_words = stop_words_base.union(palabras_basura)


def preprocesar_texto(texto):
    if not texto:
        return ""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s]', '', texto)
    tokens = word_tokenize(texto, language='spanish')
    # Aquí actúa el filtro: si la palabra está en la lista negra, la ignora
    tokens_limpios = [stemmer.stem(word) for word in tokens if word not in stop_words]
    return " ".join(tokens_limpios)

def entrenar_modelo_knn(ruta_csv):
    textos_entrenamiento = []
    etiquetas = []
    
    with open(ruta_csv, mode='r', encoding='utf-8-sig') as archivo:
        lector = csv.DictReader(archivo)
        
        for fila in lector:
            carrera = fila.get('Programa educativo', '')
            if not carrera:
                continue
            
            # 2. LA FUSIÓN: Juntamos todo el contexto de Ingreso en un solo bloque gigante
            bloque_ingreso = " ".join([
                fila.get('Perfil de Ingreso (Expandido)', ''),
                fila.get('Palabras Clave (Ingreso)', ''),
                fila.get('Sinónimos y Variaciones (Ingreso)', ''),
                fila.get('Frases Vocacionales (Ingreso)', ''),
                fila.get('Intereses y Actividades (Ingreso)', '')
            ])
            
            # 3. LA FUSIÓN: Juntamos todo el contexto de Egreso
            bloque_egreso = " ".join([
                fila.get('Perfil de Egreso (Expandido)', ''),
                fila.get('Palabras Clave Profesionales (Egreso)', ''),
                fila.get('Sinónimos y Variaciones (Egreso)', ''),
                fila.get('Actividades y Contextos (Egreso)', ''),
                fila.get('Frases del Ejercicio Profesional (Egreso)', '')
            ])
            
            if bloque_ingreso.strip():
                textos_entrenamiento.append(preprocesar_texto(bloque_ingreso))
                etiquetas.append(carrera)
                
            if bloque_egreso.strip():
                textos_entrenamiento.append(preprocesar_texto(bloque_egreso))
                etiquetas.append(carrera)
                
    vectorizador = TfidfVectorizer()
    X_entrenamiento = vectorizador.fit_transform(textos_entrenamiento)
    
    # Subimos a n_neighbors=5 para que te recomiende un abanico un poco más amplio
    knn = KNeighborsClassifier(n_neighbors=5, weights='distance', metric='cosine')
    knn.fit(X_entrenamiento, etiquetas)
    
    return vectorizador, knn, knn.classes_

def analizar_afinidad(respuestas_alumno, vectorizador, modelo_knn, clases):
    perfil_crudo = " ".join(respuestas_alumno)
    perfil_procesado = preprocesar_texto(perfil_crudo)
    
    vector_alumno = vectorizador.transform([perfil_procesado])
    probabilidades = modelo_knn.predict_proba(vector_alumno)[0]
    
    resultados = []
    for idx, prob in enumerate(probabilidades):
        if prob > 0: 
            resultados.append({
                "Carrera": clases[idx],
                "Similitud": round(prob * 100, 2)
            })
            
    return sorted(resultados, key=lambda x: x["Similitud"], reverse=True)

def obtener_lista_carreras(ruta_csv):
    carreras = set()
    # Usamos utf-8-sig para ignorar el BOM de Excel
    with open(ruta_csv, mode='r', encoding='utf-8-sig') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            carreras.add(fila.get('Programa educativo', '').strip())
    # Filtramos por si hay filas vacías
    return sorted([c for c in carreras if c])

def obtener_info_carrera(ruta_csv, nombre_carrera):
    # Usamos utf-8-sig para ignorar el BOM de Excel
    with open(ruta_csv, mode='r', encoding='utf-8-sig') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            # Usamos .strip() en ambos lados para que coincidan sin importar los espacios extra
            if fila.get('Programa educativo', '').strip() == nombre_carrera.strip():
                return fila
    return {}