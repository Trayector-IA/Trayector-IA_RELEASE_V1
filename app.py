import os
import uuid
import json
from io import BytesIO
from database import db_client
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from api.orientador import OrientadorAPI

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'trayectoria-ia-dev-secret-2024')

orientador = OrientadorAPI()

# ── Store en memoria del servidor ─────────────────────────────────────────────
# Guarda las respuestas y resultado fuera de la cookie de sesión.
# La cookie solo almacena el sid (UUID pequeño) + el índice actual.
# Para producción multi-proceso: reemplazar por Redis o filesystem.
_STORE: dict = {}


def get_store(sid: str) -> dict:
    if sid not in _STORE:
        _STORE[sid] = {'respuestas': [], 'resultado': None}
    return _STORE[sid]

@app.route('/admin')
def admin_dashboard():
    # Muro de seguridad: validación estricta de sesión
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))
    
    # Extraemos la información fresca de la base de datos
    usuarios = db_client.obtener_todos_usuarios()
    resultados = db_client.obtener_todos_resultados()
    
    # Renderizamos la plantilla inyectando los datos
    return render_template('admin.html', usuarios=usuarios, resultados=resultados)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    usuario_id = data.get('usuario_id', '').strip()
    password = data.get('password', '').strip() # Opcional, solo para admin

    if not usuario_id:
        return jsonify({'success': False, 'error': 'ID no proporcionado.'}), 400

    es_valido, mensaje, rol = db_client.verificar_acceso(usuario_id, password)
    
    if es_valido:
        session['usuario_id'] = usuario_id
        session['rol'] = rol
        session.modified = True
        return jsonify({
            'success': True, 
            'message': mensaje,
            'rol': rol
        })
    else:
        return jsonify({'success': False, 'error': mensaje}), 403

# ─── PAGE ROUTES ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/orientador')
def orientador_page():
    return render_template('orientador.html')

@app.route('/resultados')
def resultados():
    sid = session.get('sid')
    resultado = _STORE.get(sid, {}).get('resultado') if sid else None
    if not resultado:
        return render_template('resultados.html', locked=True)
    return render_template('resultados.html', locked=False, resultado=resultado)

@app.route('/sobre-nosotros')
def sobre_nosotros():
    return render_template('sobre-nosotros.html')


# ─── API ROUTES ───────────────────────────────────────────────────────────────

@app.route('/api/start', methods=['POST'])
def api_start():
    # El salvavidas: silent=True evita que Flask colapse si JS manda una petición vacía
    data = request.get_json(silent=True) or {}
    usuario_modal = data.get('usuario_id', '').strip()

    usuario_guardado = session.get('usuario_id')
    rol_guardado = session.get('rol')

    if not usuario_guardado:
        if not usuario_modal:
            return jsonify({'success': False, 'error': 'El ID es obligatorio.'})
        
        acceso_permitido, mensaje, rol = db_client.verificar_acceso(usuario_modal)
        if not acceso_permitido:
            return jsonify({'success': False, 'error': mensaje})
        
        usuario_guardado = usuario_modal
        rol_guardado = rol

    # --- BARRERA DE ESTADO ---
    if rol_guardado != 'admin' and db_client.ya_realizo_prueba(usuario_guardado):
        session.clear()
        return jsonify({'success': False, 'error': 'Este usuario ya completó la prueba.'})
    # -------------------------

    # --- REANUDAR PROGRESO EXISTENTE ---
    progreso = db_client.obtener_progreso(usuario_guardado)
    if progreso and progreso.get('indice', 0) > 0:
        sid = str(uuid.uuid4())
        indice_guardado = progreso['indice']
        respuestas_guardadas = progreso.get('respuestas', [])

        session['usuario_id'] = usuario_guardado
        session['rol'] = rol_guardado
        session['sid'] = sid
        session['indice_pregunta'] = indice_guardado
        session['completado'] = False
        session.modified = True

        _STORE[sid] = {'respuestas': respuestas_guardadas, 'resultado': None}

        pregunta_actual = orientador.obtener_pregunta(indice_guardado)
        return jsonify({
            'success': True,
            'reanudado': True,
            'message': (
                f"¡Bienvenido de vuelta! Hemos restaurado tu progreso.\n\n"
                f"Continuemos desde la **pregunta {indice_guardado + 1}** "
                f"de {orientador.total_preguntas()}:\n\n**{pregunta_actual}**"
            ),
            'total_preguntas': orientador.total_preguntas(),
            'pregunta_actual': indice_guardado,
        })
    # -----------------------------------

    session['usuario_id'] = usuario_guardado
    session['rol'] = rol_guardado

    sid = str(uuid.uuid4())
    session['sid'] = sid
    session['indice_pregunta'] = 0
    session['completado'] = False
    session.modified = True

    _STORE[sid] = {'respuestas': [], 'resultado': None}

    try:
        saludo = orientador.obtener_saludo_inicial()
        return jsonify({
            'success': True,
            'reanudado': False,
            'message': saludo,
            'total_preguntas': orientador.total_preguntas(),
            'pregunta_actual': 0
        })
    except Exception as e:
        app.logger.error(f'Error en api_start: {e}')
        return jsonify({'success': False, 'error': 'Error interno del servidor'})


