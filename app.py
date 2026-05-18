import os
import uuid
import json
from io import BytesIO
from database_cloud import db_cloud
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


def _clasificar_semestre(uid_str: str):
    """
    Busca el primer segmento todo-numérico (separado por '_') que empiece
    con '4' o '6' para determinar semestre y bachillerato.
    Ej: 'cpo_est_601' → ('600', '1')
        'alumno_401'  → ('400', '1')
        '600'         → ('600', '0')
    Devuelve (None, None) si no hay coincidencia.
    """
    for parte in uid_str.split("_"):
        if parte.isdigit():
            sufijo = parte[1:]
            bach = str(int(sufijo)) if sufijo else "0"
            if parte[0] == "4":
                return "400", bach
            elif parte[0] == "6":
                return "600", bach
    return None, None

@app.route('/admin')
def admin_panel():
    # 1. Filtro de seguridad por rol
    if session.get('rol') not in ['admin', 'maestro']:
        return redirect('/login')

    scope        = session.get('cloud_scope', 'global')
    preparatoria = session.get('cloud_preparatoria')
    todos_los_alumnos  = db_cloud.obtener_resultados_filtrados(scope, preparatoria)
    todos_los_usuarios = db_cloud.obtener_usuarios_filtrados(scope, preparatoria)

    # 3. Clasificación por semestre y bachillerato
    bachilleratos_400 = {}
    bachilleratos_600 = {}
    otros_grupos = []

    for alumno in todos_los_alumnos:
        uid_str = str(alumno.get("usuario_id", ""))
        semestre, bach = _clasificar_semestre(uid_str)
        if semestre == "400":
            bachilleratos_400.setdefault(bach, []).append(alumno)
        elif semestre == "600":
            bachilleratos_600.setdefault(bach, []).append(alumno)
        else:
            otros_grupos.append(alumno)

    bachilleratos_400 = dict(sorted(bachilleratos_400.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]))
    bachilleratos_600 = dict(sorted(bachilleratos_600.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]))

    # 4. Renderizado con las variables mapeadas para el admin.html con pestañas
    return render_template(
        'admin.html',
        bachilleratos_400=bachilleratos_400,
        bachilleratos_600=bachilleratos_600,
        total_400=sum(len(v) for v in bachilleratos_400.values()),
        total_600=sum(len(v) for v in bachilleratos_600.values()),
        otros_grupos=otros_grupos,
        usuarios=todos_los_usuarios
    )

