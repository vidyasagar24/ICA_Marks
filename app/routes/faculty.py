from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_login import login_required, current_user
from app.models import (
    db, Faculty, Student, FacultySubjectMapping, Assessment, Mark, Submission, MarksAudit
)
from app.utils.decorators import faculty_required
from app.services.audit_service import log_action
from app.services.analytics_service import get_faculty_workload_analysis, get_section_analysis

faculty_bp = Blueprint('faculty', __name__, url_prefix='/faculty')

def check_faculty_allocation(mapping_id):
    """Enforces PRD rule: Faculty shall see ONLY active allocations assigned to their account."""
    if not current_user.faculty_id:
        abort(403)
    mapping = FacultySubjectMapping.query.filter_by(
        id=mapping_id,
        faculty_id=current_user.faculty_id,
        status='Active'
    ).first()
    if not mapping:
        flash('Unauthorized: You are not assigned to this subject or section.', 'danger')
        abort(403)
    return mapping

# ----------------- DASHBOARD -----------------
@faculty_bp.route('/dashboard')
@login_required
@faculty_required
def dashboard():
    if not current_user.faculty_profile:
        flash('Faculty profile not linked to user account. Contact administrator.', 'danger')
        return render_template('faculty/dashboard.html', faculty=None, analysis={})

    analysis = get_faculty_workload_analysis(current_user.faculty_id)
    return render_template('faculty/dashboard.html', faculty=current_user.faculty_profile, analysis=analysis)

# ----------------- MY ALLOCATIONS -----------------
@faculty_bp.route('/my-allocations')
@login_required
@faculty_required
def my_allocations():
    if not current_user.faculty_id:
        return redirect(url_for('faculty.dashboard'))

    mappings = FacultySubjectMapping.query.filter_by(
        faculty_id=current_user.faculty_id,
        status='Active'
    ).order_by(FacultySubjectMapping.academic_year_id.desc(), FacultySubjectMapping.subject_id.asc()).all()

    # Pre-fetch submission statuses
    map_details = []
    for m in mappings:
        sub = Submission.query.filter_by(mapping_id=m.id).order_by(Submission.id.desc()).first()
        status = sub.status if sub else 'Draft'
        badge = sub.badge_class if sub else 'secondary'
        stu_count = Student.query.filter_by(section_id=m.section_id, status='Active').count()
        map_details.append({
            'mapping': m,
            'status': status,
            'badge': badge,
            'student_count': stu_count,
            'submission': sub
        })

    return render_template('faculty/my_allocations.html', allocations=map_details)

# ----------------- MY STUDENTS -----------------
@faculty_bp.route('/allocations/<int:mapping_id>/students')
@login_required
@faculty_required
def view_students(mapping_id):
    mapping = check_faculty_allocation(mapping_id)
    students = Student.query.filter_by(section_id=mapping.section_id, status='Active').order_by(Student.register_number.asc()).all()
    return render_template('faculty/students.html', mapping=mapping, students=students)

# ----------------- MARKS ENTRY -----------------
@faculty_bp.route('/allocations/<int:mapping_id>/marks', methods=['GET', 'POST'])
@login_required
@faculty_required
def marks_entry(mapping_id):
    mapping = check_faculty_allocation(mapping_id)
    
    # Check current submission lock status
    sub = Submission.query.filter_by(mapping_id=mapping.id).order_by(Submission.id.desc()).first()
    is_locked = sub is not None and sub.status in ['Submitted', 'Under Review', 'Approved']

    students = Student.query.filter_by(section_id=mapping.section_id, status='Active').order_by(Student.register_number.asc()).all()
    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()

    # Fetch existing marks
    marks_map = {}
    for m in Mark.query.filter_by(mapping_id=mapping.id).all():
        marks_map[(m.student_id, m.assessment_id)] = m

    if request.method == 'POST':
        if is_locked:
            flash('Marks entry is currently locked because submission is pending review or approved.', 'danger')
            return redirect(url_for('faculty.marks_entry', mapping_id=mapping.id))

        action = request.form.get('action', 'save_draft')

        # Process grid updates
        updated_count = 0
        validation_errors = []

        for stu in students:
            for ass in assessments:
                field_name = f"mark_{stu.id}_{ass.id}"
                raw_val = request.form.get(field_name, '').strip().upper()

                existing_mark = marks_map.get((stu.id, ass.id))

                if raw_val == '' or raw_val == '-':
                    if existing_mark:
                        db.session.delete(existing_mark)
                        updated_count += 1
                    continue

                if raw_val in ['AB', 'ABSENT']:
                    status = 'Absent'
                    score = None
                elif raw_val in ['EX', 'EXEMPT', 'EXEMPTED']:
                    status = 'Exempted'
                    score = None
                else:
                    try:
                        score = float(raw_val)
                        if score < 0 or score > ass.max_marks:
                            validation_errors.append(f"Score for {stu.register_number} in {ass.assessment_name} ({score}) exceeds maximum ({ass.max_marks}).")
                            continue
                        status = 'Present'
                    except ValueError:
                        validation_errors.append(f"Invalid entry '{raw_val}' for {stu.register_number}.")
                        continue

                old_score = existing_mark.score if existing_mark else None
                if existing_mark:
                    existing_mark.score = score
                    existing_mark.status = status
                    existing_mark.updated_at = datetime.utcnow()
                    target_mark = existing_mark
                else:
                    new_mark = Mark(
                        student_id=stu.id,
                        assessment_id=ass.id,
                        mapping_id=mapping.id,
                        score=score,
                        status=status
                    )
                    db.session.add(new_mark)
                    db.session.flush()
                    target_mark = new_mark

                if old_score != score:
                    audit_entry = MarksAudit(
                        mark_id=target_mark.id,
                        old_marks=old_score,
                        new_marks=score,
                        changed_by=current_user.id,
                        reason="Faculty web grid entry"
                    )
                    db.session.add(audit_entry)
                updated_count += 1

        if validation_errors:
            for err in validation_errors[:5]:
                flash(err, 'danger')
            return redirect(url_for('faculty.marks_entry', mapping_id=mapping.id))

        db.session.commit()

        if action == 'submit_to_admin':
            if not sub:
                sub = Submission(mapping_id=mapping.id, submitted_by_id=current_user.id)
                db.session.add(sub)
            sub.status = 'Submitted'
            sub.submission_date = datetime.utcnow()
            db.session.commit()
            log_action('SUBMIT_MARKS', 'Submission', entity_id=sub.id, updated_value={'mapping': mapping.display_title})
            flash('Marks submitted successfully to Administrator for review and approval.', 'success')
            return redirect(url_for('faculty.my_allocations'))

        log_action('SAVE_DRAFT_MARKS', 'FacultySubjectMapping', entity_id=mapping.id, updated_value={'updated_slots': updated_count})
        flash(f'Marks saved as Draft successfully ({updated_count} records saved/updated).', 'success')
        return redirect(url_for('faculty.marks_entry', mapping_id=mapping.id))

    return render_template(
        'faculty/marks_entry.html',
        mapping=mapping,
        students=students,
        assessments=assessments,
        marks_map=marks_map,
        is_locked=is_locked,
        submission=sub
    )

# ----------------- EXCEL TEMPLATE & UPLOAD -----------------
@faculty_bp.route('/allocations/<int:mapping_id>/template')
@login_required
@faculty_required
def download_template(mapping_id):
    from app.services.excel_service import generate_assessment_template
    mapping = check_faculty_allocation(mapping_id)
    output = generate_assessment_template(mapping.id)
    filename = f"Marks_Template_{mapping.subject.subject_code}_{mapping.section.name}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@faculty_bp.route('/allocations/<int:mapping_id>/upload', methods=['GET', 'POST'])
@login_required
@faculty_required
def upload_marks(mapping_id):
    mapping = check_faculty_allocation(mapping_id)

    # Check lock
    sub = Submission.query.filter_by(mapping_id=mapping.id).order_by(Submission.id.desc()).first()
    is_locked = sub is not None and sub.status in ['Submitted', 'Under Review', 'Approved']

    if request.method == 'POST':
        if is_locked:
            flash('Upload rejected: Marks submission is currently locked.', 'danger')
            return redirect(url_for('faculty.upload_marks', mapping_id=mapping.id))

        file = request.files.get('file')
        if not file or not file.filename:
            flash('Please choose an Excel or CSV file to upload.', 'danger')
            return redirect(url_for('faculty.upload_marks', mapping_id=mapping.id))

        from app.services.excel_service import parse_marks_upload
        result = parse_marks_upload(file, mapping.id)

        if not result['success']:
            for err in result['errors']:
                flash(err, 'danger')
            return render_template('faculty/excel_upload.html', mapping=mapping, is_locked=is_locked, submission=sub)

        # Save records as Draft
        saved_count = 0
        for rec in result['records']:
            stu_id = rec['student_id']
            for ass_id, m_data in rec['marks'].items():
                mark = Mark.query.filter_by(student_id=stu_id, assessment_id=ass_id, mapping_id=mapping.id).first()
                old_score = mark.score if mark else None
                if mark:
                    mark.score = m_data['score']
                    mark.status = m_data['status']
                    mark.updated_at = datetime.utcnow()
                    target_mark = mark
                else:
                    mark = Mark(
                        student_id=stu_id,
                        assessment_id=ass_id,
                        mapping_id=mapping.id,
                        score=m_data['score'],
                        status=m_data['status']
                    )
                    db.session.add(mark)
                    db.session.flush()
                    target_mark = mark

                if old_score != m_data['score']:
                    audit_entry = MarksAudit(
                        mark_id=target_mark.id,
                        old_marks=old_score,
                        new_marks=m_data['score'],
                        changed_by=current_user.id,
                        reason="Bulk Excel import"
                    )
                    db.session.add(audit_entry)
                saved_count += 1

        db.session.commit()
        log_action('EXCEL_UPLOAD_MARKS', 'FacultySubjectMapping', entity_id=mapping.id, updated_value={'records_updated': saved_count})
        flash(f"Successfully processed spreadsheet! {saved_count} mark entries saved as draft.", 'success')
        return redirect(url_for('faculty.marks_entry', mapping_id=mapping.id))

    return render_template('faculty/excel_upload.html', mapping=mapping, is_locked=is_locked, submission=sub)

# ----------------- EXPORT MARKS -----------------
@faculty_bp.route('/allocations/<int:mapping_id>/export/<format>')
@login_required
@faculty_required
def export_marks(mapping_id, format):
    mapping = check_faculty_allocation(mapping_id)

    if format == 'pdf':
        from app.services.pdf_service import generate_section_marks_pdf
        output = generate_section_marks_pdf(mapping.id)
        filename = f"Marks_{mapping.subject.subject_code}_{mapping.section.name}.pdf"
        return send_file(output, download_name=filename, as_attachment=True, mimetype='application/pdf')
    elif format in ['xlsx', 'csv']:
        from app.services.excel_service import export_marks_sheet
        output = export_marks_sheet(mapping.id, format=format)
        mime = 'text/csv' if format == 'csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename = f"Marks_{mapping.subject.subject_code}_{mapping.section.name}.{format}"
        return send_file(output, download_name=filename, as_attachment=True, mimetype=mime)
    else:
        abort(400)

# ----------------- SUBMISSION HISTORY -----------------
@faculty_bp.route('/submissions')
@login_required
@faculty_required
def submissions_history():
    mappings = FacultySubjectMapping.query.filter_by(faculty_id=current_user.faculty_id).all()
    map_ids = [m.id for m in mappings]
    subs = Submission.query.filter(Submission.mapping_id.in_(map_ids)).order_by(Submission.updated_at.desc()).all()
    return render_template('faculty/submissions.html', submissions=subs)