@app.route('/api/question', methods=['GET'])
def api_question():
    indice = session.get('indice_pregunta', 0)
    return jsonify({
        'success': True,
        'pregunta': orientador.obtener_pregunta(indice),
        'indice': indice,
        'total': orientador.total_preguntas()
    })


@app.route('/api/answer', methods=['POST'])
def api_answer():
    data = request.get_json()
    respuesta_usuario = data.get('respuesta', '').strip()
    indice_actual = session.get('indice_pregunta', 0)
    sid = session.get('sid')

    if not sid:
        return jsonify({'success': False, 'error': 'Sesión no iniciada. Recarga la página.'}), 400

    # Validación mínima de palabras
    palabras = respuesta_usuario.split()
    if len(palabras) < 10:
        return jsonify({
            'success': True,
            'es_valida': False,
            'message': f'⚠️ Tu respuesta tiene solo {len(palabras)} palabras. Elabora más (mínimo 10).',
            'indice': indice_actual,
            'total': orientador.total_preguntas()
        })

    try:
        evaluacion = orientador.evaluar_respuesta(respuesta_usuario, indice_actual)

        # Normalizar claves del LLM (puede responder en inglés)
        eval_norm = {k.lower(): v for k, v in evaluacion.items()}
        es_valida = (eval_norm.get('es_valida') or eval_norm.get('esvalida')
                     or eval_norm.get('valid') or eval_norm.get('is_valid'))
        if isinstance(es_valida, str):
            es_valida = es_valida.lower() == 'true'
        es_valida = bool(es_valida)

        mensaje = (eval_norm.get('mensaje') or eval_norm.get('message')
                   or eval_norm.get('respuesta') or eval_norm.get('response')
                   or 'Gracias por tu respuesta.')

        if es_valida:
            # Guardar respuesta en store de memoria (no en cookie)
            store = get_store(sid)
            store['respuestas'].append(respuesta_usuario)

            # Solo guardar el índice (número pequeño) en la cookie
            session['indice_pregunta'] = indice_actual + 1
            session.modified = True

            # Persistir progreso en MongoDB para sobrevivir reinicios
            db_client.guardar_progreso(
                session.get('usuario_id'),
                store['respuestas'],
                indice_actual + 1,
            )

        nuevo_indice = session['indice_pregunta']
        return jsonify({
            'success': True,
            'es_valida': es_valida,
            'message': mensaje,
            'indice': nuevo_indice,
            'total': orientador.total_preguntas(),
            'finalizado': nuevo_indice >= orientador.total_preguntas()
        })
    except Exception as e:
        app.logger.error(f'[/api/answer] Error en pregunta {indice_actual}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/result', methods=['POST'])
