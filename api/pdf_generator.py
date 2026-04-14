"""
pdf_generator.py — Trayector-IA
Genera el reporte PDF de resultados vocacionales con el mismo estilo visual
del sitio web (colores, tipografía, estructura de tarjetas).
"""

import os
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.pdfgen import canvas as rl_canvas

# ── Paleta de colores del design system ──────────────────────────────────────
C_PRIMARY   = HexColor('#4062BB')
C_ACCENT    = HexColor('#2c46a0')
C_SUCCESS   = HexColor('#1cb87e')
C_TEXT      = HexColor('#121413')
C_MUTED     = HexColor('#5a5f6a')
C_BG_CARD   = HexColor('#ffffff')
C_BG_SUBTLE = HexColor('#f4f4f6')
C_BORDER    = HexColor('#dedede')
C_PRIMARY_DIM = HexColor('#EEF2FF')

PAGE_W, PAGE_H = A4          # 595.28 × 841.89 pts
MARGIN = 2.0 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

# ── Meses en español ──────────────────────────────────────────────────────────
_MESES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre',
}


def _fecha_es() -> str:
    hoy = datetime.now()
    return f"{hoy.day} de {_MESES[hoy.month]} de {hoy.year}"


# ── Estilos de párrafo ────────────────────────────────────────────────────────
def _build_styles() -> dict:
    return {
        'page_title': ParagraphStyle(
            'page_title',
            fontName='Helvetica-Bold',
            fontSize=14,
            textColor=C_TEXT,
            spaceAfter=3,
            leading=18,
        ),
        'page_subtitle': ParagraphStyle(
            'page_subtitle',
            fontName='Helvetica',
            fontSize=8.5,
            textColor=C_SUCCESS,
            spaceAfter=14,
        ),
        'mono_label': ParagraphStyle(
            'mono_label',
            fontName='Helvetica',
            fontSize=6.5,
            textColor=C_MUTED,
            spaceAfter=5,
            leading=10,
            charSpace=1.5,
        ),
        'career_name': ParagraphStyle(
            'career_name',
            fontName='Helvetica-Bold',
            fontSize=22,
            textColor=C_PRIMARY,
            spaceBefore=2,
            spaceAfter=10,
            leading=28,
        ),
        'uv_available': ParagraphStyle(
            'uv_available',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            textColor=C_SUCCESS,
            spaceAfter=8,
        ),
        'uv_external': ParagraphStyle(
            'uv_external',
            fontName='Helvetica',
            fontSize=8.5,
            textColor=C_MUTED,
            spaceAfter=8,
        ),
        'badge_text': ParagraphStyle(
            'badge_text',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            textColor=C_PRIMARY,
            leading=11,
        ),
        'section_title': ParagraphStyle(
            'section_title',
            fontName='Helvetica-Bold',
            fontSize=10,
            textColor=C_MUTED,
            spaceAfter=8,
        ),
        'explanation': ParagraphStyle(
            'explanation',
            fontName='Helvetica',
            fontSize=9.5,
            textColor=C_MUTED,
            leading=16,
        ),
        'body': ParagraphStyle(
            'body',
            fontName='Helvetica',
            fontSize=9,
            textColor=C_TEXT,
            leading=14,
            spaceAfter=4,
        ),
        'secondary_label': ParagraphStyle(
            'secondary_label',
            fontName='Helvetica',
            fontSize=6.5,
            textColor=C_MUTED,
            spaceAfter=3,
            charSpace=1.5,
        ),
        'secondary_career': ParagraphStyle(
            'secondary_career',
            fontName='Helvetica-Bold',
            fontSize=10.5,
            textColor=C_PRIMARY,
            leading=14,
            spaceAfter=4,
        ),
        'uv_tag': ParagraphStyle(
            'uv_tag',
            fontName='Helvetica',
            fontSize=7.5,
            textColor=C_SUCCESS,
        ),
        'ext_tag': ParagraphStyle(
            'ext_tag',
            fontName='Helvetica',
            fontSize=7.5,
            textColor=C_MUTED,
        ),
        'date_right': ParagraphStyle(
            'date_right',
            fontName='Helvetica',
            fontSize=8,
            textColor=C_MUTED,
            alignment=TA_RIGHT,
        ),
        'footer': ParagraphStyle(
            'footer',
            fontName='Helvetica',
            fontSize=7,
            textColor=C_MUTED,
            alignment=TA_CENTER,
            leading=11,
        ),
        'profile_label': ParagraphStyle(
            'profile_label',
            fontName='Helvetica-Bold',
            fontSize=7,
            textColor=C_PRIMARY,
            charSpace=1,
            leading=11,
        ),
        'profile_body': ParagraphStyle(
            'profile_body',
            fontName='Helvetica',
            fontSize=8.5,
            textColor=C_MUTED,
            leading=13,
        ),
    }


# ── Canvas callbacks (header/footer de página) ────────────────────────────────
def _page_footer(canvas_obj, doc):
    """Dibuja el pie de página con número de página."""
    canvas_obj.saveState()
    canvas_obj.setFont('Helvetica', 7)
    canvas_obj.setFillColor(C_MUTED)
    footer_y = MARGIN * 0.55
    canvas_obj.drawCentredString(
        PAGE_W / 2,
        footer_y,
        'Trayector-IA  ·  Universidad Veracruzana — Facultad de Negocios y Tecnologías, Campus Ixtac',
    )
    canvas_obj.setFillColor(C_BORDER)
    canvas_obj.drawRightString(
        PAGE_W - MARGIN,
        footer_y,
        f'Pág. {doc.page}',
    )
    canvas_obj.restoreState()


# ── Logo como texto con estilo (fallback robusto) ─────────────────────────────
def _build_logo_paragraph() -> Paragraph:
    """
    Intenta renderizar el SVG del logo vía svglib.
    Si no está disponible, genera el logo como texto estilizado.
    """
    logo_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', 'static', 'img', 'logo-trayectoria.svg')
    )
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPDF
        from reportlab.platypus import Flowable

        drawing = svg2rlg(logo_path)
        if drawing and drawing.width > 0:
            target_h = 28.0
            scale = target_h / drawing.height
            drawing.width  = drawing.width * scale
            drawing.height = target_h
            drawing.transform = (scale, 0, 0, scale, 0, 0)

            class _SvgFlowable(Flowable):
                def __init__(self, drw):
                    super().__init__()
                    self.drw = drw
                    self.width  = drw.width
                    self.height = drw.height

                def draw(self):
                    renderPDF.draw(self.drw, self.canv, 0, 0)

            return _SvgFlowable(drawing)
    except Exception:
        pass

    # Fallback: texto estilizado "Trayector-IA"
    return Paragraph(
        '<font name="Helvetica-Bold" size="18" color="#4062BB">Trayector</font>'
        '<font name="Helvetica-Bold" size="18" color="#121413">-IA</font>',
        ParagraphStyle('logo_text', fontName='Helvetica-Bold', fontSize=18),
    )


