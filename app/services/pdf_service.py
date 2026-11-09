import io
from datetime import datetime
from reportlab.lib.pagesizes import letter, landscape, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from app.models import Student, Assessment, Mark, FacultySubjectMapping

def generate_section_marks_pdf(mapping_id):
    """
    Generate an official section assessment marks report PDF in landscape A4.
    """
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    students = Student.query.filter_by(section_id=mapping.section_id).order_by(Student.register_number.asc()).all()
    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()

    marks_map = {}
    existing_marks = Mark.query.filter_by(mapping_id=mapping.id).all()
    for m in existing_marks:
        marks_map[(m.student_id, m.assessment_id)] = m

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        textColor=colors.HexColor('#1B365D'),
        alignment=1, # Center
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor('#4A5568'),
        alignment=1,
        spaceAfter=12
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#2D3748'),
        leading=13
    )
    meta_bold = ParagraphStyle(
        'MetaBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.HexColor('#1A202C'),
        leading=13
    )
    th_style = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        textColor=colors.white,
        alignment=1
    )
    td_style = ParagraphStyle(
        'TableData',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        alignment=1
    )
    td_left = ParagraphStyle(
        'TableDataLeft',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        alignment=0
    )

    story = []

    # Title & University Header
    story.append(Paragraph("FACULTY ASSESSMENT & STUDENT MARKS MANAGEMENT SYSTEM", title_style))
    story.append(Paragraph(f"Official Consolidated Assessment Report — Academic Year {mapping.academic_year.year_code}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1B365D'), spaceBefore=2, spaceAfter=8))

    # Meta Details Grid
    meta_data = [
        [
            Paragraph(f"<b>Programme:</b> {mapping.programme.name} ({mapping.programme.code})", meta_style),
            Paragraph(f"<b>Semester:</b> {mapping.semester.name}", meta_style),
            Paragraph(f"<b>Section:</b> {mapping.section.name}", meta_style)
        ],
        [
            Paragraph(f"<b>Subject:</b> {mapping.subject.subject_code} - {mapping.subject.subject_name}", meta_style),
            Paragraph(f"<b>Faculty In-Charge:</b> {mapping.faculty.name} ({mapping.faculty.faculty_id_code})", meta_style),
            Paragraph(f"<b>Generated On:</b> {datetime.now().strftime('%d-%b-%Y %H:%M')}", meta_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[280, 280, 200])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Table Header setup
    headers = [
        Paragraph("S#", th_style),
        Paragraph("Reg. Number", th_style),
        Paragraph("Student Name", th_style)
    ]
    col_widths = [28, 75, 140]
    
    # Calculate available remaining width for assessment columns
    remaining_width = 780 - 243
    ass_width = max(remaining_width / (len(assessments) + 3), 45)

    for ass in assessments:
        headers.append(Paragraph(f"{ass.assessment_name}<br/>(Max: {int(ass.max_marks)})", th_style))
        col_widths.append(ass_width)

    headers.append(Paragraph("Total<br/>Scored", th_style))
    col_widths.append(ass_width)
    headers.append(Paragraph("Max<br/>Possible", th_style))
    col_widths.append(ass_width)
    headers.append(Paragraph("Class<br/>%", th_style))
    col_widths.append(ass_width)

    table_data = [headers]

    # Analytics aggregations
    class_totals = []
    ass_totals = {a.id: [] for a in assessments}

    for idx, stu in enumerate(students, 1):
        row = [
            Paragraph(str(idx), td_style),
            Paragraph(stu.register_number, td_style),
            Paragraph(stu.student_name, td_left)
        ]
        stu_scored = 0.0
        stu_max = 0.0
        
        for ass in assessments:
            m = marks_map.get((stu.id, ass.id))
            if m:
                if m.status == 'Absent':
                    row.append(Paragraph("<font color='red'><b>AB</b></font>", td_style))
                    stu_max += ass.max_marks
                elif m.status == 'Exempted':
                    row.append(Paragraph("<font color='blue'><b>EX</b></font>", td_style))
                elif m.score is not None:
                    row.append(Paragraph(f"{m.score:g}", td_style))
                    stu_scored += m.score
                    stu_max += ass.max_marks
                    ass_totals[ass.id].append(m.score)
                else:
                    row.append(Paragraph("-", td_style))
                    stu_max += ass.max_marks
            else:
                row.append(Paragraph("-", td_style))
                stu_max += ass.max_marks

        pct = (stu_scored / stu_max * 100) if stu_max > 0 else 0
        if stu_max > 0:
            class_totals.append(pct)
            
        row.append(Paragraph(f"<b>{stu_scored:g}</b>", td_style))
        row.append(Paragraph(f"{stu_max:g}", td_style))
        pct_color = "green" if pct >= 50 else ("orange" if pct >= 40 else "red")
        row.append(Paragraph(f"<font color='{pct_color}'><b>{pct:.1f}%</b></font>", td_style))

        table_data.append(row)

    # Class Averages Summary Row
    summary_row = [
        Paragraph("", td_style),
        Paragraph("<b>SUMMARY</b>", td_style),
        Paragraph("<b>Class Average</b>", td_left)
    ]
    for ass in assessments:
        scores = ass_totals[ass.id]
        avg = (sum(scores) / len(scores)) if scores else 0
        summary_row.append(Paragraph(f"<b>{avg:.1f}</b>", td_style))

    avg_pct = (sum(class_totals) / len(class_totals)) if class_totals else 0
    summary_row.append(Paragraph("-", td_style))
    summary_row.append(Paragraph("-", td_style))
    summary_row.append(Paragraph(f"<b>{avg_pct:.1f}%</b>", td_style))
    table_data.append(summary_row)

    marks_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    marks_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B365D')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F7FAFC')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(marks_table)
    story.append(Spacer(1, 20))

    # Signature Block
    sig_data = [
        [
            Paragraph("____________________________<br/><b>Faculty Signature</b>", meta_style),
            Paragraph("____________________________<br/><b>HOD / Academic Dean</b>", meta_style),
            Paragraph("____________________________<br/><b>Controller of Examinations</b>", meta_style)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260, 240])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(KeepTogether([sig_table]))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_section_consolidated_pdf(section_id):
    """
    Generate an official consolidated grade sheet PDF for a section across all mapped subjects.
    Page orientation: Landscape A4.
    """
    from app.services.analytics_service import get_section_consolidated_sheet
    data = get_section_consolidated_sheet(section_id)
    section = data['section']
    mappings = data['mappings']
    students_data = data['students_data']
    subject_stats = data['subject_stats']
    overall_stats = data['overall_stats']

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=colors.HexColor('#1B365D'),
        alignment=1,
        spaceAfter=3
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#2E5B88'),
        alignment=1,
        spaceAfter=8
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor('#2D3748'),
        leading=11
    )
    th_style = ParagraphStyle(
        'ThStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        textColor=colors.white,
        alignment=1
    )
    td_style = ParagraphStyle(
        'TdStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        alignment=1
    )
    td_bold = ParagraphStyle(
        'TdBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        alignment=1
    )
    td_left = ParagraphStyle(
        'TdLeft',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        alignment=0
    )

    story = []
    story.append(Paragraph("ACADEMIC ASSESSMENT MANAGEMENT SYSTEM", title_style))
    story.append(Paragraph("OFFICIAL CONSOLIDATED SECTION GRADE SHEET (ALL SUBJECTS)", subtitle_style))

    # Meta Table
    meta_data = [
        [
            Paragraph(f"<b>Programme:</b> {section.programme.name} ({section.programme.code})", meta_style),
            Paragraph(f"<b>Semester:</b> {section.semester.name}", meta_style),
            Paragraph(f"<b>Section:</b> {section.name}", meta_style),
        ],
        [
            Paragraph(f"<b>Academic Year:</b> {section.academic_year.year_code}", meta_style),
            Paragraph(f"<b>Total Students:</b> {overall_stats['total_students']}", meta_style),
            Paragraph(f"<b>Class Pass Rate:</b> {overall_stats['class_pass_rate']}%", meta_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[280, 240, 240])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Table Headers: Tier 1 (Subject groups) & Tier 2 (ICA/TEE/Tot)
    tier1 = [
        Paragraph("#", th_style),
        Paragraph("Register No", th_style),
        Paragraph("Student Name", th_style)
    ]
    tier2 = [
        Paragraph("", th_style),
        Paragraph("", th_style),
        Paragraph("", th_style)
    ]

    for m in mappings:
        tier1.extend([
            Paragraph(f"<b>{m.subject.subject_code}</b>", th_style),
            Paragraph("", th_style),
            Paragraph("", th_style)
        ])
        tier2.extend([
            Paragraph(f"ICA ({int(m.subject.ica_max)})", th_style),
            Paragraph(f"TEE ({int(m.subject.tee_max)})", th_style),
            Paragraph("Total", th_style)
        ])

    tier1.extend([
        Paragraph("Grand Tot", th_style),
        Paragraph("Overall %", th_style),
        Paragraph("Result", th_style)
    ])
    tier2.extend([
        Paragraph("", th_style),
        Paragraph("", th_style),
        Paragraph("", th_style)
    ])

    rows = [tier1, tier2]

    # Data rows
    for idx, s_row in enumerate(students_data, 1):
        r = [
            Paragraph(str(idx), td_style),
            Paragraph(f"<b>{s_row['student'].register_number}</b>", td_style),
            Paragraph(s_row['student'].student_name, td_left)
        ]
        for m in mappings:
            subj_info = s_row['subjects'].get(m.id, {})
            r.append(Paragraph(str(subj_info.get('ica_disp', '-')), td_style))
            r.append(Paragraph(str(subj_info.get('tee_disp', '-')), td_style))
            
            tot_val = subj_info.get('total_score', '-')
            is_pass = subj_info.get('is_pass')
            if is_pass is False:
                r.append(Paragraph(f"<font color='red'><b>{tot_val}</b></font>", td_bold))
            else:
                r.append(Paragraph(f"<b>{tot_val}</b>", td_bold))

        r.append(Paragraph(f"<b>{s_row['grand_total_score']}/{s_row['grand_total_max']}</b>", td_bold))
        r.append(Paragraph(f"<b>{s_row['overall_percentage']}%</b>", td_bold))
        res_color = "green" if s_row['result'] == 'PASS' else ("red" if s_row['result'] == 'FAIL' else "gray")
        r.append(Paragraph(f"<font color='{res_color}'><b>{s_row['result']}</b></font>", td_bold))
        rows.append(r)

    # Class Average Row
    avg_row = [
        Paragraph("<b>Avg</b>", td_bold),
        Paragraph("", td_bold),
        Paragraph("<b>Class Average</b>", td_bold)
    ]
    for m in mappings:
        st = subject_stats.get(m.id, {})
        avg_row.append(Paragraph(str(st.get('avg_ica', '-')), td_style))
        avg_row.append(Paragraph(str(st.get('avg_tee', '-')), td_style))
        avg_row.append(Paragraph(f"<b>{st.get('avg_total', '-')}</b>", td_bold))

    avg_row.append(Paragraph("-", td_style))
    avg_row.append(Paragraph(f"<b>{overall_stats['class_average_pct']}%</b>", td_bold))
    avg_row.append(Paragraph(f"<b>{overall_stats['class_pass_rate']}% Pass</b>", td_bold))
    rows.append(avg_row)

    # Calculate column widths dynamically based on number of subjects
    num_subj = len(mappings)
    fixed_widths = [20, 65, 95]
    end_widths = [55, 45, 45]
    total_avail = 780 - sum(fixed_widths) - sum(end_widths)
    subj_col_width = (total_avail / (num_subj * 3)) if num_subj > 0 else 30
    subj_col_width = max(min(subj_col_width, 45), 25)

    col_widths = fixed_widths + ([subj_col_width] * (num_subj * 3)) + end_widths

    t_style = [
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#1B365D')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
    ]

    # Spanning for Tier 1 subject headers
    col_idx = 3
    for m in mappings:
        t_style.append(('SPAN', (col_idx, 0), (col_idx + 2, 0)))
        col_idx += 3

    # Spanning for fixed columns in header
    t_style.append(('SPAN', (0, 0), (0, 1)))
    t_style.append(('SPAN', (1, 0), (1, 1)))
    t_style.append(('SPAN', (2, 0), (2, 1)))
    t_style.append(('SPAN', (col_idx, 0), (col_idx, 1)))
    t_style.append(('SPAN', (col_idx + 1, 0), (col_idx + 1, 1)))
    t_style.append(('SPAN', (col_idx + 2, 0), (col_idx + 2, 1)))

    table = Table(rows, colWidths=col_widths)
    table.setStyle(TableStyle(t_style))
    story.append(table)
    story.append(Spacer(1, 25))

    # Signatures
    sig_data = [
        [
            Paragraph("____________________________<br/><b>Class Coordinator</b>", meta_style),
            Paragraph("____________________________<br/><b>Head of Department</b>", meta_style),
            Paragraph("____________________________<br/><b>Dean / Controller of Examinations</b>", meta_style),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260, 240])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_student_grade_card_pdf(student_id):
    """
    Generate an individual student academic report PDF in Portrait A4.
    """
    student = Student.query.get_or_404(student_id)
    
    # Fetch all mappings for this student's section
    mappings = FacultySubjectMapping.query.filter_by(
        academic_year_id=student.academic_year_id,
        programme_id=student.programme_id,
        semester_id=student.current_semester_id,
        section_id=student.section_id,
        status='Active'
    ).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CardTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=colors.HexColor('#1B365D'),
        alignment=1,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'CardSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        textColor=colors.HexColor('#4A5568'),
        alignment=1,
        spaceAfter=12
    )
    th_style = ParagraphStyle(
        'CardTH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white,
        alignment=1
    )
    td_style = ParagraphStyle(
        'CardTD',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        alignment=1
    )
    td_left = ParagraphStyle(
        'CardTDLeft',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        alignment=0
    )

    story = []
    story.append(Paragraph("UNIVERSITY ACADEMIC ASSESSMENT RECORD", title_style))
    story.append(Paragraph("STUDENT PERFORMANCE TRANSCRIPT", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1B365D'), spaceAfter=12))

    # Student Info Box
    info_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student.student_name}", td_left),
            Paragraph(f"<b>Register No:</b> {student.register_number}", td_left)
        ],
        [
            Paragraph(f"<b>Programme:</b> {student.programme.name} ({student.programme.code})", td_left),
            Paragraph(f"<b>Academic Year:</b> {student.academic_year.year_code}", td_left)
        ],
        [
            Paragraph(f"<b>Current Semester:</b> {student.current_semester.name}", td_left),
            Paragraph(f"<b>Section:</b> {student.section.name}", td_left)
        ]
    ]
    info_table = Table(info_data, colWidths=[260, 260])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F7FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # Table of subjects & assessment marks
    headers = [
        Paragraph("Code", th_style),
        Paragraph("Subject Name", th_style),
        Paragraph("Faculty", th_style),
        Paragraph("ICA / Tests", th_style),
        Paragraph("TEE", th_style),
        Paragraph("Total", th_style),
        Paragraph("Result", th_style)
    ]
    rows = [headers]

    grand_scored = 0.0
    grand_max = 0.0

    for m in mappings:
        assessments = Assessment.query.filter_by(mapping_id=m.id, is_active=True).all()
        subj_scored = 0.0
        subj_max = 0.0
        ica_scores = []
        tee_score = "-"

        for ass in assessments:
            mark = Mark.query.filter_by(student_id=student.id, assessment_id=ass.id, mapping_id=m.id).first()
            if 'TEE' in ass.assessment_name.upper() or 'TERM END' in ass.assessment_name.upper():
                if mark and mark.score is not None:
                    tee_score = f"{mark.score:g}/{int(ass.max_marks)}"
                    subj_scored += mark.score
                elif mark and mark.status == 'Absent':
                    tee_score = "AB"
                subj_max += ass.max_marks
            else:
                if mark and mark.score is not None:
                    ica_scores.append(f"{ass.assessment_name}: {mark.score:g}/{int(ass.max_marks)}")
                    subj_scored += mark.score
                elif mark and mark.status == 'Absent':
                    ica_scores.append(f"{ass.assessment_name}: AB")
                subj_max += ass.max_marks

        grand_scored += subj_scored
        grand_max += subj_max

        pct = (subj_scored / subj_max * 100) if subj_max > 0 else 0
        status_text = "PASS" if pct >= 40 else "FAIL"
        color = "green" if status_text == "PASS" else "red"

        rows.append([
            Paragraph(m.subject.subject_code, td_style),
            Paragraph(m.subject.subject_name, td_left),
            Paragraph(m.faculty.name, td_left),
            Paragraph("<br/>".join(ica_scores) if ica_scores else "-", td_left),
            Paragraph(str(tee_score), td_style),
            Paragraph(f"<b>{subj_scored:g} / {subj_max:g}</b><br/>({pct:.1f}%)", td_style),
            Paragraph(f"<font color='{color}'><b>{status_text}</b></font>", td_style),
        ])

    table = Table(rows, colWidths=[55, 120, 95, 120, 45, 55, 40])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1B365D')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 15))

    overall_pct = (grand_scored / grand_max * 100) if grand_max > 0 else 0
    story.append(Paragraph(
        f"<b>Cumulative Aggregate:</b> {grand_scored:g} out of {grand_max:g} &nbsp;|&nbsp; <b>Overall Percentage:</b> {overall_pct:.2f}%",
        ParagraphStyle('Agg', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#1B365D'))
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_section_consolidated_pdf(section_id):
    """
    Generate an official consolidated grade sheet PDF for a section across all mapped subjects.
    Page orientation: Landscape A4.
    """
    from app.services.analytics_service import get_section_consolidated_sheet
    data = get_section_consolidated_sheet(section_id)
    section = data['section']
    mappings = data['mappings']
    students_data = data['students_data']
    subject_stats = data['subject_stats']
    overall_stats = data['overall_stats']

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=colors.HexColor('#1B365D'),
        alignment=1,
        spaceAfter=3
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#2E5B88'),
        alignment=1,
        spaceAfter=8
    )
    meta_style = ParagraphStyle(
        'MetaStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        textColor=colors.HexColor('#2D3748'),
        leading=11
    )
    th_style = ParagraphStyle(
        'ThStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        textColor=colors.white,
        alignment=1
    )
    td_style = ParagraphStyle(
        'TdStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        alignment=1
    )
    td_bold = ParagraphStyle(
        'TdBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        alignment=1
    )
    td_left = ParagraphStyle(
        'TdLeft',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        alignment=0
    )

    story = []
    story.append(Paragraph("ACADEMIC ASSESSMENT MANAGEMENT SYSTEM", title_style))
    story.append(Paragraph("OFFICIAL CONSOLIDATED SECTION GRADE SHEET (ALL SUBJECTS)", subtitle_style))

    # Meta Table
    meta_data = [
        [
            Paragraph(f"<b>Programme:</b> {section.programme.name} ({section.programme.code})", meta_style),
            Paragraph(f"<b>Semester:</b> {section.semester.name}", meta_style),
            Paragraph(f"<b>Section:</b> {section.name}", meta_style),
        ],
        [
            Paragraph(f"<b>Academic Year:</b> {section.academic_year.year_code}", meta_style),
            Paragraph(f"<b>Total Students:</b> {overall_stats['total_students']}", meta_style),
            Paragraph(f"<b>Class Pass Rate:</b> {overall_stats['class_pass_rate']}%", meta_style),
        ]
    ]
    meta_table = Table(meta_data, colWidths=[280, 240, 240])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # Table Headers: Tier 1 (Subject groups) & Tier 2 (ICA/TEE/Tot)
    tier1 = [
        Paragraph("#", th_style),
        Paragraph("Register No", th_style),
        Paragraph("Student Name", th_style)
    ]
    tier2 = [
        Paragraph("", th_style),
        Paragraph("", th_style),
        Paragraph("", th_style)
    ]

    for m in mappings:
        tier1.extend([
            Paragraph(f"<b>{m.subject.subject_code}</b>", th_style),
            Paragraph("", th_style),
            Paragraph("", th_style)
        ])
        tier2.extend([
            Paragraph(f"ICA ({int(m.subject.ica_max)})", th_style),
            Paragraph(f"TEE ({int(m.subject.tee_max)})", th_style),
            Paragraph("Total", th_style)
        ])

    tier1.extend([
        Paragraph("Grand Tot", th_style),
        Paragraph("Overall %", th_style),
        Paragraph("Result", th_style)
    ])
    tier2.extend([
        Paragraph("", th_style),
        Paragraph("", th_style),
        Paragraph("", th_style)
    ])

    rows = [tier1, tier2]

    # Data rows
    for idx, s_row in enumerate(students_data, 1):
        r = [
            Paragraph(str(idx), td_style),
            Paragraph(f"<b>{s_row['student'].register_number}</b>", td_style),
            Paragraph(s_row['student'].student_name, td_left)
        ]
        for m in mappings:
            subj_info = s_row['subjects'].get(m.id, {})
            r.append(Paragraph(str(subj_info.get('ica_disp', '-')), td_style))
            r.append(Paragraph(str(subj_info.get('tee_disp', '-')), td_style))
            
            tot_val = subj_info.get('total_score', '-')
            is_pass = subj_info.get('is_pass')
            if is_pass is False:
                r.append(Paragraph(f"<font color='red'><b>{tot_val}</b></font>", td_bold))
            else:
                r.append(Paragraph(f"<b>{tot_val}</b>", td_bold))

        r.append(Paragraph(f"<b>{s_row['grand_total_score']}/{s_row['grand_total_max']}</b>", td_bold))
        r.append(Paragraph(f"<b>{s_row['overall_percentage']}%</b>", td_bold))
        res_color = "green" if s_row['result'] == 'PASS' else ("red" if s_row['result'] == 'FAIL' else "gray")
        r.append(Paragraph(f"<font color='{res_color}'><b>{s_row['result']}</b></font>", td_bold))
        rows.append(r)

    # Class Average Row
    avg_row = [
        Paragraph("<b>Avg</b>", td_bold),
        Paragraph("", td_bold),
        Paragraph("<b>Class Average</b>", td_bold)
    ]
    for m in mappings:
        st = subject_stats.get(m.id, {})
        avg_row.append(Paragraph(str(st.get('avg_ica', '-')), td_style))
        avg_row.append(Paragraph(str(st.get('avg_tee', '-')), td_style))
        avg_row.append(Paragraph(f"<b>{st.get('avg_total', '-')}</b>", td_bold))

    avg_row.append(Paragraph("-", td_style))
    avg_row.append(Paragraph(f"<b>{overall_stats['class_average_pct']}%</b>", td_bold))
    avg_row.append(Paragraph(f"<b>{overall_stats['class_pass_rate']}% Pass</b>", td_bold))
    rows.append(avg_row)

    # Calculate column widths dynamically based on number of subjects
    num_subj = len(mappings)
    fixed_widths = [20, 65, 95]
    end_widths = [55, 45, 45]
    total_avail = 780 - sum(fixed_widths) - sum(end_widths)
    subj_col_width = (total_avail / (num_subj * 3)) if num_subj > 0 else 30
    subj_col_width = max(min(subj_col_width, 45), 25)

    col_widths = fixed_widths + ([subj_col_width] * (num_subj * 3)) + end_widths

    t_style = [
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#1B365D')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
    ]

    # Spanning for Tier 1 subject headers
    col_idx = 3
    for m in mappings:
        t_style.append(('SPAN', (col_idx, 0), (col_idx + 2, 0)))
        col_idx += 3

    # Spanning for fixed columns in header
    t_style.append(('SPAN', (0, 0), (0, 1)))
    t_style.append(('SPAN', (1, 0), (1, 1)))
    t_style.append(('SPAN', (2, 0), (2, 1)))
    t_style.append(('SPAN', (col_idx, 0), (col_idx, 1)))
    t_style.append(('SPAN', (col_idx + 1, 0), (col_idx + 1, 1)))
    t_style.append(('SPAN', (col_idx + 2, 0), (col_idx + 2, 1)))

    table = Table(rows, colWidths=col_widths)
    table.setStyle(TableStyle(t_style))
    story.append(table)
    story.append(Spacer(1, 25))

    # Signatures
    sig_data = [
        [
            Paragraph("____________________________<br/><b>Class Coordinator</b>", meta_style),
            Paragraph("____________________________<br/><b>Head of Department</b>", meta_style),
            Paragraph("____________________________<br/><b>Dean / Controller of Examinations</b>", meta_style),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260, 240])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer
