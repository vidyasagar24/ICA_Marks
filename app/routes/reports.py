from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, jsonify
from flask_login import login_required, current_user
from app.models import (
    db, Faculty, Student, Subject, FacultySubjectMapping, Assessment, Mark, Submission, AcademicYear, Programme, Semester, Section
)
from app.utils.decorators import admin_required
from app.services.analytics_service import (
    get_section_analysis, get_faculty_workload_analysis, get_subject_wise_analysis
)
from app.services.pdf_service import generate_section_marks_pdf, generate_student_grade_card_pdf
from app.services.excel_service import export_marks_sheet

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

# ----------------- ANALYTICS DASHBOARD -----------------
@reports_bp.route('/analytics')
@login_required
def analytics():
    # Admin can view all; Faculty can view their assigned mappings
    mapping_id = request.args.get('mapping_id', type=int)
    subject_id = request.args.get('subject_id', type=int)
    faculty_id = request.args.get('faculty_id', type=int)
    student_id = request.args.get('student_id', type=int)

    if current_user.is_faculty_role:
        faculty_id = current_user.faculty_id

    # Options for dropdowns
    if current_user.is_admin:
        mappings = FacultySubjectMapping.query.filter_by(status='Active').all()
        faculty_list = Faculty.query.filter_by(status='Active').order_by(Faculty.name.asc()).all()
        subjects = Subject.query.filter_by(status='Active').order_by(Subject.subject_code.asc()).all()
    else:
        mappings = FacultySubjectMapping.query.filter_by(faculty_id=current_user.faculty_id, status='Active').all()
        faculty_list = [current_user.faculty_profile] if current_user.faculty_profile else []
        subj_ids = {m.subject_id for m in mappings}
        subjects = Subject.query.filter(Subject.id.in_(subj_ids)).all() if subj_ids else []

    section_data = None
    if mapping_id:
        section_data = get_section_analysis(mapping_id)
    elif mappings:
        mapping_id = mappings[0].id
        section_data = get_section_analysis(mapping_id)

    faculty_data = None
    if faculty_id:
        faculty_data = get_faculty_workload_analysis(faculty_id)

    subject_data = None
    if subject_id:
        subject_data = get_subject_wise_analysis(subject_id)

    student_data = None
    if student_id:
        student = Student.query.get(student_id)
        if student:
            student_data = {'student': student}

    return render_template(
        'reports/analytics.html',
        mappings=mappings,
        faculty_list=faculty_list,
        subjects=subjects,
        selected_mapping_id=mapping_id,
        selected_faculty_id=faculty_id,
        selected_subject_id=subject_id,
        section_data=section_data,
        faculty_data=faculty_data,
        subject_data=subject_data,
        student_data=student_data
    )

# ----------------- CONSOLIDATED SECTION MARKS -----------------
@reports_bp.route('/consolidated')
@login_required
def consolidated():
    mapping_id = request.args.get('mapping_id', type=int)
    
    if current_user.is_admin:
        mappings = FacultySubjectMapping.query.filter_by(status='Active').all()
    else:
        mappings = FacultySubjectMapping.query.filter_by(faculty_id=current_user.faculty_id, status='Active').all()

    if not mapping_id and mappings:
        mapping_id = mappings[0].id

    mapping = FacultySubjectMapping.query.get(mapping_id) if mapping_id else None
    
    students = []
    assessments = []
    marks_map = {}
    if mapping:
        students = Student.query.filter_by(section_id=mapping.section_id, status='Active').order_by(Student.register_number.asc()).all()
        assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()
        for m in Mark.query.filter_by(mapping_id=mapping.id).all():
            marks_map[(m.student_id, m.assessment_id)] = m

    return render_template(
        'reports/consolidated.html',
        mappings=mappings,
        selected_mapping=mapping,
        students=students,
        assessments=assessments,
        marks_map=marks_map
    )