@app.route('/api/login', methods=['POST'])
def api_login():
    data       = request.get_json()
    usuario_id = data.get('usuario_id', '').strip()
    password   = data.get('password',   '').strip()

    if not usuario_id:
        return jsonify({'success': False, 'error': 'ID no proporcionado.'}), 400

    ok, mensaje, rol, meta = db_cloud.verificar_acceso(usuario_id, password)
    if ok:
        session['usuario_id']         = usuario_id
        session['rol']                = rol
        session['cloud_session_id']   = meta.get('session_id')
        session['cloud_scope']        = meta.get('scope', 'local')
        session['cloud_preparatoria'] = meta.get('preparatoria')
        session.modified = True
        return jsonify({
            'success': True,
            'message': mensaje,
            'rol':     rol,
            'cloud':   bool(meta.get('session_id')),
        })

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
    # 1. Detectar si el test se acaba de completar (Única vista permitida para alumnos)
    finalizado = request.args.get('finalizado') == 'true'
    if finalizado:
        return render_template('resultados.html', test_finalizado=True)

    # 2. BARRERA DE SEGURIDAD: ¿Es maestro?
    # Si no hay sesión de admin, bloqueamos el acceso y mostramos el aviso de "Solo Maestros"
    if session.get('rol') not in ['admin', 'maestro']:
        return render_template('resultados.html', acceso_restringido=True)

    # 3. LÓGICA PARA MAESTROS (Solo accesible si rol == 'admin')
    codigo_busqueda = request.args.get('codigo', '').strip()
    if codigo_busqueda:
        doc_db = db_cloud.obtener_resultado_por_id(codigo_busqueda)
        if doc_db and "resultado" in doc_db:
            res = doc_db["resultado"]
            
            # (Mantenemos tu lógica de mapeo para que el maestro vea todo bien)
            if "carrera_principal" in res and "carrera_recomendada" not in res:
                res["carrera_recomendada"] = res["carrera_principal"]
            
            # El maestro SÍ puede ver los porcentajes si quieres, 
            # pero mantendremos la consistencia de ocultarlos si prefieres.
            res["porcentaje"] = None 

            source_opciones = res.get("otras_carreras") or res.get("otras_opciones") or []
            res["otras_opciones"] = [
                {"Carrera": op.get("Carrera") or op.get("carrera") if isinstance(op, dict) else str(op), "Similitud": None}
                for op in source_opciones
            ]
            
            return render_template('resultados.html', acceso_maestro=True, resultado=res)
        else:
            return render_template('resultados.html', acceso_maestro=True, error_busqueda="Código no encontrado.")

    # Si es maestro pero no ha buscado nada aún
    return render_template('resultados.html', acceso_maestro=True)

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
        
        acceso_permitido, mensaje, rol, _ = db_cloud.verificar_acceso(usuario_modal)
        if not acceso_permitido:
            return jsonify({'success': False, 'error': mensaje})

        usuario_guardado = usuario_modal
        rol_guardado = rol

    # --- BARRERA DE ESTADO ---
    if rol_guardado != 'admin' and db_cloud.ya_realizo_prueba(usuario_guardado):
        session.clear()
        return jsonify({'success': False, 'error': 'Este usuario ya completó la prueba.'})
    # -------------------------

    # --- REANUDAR PROGRESO EXISTENTE ---
    progreso = db_cloud.obtener_progreso(usuario_guardado)
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
            db_cloud.guardar_progreso(
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
        # _STORE is in-memory; recover from MongoDB if the server restarted
        progreso = db_cloud.obtener_progreso(usuario_id)
        if progreso and len(progreso.get('respuestas', [])) >= orientador.total_preguntas():
            respuestas = progreso['respuestas']
            store['respuestas'] = respuestas
        else:
            return jsonify({
                'success': False,
                'error': f'Faltan respuestas ({len(respuestas)}/{orientador.total_preguntas()}).'
            }), 400

    try:
        resultado = orientador.obtener_resultado(respuestas)
        
        if resultado.get("error"):
            return jsonify({'success': False, 'error': resultado.get("explicacion", "Error en el análisis.")})

        store['resultado'] = resultado
        session['completado'] = True
        session.modified = True
        db_cloud.limpiar_progreso(usuario_id)

        datos_para_mongo = resultado.copy()
        datos_para_mongo["carrera_principal"]   = datos_para_mongo.pop("carrera_recomendada", None)
        datos_para_mongo["similitud_principal"] = datos_para_mongo.pop("porcentaje", None)
        datos_para_mongo["otras_carreras"]      = datos_para_mongo.pop("otras_opciones", [])
        db_cloud.guardar_resultado(usuario_id, datos_para_mongo, respuestas=respuestas)

        return jsonify({'success': True, 'resultado': resultado})
            
    except Exception as e:
        app.logger.error(f'[/api/result] Error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/respuestas/<usuario_id>')
def api_admin_respuestas(usuario_id):
    if session.get('rol') not in ['admin', 'maestro']:
        return jsonify({'success': False, 'error': 'Sin permisos.'}), 403
    doc = db_cloud.obtener_resultado_por_id(usuario_id)
    if not doc:
        return jsonify({'success': False, 'error': 'No se encontraron datos para este usuario.'}), 404
    preguntas = orientador.preguntas
    respuestas = doc.get('respuestas', [])
    pares = [
        {
            'numero': i + 1,
            'pregunta': preguntas[i] if i < len(preguntas) else f'Pregunta {i+1}',
            'respuesta': respuestas[i] if i < len(respuestas) else None,
        }
        for i in range(len(preguntas))
    ]
    return jsonify({'success': True, 'usuario_id': usuario_id, 'pares': pares})


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id', '').strip()
        password   = request.form.get('password',   '').strip()

        valido, mensaje, rol, meta = db_cloud.verificar_acceso(usuario_id, password)

        if valido:
            session['usuario_id']         = usuario_id
            session['rol']                = rol
            session['cloud_session_id']   = meta.get('session_id')
            session['cloud_scope']        = meta.get('scope', 'local')
            session['cloud_preparatoria'] = meta.get('preparatoria')
            session.modified = True
            if rol in ['admin', 'maestro']:
                return redirect(url_for('admin_panel'))
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error=mensaje)
            
    # Esto es lo que se ejecuta si es GET
    if session.get('rol') in ['admin', 'maestro']:
        return redirect(url_for('admin_panel'))
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
        db_cloud.limpiar_progreso(usuario_id)
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