# ── Tarjetas de otras opciones ────────────────────────────────────────────────
def _build_other_careers_section(otras: list, styles: dict) -> list:
    """Construye la grilla de tarjetas de carreras secundarias (3 por fila)."""
    elements = []
    if not otras:
        return elements

    elements.append(HRFlowable(width='100%', thickness=1, color=C_BORDER, spaceAfter=12))
    elements.append(Paragraph('TAMBIÉN PODRÍAN INTERESARTE', styles['section_title']))

    col_w = CONTENT_W / 3

    # Agrupar en filas de 3
    rows = [otras[i:i + 3] for i in range(0, len(otras), 3)]

    for row_items in rows:
        # Rellenar con celdas vacías si la fila incompleta
        while len(row_items) < 3:
            row_items.append(None)

        cells = []
        for op in row_items:
            if op is None:
                cells.append('')
                continue
            nombre = op.get('Carrera', '—')
            es_uv  = op.get('es_uv', False)
            tag_para = Paragraph(
                '✓  Sede UV' if es_uv else 'Opción externa',
                styles['uv_tag'] if es_uv else styles['ext_tag'],
            )
            cells.append([
                Paragraph('OPCIÓN ADICIONAL', styles['secondary_label']),
                Paragraph(nombre, styles['secondary_career']),
                tag_para,
            ])

        t = Table([cells], colWidths=[col_w] * 3)
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), C_BG_CARD),
            ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
            ('INNERGRID',     (0, 0), (-1, -1), 0.5, C_BORDER),
            ('LINEABOVE',     (0, 0), (-1,  0), 2.5, C_PRIMARY),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 14),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 14),
            ('TOPPADDING',    (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 6))

    return elements


# ── Sección de perfiles académicos ────────────────────────────────────────────
def _build_profiles_section(resultado: dict, styles: dict) -> list:
    perfil_ingreso = resultado.get('perfil_ingreso', '').strip()
    perfil_egreso  = resultado.get('perfil_egreso', '').strip()

    skip_values = {'No disponible', 'Consulta el portal oficial.', ''}
    if perfil_ingreso in skip_values and perfil_egreso in skip_values:
        return []

    elements = [
        Spacer(1, 6),
        HRFlowable(width='100%', thickness=1, color=C_BORDER, spaceAfter=12),
        Paragraph('PERFILES ACADÉMICOS', styles['section_title']),
    ]

    label_w   = 3.2 * cm
    content_w = CONTENT_W - label_w

    profile_pairs = [
        ('PERFIL DE INGRESO', perfil_ingreso),
        ('PERFIL DE EGRESO',  perfil_egreso),
    ]

    for label, text in profile_pairs:
        if not text or text in skip_values:
            continue
        row = [
            Paragraph(label, styles['profile_label']),
            Paragraph(text, styles['profile_body']),
        ]
        t = Table([row], colWidths=[label_w, content_w])
        t.setStyle(TableStyle([
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW',     (0, 0), (-1, -1), 0.4, C_BORDER),
        ]))
        elements.append(t)

    return elements