# ----------------- STUDENT REPORT -----------------
@reports_bp.route('/students')
@login_required
def student_report():
    student_id = request.args.get('student_id', type=int)
    search = request.args.get('search', '').strip()

    student = None
    mappings = []
    student_results = []
    if student_id:
        student = Student.query.get(student_id)
        if student:
            mappings = FacultySubjectMapping.query.filter_by(
                academic_year_id=student.academic_year_id,
                programme_id=student.programme_id,
                semester_id=student.current_semester_id,
                section_id=student.section_id,
                status='Active'
            ).all()

            for m in mappings:
                assessments = Assessment.query.filter_by(mapping_id=m.id, is_active=True).all()
                total_scored = 0.0
                total_max = 0.0
                m_details = []
                for ass in assessments:
                    mk = Mark.query.filter_by(student_id=student.id, assessment_id=ass.id, mapping_id=m.id).first()
                    score_str = '-'
                    if mk:
                        if mk.status == 'Absent':
                            score_str = 'AB'
                        elif mk.status == 'Exempted':
                            score_str = 'EX'
                        elif mk.score is not None:
                            score_str = str(mk.score)
                            total_scored += mk.score
                    total_max += ass.max_marks
                    m_details.append({'name': ass.assessment_name, 'max': ass.max_marks, 'score': score_str})

                pct = (total_scored / total_max * 100) if total_max > 0 else 0
                student_results.append({
                    'mapping': m,
                    'assessments': m_details,
                    'total_scored': round(total_scored, 2),
                    'total_max': round(total_max, 2),
                    'percentage': round(pct, 1),
                    'is_pass': pct >= 40
                })

    students_list = []
    if search:
        students_list = Student.query.filter(
            (Student.register_number.ilike(f'%{search}%')) | (Student.student_name.ilike(f'%{search}%'))
        ).limit(25).all()

    return render_template(
        'reports/student_report.html',
        student=student,
        students_list=students_list,
        search=search,
        student_results=student_results
    )

# ----------------- PENDING MARKS REPORT -----------------
@reports_bp.route('/pending-marks')
@login_required
@admin_required
def pending_report():
    """Identifies outstanding faculty submissions across all allocations"""
    mappings = FacultySubjectMapping.query.filter_by(status='Active').all()
    pending_list = []

    for m in mappings:
        sub = Submission.query.filter_by(mapping_id=m.id).order_by(Submission.id.desc()).first()
        status = sub.status if sub else 'Draft'

        total_students = Student.query.filter_by(section_id=m.section_id, status='Active').count()
        total_assessments = Assessment.query.filter_by(mapping_id=m.id, is_active=True).count()
        expected_slots = total_students * total_assessments

        filled_slots = Mark.query.filter_by(mapping_id=m.id).filter(
            (Mark.score.isnot(None)) | (Mark.status.in_(['Absent', 'Exempted']))
        ).count()

        if status in ['Draft', 'Reopened'] or filled_slots < expected_slots:
            completion = (filled_slots / expected_slots * 100) if expected_slots > 0 else 0
            pending_list.append({
                'mapping': m,
                'faculty': m.faculty,
                'subject': m.subject,
                'section': m.section,
                'status': status,
                'badge': sub.badge_class if sub else 'secondary',
                'filled_slots': filled_slots,
                'expected_slots': expected_slots,
                'completion_pct': round(completion, 1)
            })

    return render_template('reports/pending_report.html', pending_list=pending_list)

# ----------------- EXPORT ROUTING -----------------
@reports_bp.route('/export/section/<int:mapping_id>/<format>')
@login_required
def export_section_report(mapping_id, format):
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    if current_user.is_faculty_role and mapping.faculty_id != current_user.faculty_id:
        abort(403)

    if format == 'pdf':
        output = generate_section_marks_pdf(mapping.id)
        filename = f"Report_{mapping.subject.subject_code}_{mapping.section.name}.pdf"
        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/pdf')
    elif format in ['xlsx', 'csv']:
        output = export_marks_sheet(mapping.id, format=format)
        mime = 'text/csv' if format == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = f"Report_{mapping.subject.subject_code}_{mapping.section.name}.{format}"
        return send_file(output, download_name=filename, as_attachment=True, mimetype=mime)
    abort(400)

@reports_bp.route('/export/student/<int:student_id>/pdf')
@login_required
def export_student_pdf(student_id):
    student = Student.query.get_or_404(student_id)
    output = generate_student_grade_card_pdf(student.id)
    filename = f"Grade_Card_{student.register_number}.pdf"
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/pdf')