@app.route('/api/admin/download-report')
def admin_download_report():
    # 1. Validación de seguridad por rol
    if session.get('rol') not in ['admin', 'maestro']:
        return jsonify({'success': False, 'error': 'Acceso denegado.'}), 403
        
    # 2. Obtener el grupo solicitado desde la URL
    grupo        = request.args.get('grupo', '').strip()
    scope        = session.get('cloud_scope', 'global')
    preparatoria = session.get('cloud_preparatoria')
    todos_los_alumnos = db_cloud.obtener_resultados_filtrados(scope, preparatoria)
    
    # 3. Filtrar los alumnos pertenecientes únicamente a ese grupo
    alumnos_filtrados = []
    for alumno in todos_los_alumnos:
        uid_str = str(alumno.get("usuario_id", ""))
        
        semestre, _ = _clasificar_semestre(uid_str)
        if grupo == "400" and semestre == "400":
            alumnos_filtrados.append(alumno)
        elif grupo == "600" and semestre == "600":
            alumnos_filtrados.append(alumno)
        elif grupo == "otros" and semestre is None:
            alumnos_filtrados.append(alumno)

    # 4. COMPILACIÓN Y TRANSMISIÓN DEL PDF REAL
    from io import BytesIO
    from flask import send_file
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    # Inicializar el buffer en memoria para no saturar el almacenamiento del servidor
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=40, 
        leftMargin=40, 
        topMargin=40, 
        bottomMargin=40
    )
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos tipográficos personalizados para el documento
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6
    )
    
    header_style = ParagraphStyle(
        'HeaderStyle', 
        parent=styles['Normal'], 
        fontSize=10, 
        leading=12, 
        textColor=colors.white, 
        fontName='Helvetica-Bold'
    )
    
    cell_style = ParagraphStyle(
        'CellStyle', 
        parent=styles['Normal'], 
        fontSize=9, 
        leading=13, 
        textColor=colors.HexColor('#334155')
    )
    
    bold_cell = ParagraphStyle(
        'BoldCell', 
        parent=styles['Normal'], 
        fontSize=9, 
        leading=13, 
        fontName='Helvetica-Bold', 
        textColor=colors.HexColor('#0f172a')
    )
    
    # Estructuración de la cabecera del documento PDF
    story.append(Paragraph("Trayector-IA — Reporte General de Resultados", title_style))
    story.append(Paragraph(f"Filtro de exportación: Estudiantes pertenecientes al bloque {grupo}", styles['Normal']))
    story.append(Spacer(1, 15))
    
    # Matriz de datos de la tabla (Fila de encabezado inicial)
    data_matrix = [[
        Paragraph("ID Usuario", header_style),
        Paragraph("Carrera Principal Recomendada", header_style),
        Paragraph("Otras Opciones Afines Detectadas", header_style)
    ]]
    
    # Población de la matriz mapeando la estructura limpia de las celdas
    for al in alumnos_filtrados:
        uid = al.get("usuario_id", "N/A")
        res_data = al.get("resultado", {})
        
        if res_data:
            carrera_principal = res_data.get("carrera_principal", "N/A")
            otras_list = res_data.get("otras_carreras", [])
            otras_texto = ", ".join([op.get("Carrera", str(op)) for op in otras_list]) if otras_list else "Ninguna"
        else:
            carrera_principal = "Test no finalizado"
            otras_texto = "-"
            
        data_matrix.append([
            Paragraph(str(uid), cell_style),
            Paragraph(carrera_principal, bold_cell),
            Paragraph(otras_texto, cell_style)
        ])
        
    # Crear la tabla adaptando las proporciones al tamaño Carta (Letter)
    tabla_reporte = Table(data_matrix, colWidths=[80, 180, 272])
    tabla_reporte.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2dd4bf')), # Paleta de color identitaria
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])
    ]))
    
    story.append(tabla_reporte)
    doc.build(story)
    
    # Reposicionar el puntero del buffer para la lectura de descarga
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Reporte_Grupo_{grupo}.pdf",
        mimetype='application/pdf'
    )


# ── Eliminación de registros ──────────────────────────────────────────────────

@app.route('/api/admin/eliminar-resultado/<usuario_id>', methods=['DELETE'])
def eliminar_resultado(usuario_id):
    if session.get('rol') not in ['admin', 'maestro']:
        return jsonify({'success': False, 'error': 'Sin permisos.'}), 403

    scope = session.get('cloud_scope', 'global')
    prepa = session.get('cloud_preparatoria')
    ok = db_cloud.eliminar_resultado(usuario_id, scope, prepa)

    if ok:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Registro no encontrado o sin permisos.'}), 404


@app.route('/api/admin/eliminar-usuario/<usuario_id>', methods=['DELETE'])
def eliminar_usuario(usuario_id):
    if session.get('rol') != 'admin':
        return jsonify({'success': False, 'error': 'Solo el administrador puede eliminar usuarios.'}), 403

    # Evitar auto-eliminación
    if usuario_id == session.get('usuario_id'):
        return jsonify({'success': False, 'error': 'No puedes eliminar tu propia cuenta.'}), 400

    scope = session.get('cloud_scope', 'global')
    prepa = session.get('cloud_preparatoria')
    ok = db_cloud.eliminar_usuario(usuario_id, scope, prepa)

    if ok:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Usuario no encontrado o sin permisos.'}), 404


