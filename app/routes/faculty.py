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

    from app.services.assessment_service import split_ica_assessments
    _, explicit_ica_ass, tee_ass = split_ica_assessments(assessments)

    return render_template(
        'faculty/marks_entry.html',
        mapping=mapping,
        students=students,
        assessments=assessments,
        marks_map=marks_map,
        is_locked=is_locked,
        submission=sub,
        has_explicit_ica=(explicit_ica_ass is not None),
        tee_ass=tee_ass
    )


# ----------------- FACULTY ICA DISTRIBUTION CONFIG -----------------
@faculty_bp.route('/allocations/<int:mapping_id>/ica-distribution', methods=['GET', 'POST'])
@login_required
@faculty_required
def ica_distribution(mapping_id):
    from app.services.assessment_service import (
        get_ica_presets, save_faculty_ica_distribution, split_ica_assessments
    )
    mapping = check_faculty_allocation(mapping_id)
    sub = Submission.query.filter_by(mapping_id=mapping.id).order_by(Submission.id.desc()).first()
    is_locked = sub is not None and sub.status in ['Submitted', 'Under Review', 'Approved']

    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()
    internals, explicit_ica, tee_ass = split_ica_assessments(assessments)
    ica_components = internals + ([explicit_ica] if explicit_ica else [])
    presets = get_ica_presets(mapping.subject.ica_max)

    if request.method == 'POST':
        if is_locked:
            flash('ICA configuration cannot be changed while submission is locked/approved.', 'danger')
            return redirect(url_for('faculty.ica_distribution', mapping_id=mapping.id))

        comp_ids = request.form.getlist('component_id[]')
        comp_names = request.form.getlist('component_name[]')
        comp_types = request.form.getlist('component_type[]')
        comp_maxes = request.form.getlist('component_max[]')
        include_tee = bool(request.form.get('include_tee'))
        tee_max = request.form.get('tee_max', type=float)

        components = []
        for idx, name in enumerate(comp_names):
            clean_name = name.strip()
            if not clean_name:
                continue
            cid = comp_ids[idx].strip() if idx < len(comp_ids) and comp_ids[idx].strip() else None
            ctype = comp_types[idx].strip() if idx < len(comp_types) else 'Test'
            try:
                cmax = float(comp_maxes[idx]) if idx < len(comp_maxes) else 0.0
            except (ValueError, TypeError):
                cmax = 0.0
            components.append({'id': cid, 'name': clean_name, 'type': ctype, 'max_marks': cmax})

        if not components:
            flash('Please configure at least one ICA assessment component.', 'danger')
            return redirect(url_for('faculty.ica_distribution', mapping_id=mapping.id))

        try:
            save_faculty_ica_distribution(mapping, components, include_tee=include_tee, tee_max=tee_max)
            log_action('CONFIGURE_ICA_DISTRIBUTION', 'FacultySubjectMapping', entity_id=mapping.id, updated_value={
                'components': [f"{c['name']} ({c['max_marks']})" for c in components],
                'include_tee': include_tee
            })
            flash(f"ICA distribution updated successfully ({len(components)} components configured).", 'success')
            return redirect(url_for('faculty.marks_entry', mapping_id=mapping.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Could not save ICA distribution: {str(e)}", 'danger')
            return redirect(url_for('faculty.ica_distribution', mapping_id=mapping.id))

    return render_template(
        'faculty/ica_distribution.html',
        mapping=mapping,
        ica_components=ica_components,
        tee_ass=tee_ass,
        presets=presets,
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
    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()

    if request.method == 'POST':
        if is_locked:
            flash('Upload rejected: Marks submission is currently locked.', 'danger')
            return redirect(url_for('faculty.upload_marks', mapping_id=mapping.id))

        file = request.files.get('file')
        if not file or not file.filename:
            flash('Please choose an Excel or CSV file to upload.', 'danger')
            return redirect(url_for('faculty.upload_marks', mapping_id=mapping.id))

        auto_create = bool(request.form.get('auto_create_components'))
        from app.services.excel_service import parse_marks_upload
        result = parse_marks_upload(file, mapping.id, auto_create=auto_create)

        if not result['success']:
            for err in result['errors'][:10]:
                flash(err, 'danger')
            return render_template(
                'faculty/excel_upload.html', mapping=mapping, assessments=assessments, is_locked=is_locked, submission=sub
            )

        # Save records as Draft
        try:
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
            for warn in result.get('warnings', []):
                flash(warn, 'info')
            log_action('EXCEL_UPLOAD_MARKS', 'FacultySubjectMapping', entity_id=mapping.id, updated_value={'records_updated': saved_count})
            if saved_count > 0:
                cols_str = ', '.join(result.get('assessments_updated', []))
                flash(f"Successfully imported {saved_count} mark entries ({cols_str}) into Draft.", 'success')
            else:
                flash("Spreadsheet matched, but all score cells were blank (0 marks updated).", 'warning')
            return redirect(url_for('faculty.marks_entry', mapping_id=mapping.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error saving imported marks: {str(e)}", 'danger')
            return redirect(url_for('faculty.upload_marks', mapping_id=mapping.id))

    return render_template(
        'faculty/excel_upload.html', mapping=mapping, assessments=assessments, is_locked=is_locked, submission=sub
    )

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