# ── Función principal ─────────────────────────────────────────────────────────
def generate_results_pdf(resultado: dict) -> bytes:
    """
    Genera el reporte PDF de orientación vocacional.
    Recibe el dict `resultado` producido por OrientadorAPI.obtener_resultado().
    Devuelve los bytes del PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN + 0.8 * cm,   # espacio para el pie de página
        title='Reporte Vocacional — Trayector-IA',
        author='Trayector-IA · Universidad Veracruzana',
        subject='Orientación Vocacional con Inteligencia Artificial',
    )

    styles = _build_styles()
    story  = []

    # ── 1. ENCABEZADO: logo + fecha ───────────────────────────────────────────
    logo_flowable = _build_logo_paragraph()
    date_para = Paragraph(f'Generado el {_fecha_es()}', styles['date_right'])

    header_tbl = Table(
        [[logo_flowable, date_para]],
        colWidths=[CONTENT_W - 130, 130],
    )
    header_tbl.setStyle(TableStyle([
        ('VALIGN',  (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',   (1, 0), ( 1,  0), 'RIGHT'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width='100%', thickness=2.5, color=C_PRIMARY, spaceAfter=8))

    # ── 2. TÍTULO DE PÁGINA ───────────────────────────────────────────────────
    story.append(Paragraph('REPORTE DE ORIENTACIÓN VOCACIONAL', styles['page_title']))
    story.append(Paragraph(
        f'Análisis completado  ·  {resultado.get("total_respuestas", 10)} respuestas procesadas',
        styles['page_subtitle'],
    ))

    # ── 3. TARJETA PRINCIPAL ──────────────────────────────────────────────────
    card_elements = []

    # Label mono
    card_elements.append(Paragraph('CARRERA RECOMENDADA', styles['mono_label']))

    # Nombre de la carrera
    card_elements.append(Paragraph(
        resultado.get('carrera_recomendada', '—'),
        styles['career_name'],
    ))

    # Disponibilidad UV
    if resultado.get('es_uv'):
        card_elements.append(Paragraph(
            '✓  Disponible en Universidad Veracruzana — Región Orizaba-Córdoba',
            styles['uv_available'],
        ))
    else:
        card_elements.append(Paragraph(
            'ℹ  Esta carrera no se encuentra actualmente en tu región, '
            'pero es la que más se alinea con tu perfil global.',
            styles['uv_external'],
        ))

    # Badges: Facultad / Municipio / Modalidad
    badges = []
    for field, label in [
        ('facultad',  'Facultad'),
        ('municipio', 'Sede'),
        ('modalidad', 'Modalidad'),
    ]:
        val = resultado.get(field, '')
        if val and val not in ('No disponible', ''):
            badges.append((label, val))

    if badges:
        badge_col_w = CONTENT_W / len(badges)
        badge_data  = [[
            Paragraph(f'<b>{lbl}</b>: {val}', styles['badge_text'])
            for lbl, val in badges
        ]]
        badge_tbl = Table(badge_data, colWidths=[badge_col_w] * len(badges))
        badge_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), C_PRIMARY_DIM),
            ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
            ('INNERGRID',     (0, 0), (-1, -1), 0.5, C_BORDER),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        card_elements.append(badge_tbl)
        card_elements.append(Spacer(1, 14))

    # Sección "¿Por qué esta carrera?"
    card_elements.append(Paragraph('¿POR QUÉ ESTA CARRERA?', styles['mono_label']))

    explanation_para = Paragraph(
        resultado.get('explicacion', ''),
        styles['explanation'],
    )
    exp_tbl = Table([[explanation_para]], colWidths=[CONTENT_W])
    exp_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_BG_SUBTLE),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_BORDER),
        ('LINEBEFORE',    (0, 0), ( 0, -1), 3,   C_PRIMARY),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 14),
        ('TOPPADDING',    (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    card_elements.append(exp_tbl)

    # Envolver la tarjeta principal en un recuadro con borde superior degradado
    main_card_tbl = Table([[card_elements]], colWidths=[CONTENT_W])
    main_card_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_BG_CARD),
        ('BOX',           (0, 0), (-1, -1), 0.8, C_BORDER),
        ('LINEABOVE',     (0, 0), (-1,  0), 3,   C_PRIMARY),
        ('LEFTPADDING',   (0, 0), (-1, -1), 20),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 20),
        ('TOPPADDING',    (0, 0), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(KeepTogether(main_card_tbl))
    story.append(Spacer(1, 20))

    # ── 4. OTRAS OPCIONES ─────────────────────────────────────────────────────
    story.extend(_build_other_careers_section(
        resultado.get('otras_opciones', []), styles
    ))

    # ── 5. PERFILES ACADÉMICOS ────────────────────────────────────────────────
    story.extend(_build_profiles_section(resultado, styles))

    # ── 6. PIE DE CONTENIDO ───────────────────────────────────────────────────
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width='100%', thickness=1, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph(
        'Este reporte fue generado automáticamente por Trayector-IA mediante análisis NLP + TF-IDF + KNN.<br/>'
        'Los resultados son orientativos y no sustituyen la asesoría de un orientador vocacional certificado.',
        styles['footer'],
    ))

    # ── Construir PDF ─────────────────────────────────────────────────────────
    doc.build(
        story,
        onFirstPage=_page_footer,
        onLaterPages=_page_footer,
    )

    return buffer.getvalue()