def api_result():
    sid = session.get('sid')
    usuario_id = session.get('usuario_id') 

    if not sid or not usuario_id:
        return jsonify({'success': False, 'error': 'Sesión no iniciada o ID inválido.'}), 400

    store = get_store(sid)
    respuestas = store.get('respuestas', [])

    if len(respuestas) < orientador.total_preguntas():
        return jsonify({
            'success': False,
            'error': f'Faltan respuestas ({len(respuestas)}/{orientador.total_preguntas()}).'
        }), 400

    try:
        resultado = orientador.obtener_resultado(respuestas)
        
        # --- NUEVA BARRERA DE ERROR ---
        # Si el orientador detectó un fallo lógico (KNN vacío, modelo caído, etc.)
        if resultado.get("error"):
            # Devolvemos success=False para que el JS active la alerta roja
            return jsonify({'success': False, 'error': resultado.get("explicacion", "Error en el análisis.")})
        # ------------------------------

        # Si no hay error, el flujo sigue normal
        store['resultado'] = resultado
        session['completado'] = True
        session.modified = True
        db_client.limpiar_progreso(usuario_id)  # test completado → eliminar progreso parcial

        carrera_top = resultado.get("carrera_recomendada")
        porcentaje_top = resultado.get("porcentaje")
        otras_opciones = resultado.get("otras_opciones", [])
        
        datos_para_mongo = {
            "carrera_principal": carrera_top,
            "similitud_principal": porcentaje_top,
            "otras_carreras": otras_opciones
        }

        # Solo guardamos en DB si fue un éxito real
        db_client.guardar_resultado(usuario_id, datos_para_mongo)

        return jsonify({'success': True, 'resultado': resultado})
            
    except Exception as e:
        app.logger.error(f'[/api/result] Error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/login')
def login_page():
    # Si ya es admin, lo mandamos directo a su panel
    if session.get('rol') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Destruimos todas las credenciales del servidor
    session.clear()
    return redirect(url_for('index'))


@app.route('/api/reset', methods=['POST'])
def api_reset():
    sid = session.get('sid')
    usuario_id = session.get('usuario_id')
    if sid and sid in _STORE:
        del _STORE[sid]
    if usuario_id:
        db_client.limpiar_progreso(usuario_id)
    session.clear()
    return jsonify({'success': True})

@app.route('/test-diseno')
def test_diseno():
    # Datos simulados con información realista de la UV región Orizaba-Córdoba
    resultado_falso = {
        "total_respuestas": 10,
        "carrera_recomendada": "Ingeniería de Software",
        "explicacion": "Tienes un gran interés en resolver problemas tecnológicos y la ciberseguridad, lo cual se alinea perfectamente con el enfoque de esta carrera.",
        "facultad": "Facultad de Negocios y Tecnologías",
        "municipio": "Ixtaczoquitlán",
        "modalidad": "Escolarizada",
        "perfil_ingreso": "Interés por el desarrollo de software, pensamiento lógico-matemático y vocación por la tecnología.",
        "perfil_egreso": "Profesional capaz de diseñar, desarrollar e implementar soluciones de software innovadoras y seguras.",
        "otras_opciones": [
            {"Carrera": "Tecnologías de Información en las Organizaciones", "Similitud": 85},
            {"Carrera": "Ingeniería en Sistemas Computacionales", "Similitud": 78},
            {"Carrera": "Redes y Servicios de Cómputo", "Similitud": 65}
        ]
    }
    
    # Renderizamos la plantilla saltando el candado
    return render_template('resultados.html', locked=False, resultado=resultado_falso)


@app.route('/api/download-pdf', methods=['GET'])
def api_download_pdf():
    sid      = session.get('sid')
    resultado = _STORE.get(sid, {}).get('resultado') if sid else None

    if not resultado:
        return jsonify({'success': False, 'error': 'No hay resultados disponibles. Completa la entrevista primero.'}), 400

    try:
        from api.pdf_generator import generate_results_pdf
        pdf_bytes = generate_results_pdf(resultado)
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='reporte-vocacional-trayectoria.pdf',
        )
    except Exception as e:
        app.logger.error(f'[/api/download-pdf] Error: {e}')
        return jsonify({'success': False, 'error': 'No se pudo generar el PDF. Inténtalo de nuevo.'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5001)