# ══════════════════════════════════════════════════════════════════════════════
# RUTAS CLOUD  –  agente_vocacional_cloud
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/cloud/login', methods=['POST'])
def api_cloud_login():
    """Login para admins cloud con control de sesiones y scope de preparatoria."""
    data       = request.get_json()
    usuario_id = data.get('usuario_id', '').strip()
    password   = data.get('password',   '').strip()

    if not usuario_id:
        return jsonify({'success': False, 'error': 'ID no proporcionado.'}), 400

    ok, mensaje, rol, meta = db_cloud.verificar_acceso(usuario_id, password)

    if ok:
        session['usuario_id']        = usuario_id
        session['rol']               = rol
        session['cloud_session_id']  = meta.get('session_id')
        session['cloud_scope']       = meta.get('scope', 'local')
        session['cloud_preparatoria']= meta.get('preparatoria')
        session.modified = True
        return jsonify({
            'success': True,
            'message': mensaje,
            'rol':     rol,
            'scope':   meta.get('scope'),
        })

    return jsonify({'success': False, 'error': mensaje}), 403


@app.route('/api/cloud/logout', methods=['POST'])
def api_cloud_logout():
    """Cierra la sesión cloud y la marca como inactiva en MongoDB."""
    cloud_sid = session.pop('cloud_session_id', None)
    session.pop('cloud_scope',        None)
    session.pop('cloud_preparatoria', None)
    session.pop('usuario_id',         None)
    session.pop('rol',                None)
    session.modified = True

    if cloud_sid:
        db_cloud.cerrar_sesion(cloud_sid)

    return jsonify({'success': True, 'message': 'Sesión cerrada.'})


@app.route('/api/cloud/registrar-estudiante', methods=['POST'])
def api_cloud_registrar_estudiante():
    """Registra uno o varios estudiantes en una preparatoria (solo admins cloud)."""
    if session.get('rol') not in ['admin', 'maestro']:
        return jsonify({'success': False, 'error': 'Sin permisos.'}), 403

    data        = request.get_json()
    preparatoria= data.get('preparatoria', '').strip().lower()
    cantidad    = int(data.get('cantidad', 1))
    scope       = session.get('cloud_scope', 'local')
    prepa_admin = session.get('cloud_preparatoria')

    # Admin local solo puede registrar en su propia preparatoria
    if scope == 'local' and preparatoria != prepa_admin:
        return jsonify({'success': False, 'error': 'Solo puedes registrar estudiantes de tu preparatoria.'}), 403

    if not preparatoria:
        return jsonify({'success': False, 'error': 'Preparatoria no especificada.'}), 400

    inicio  = db_cloud.obtener_siguiente_numero_estudiante(preparatoria)
    creados = db_cloud.registrar_estudiantes_lote(preparatoria, cantidad, inicio)

    return jsonify({
        'success': True,
        'creados': len(creados),
        'estudiantes': creados,
    })


@app.route('/admin/cloud')
def admin_cloud_panel():
    """Panel de administración cloud filtrado por preparatoria o global."""
    if session.get('rol') not in ['admin', 'maestro']:
        return redirect('/login')

    scope       = session.get('cloud_scope',        'local')
    preparatoria= session.get('cloud_preparatoria')

    todos_los_resultados = db_cloud.obtener_resultados_filtrados(scope, preparatoria)
    todos_los_usuarios   = db_cloud.obtener_usuarios_filtrados(scope, preparatoria)
    preparatorias_lista  = db_cloud.obtener_preparatorias()

    # Clasificar resultados por semestre y bachillerato
    bachilleratos_400 = {}
    bachilleratos_600 = {}
    otros_grupos = []

    for alumno in todos_los_resultados:
        campo_semestre = alumno.get("semestre")
        uid_str = str(alumno.get("usuario_id", ""))
        semestre, bach = _clasificar_semestre(uid_str)
        if campo_semestre == "4":
            semestre = "400"
        elif campo_semestre == "6":
            semestre = "600"
        if semestre == "400":
            bachilleratos_400.setdefault(bach or "0", []).append(alumno)
        elif semestre == "600":
            bachilleratos_600.setdefault(bach or "0", []).append(alumno)
        else:
            otros_grupos.append(alumno)

    bachilleratos_400 = dict(sorted(bachilleratos_400.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]))
    bachilleratos_600 = dict(sorted(bachilleratos_600.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]))

    return render_template(
        'admin.html',
        bachilleratos_400=bachilleratos_400,
        bachilleratos_600=bachilleratos_600,
        total_400=sum(len(v) for v in bachilleratos_400.values()),
        total_600=sum(len(v) for v in bachilleratos_600.values()),
        otros_grupos=otros_grupos,
        usuarios=todos_los_usuarios,
        scope=scope,
        preparatoria_activa=preparatoria,
        preparatorias=preparatorias_lista,
    )


if __name__ == '__main__':
    app.run(debug=True, port=5001)