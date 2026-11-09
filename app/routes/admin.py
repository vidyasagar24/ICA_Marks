from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
import pandas as pd
from app.models import (
    db, User, Faculty, Student, StudentEnrollment, AcademicYear, Programme, Semester, Section,
    Subject, FacultySubjectMapping, Assessment, Mark, Submission, AuditLog, MarksAudit
)
from app.utils.decorators import admin_required
from app.services.audit_service import log_action
from app.services.analytics_service import get_admin_dashboard_kpis, get_faculty_workload_analysis
from app.services.excel_service import generate_student_import_template

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ----------------- DASHBOARD -----------------
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    year_id = request.args.get('academic_year_id', type=int)
    prog_id = request.args.get('programme_id', type=int)
    sem_id = request.args.get('semester_id', type=int)

    filters = {
        'academic_year_id': year_id,
        'programme_id': prog_id,
        'semester_id': sem_id
    }
    kpis = get_admin_dashboard_kpis(filters)

    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    programmes = Programme.query.filter_by(is_active=True).all()
    semesters = Semester.query.order_by(Semester.number.asc()).all()

    # Recent submissions awaiting review
    pending_reviews = Submission.query.filter(Submission.status.in_(['Submitted', 'Under Review'])).order_by(Submission.submission_date.desc()).limit(8).all()

    # Recent Audit Logs
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()

    return render_template(
        'admin/dashboard.html',
        kpis=kpis,
        filters=filters,
        academic_years=academic_years,
        programmes=programmes,
        semesters=semesters,
        pending_reviews=pending_reviews,
        recent_logs=recent_logs
    )

# ----------------- ACADEMIC YEARS -----------------
@admin_bp.route('/academic-years', methods=['GET', 'POST'])
@login_required
@admin_required
def academic_years():
    if request.method == 'POST':
        year_code = request.form.get('year_code', '').strip()
        start_date_str = request.form.get('start_date', '')
        end_date_str = request.form.get('end_date', '')
        status = request.form.get('status', 'Active')

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'danger')
            return redirect(url_for('admin.academic_years'))

        existing = AcademicYear.query.filter_by(year_code=year_code).first()
        if existing:
            flash(f"Academic Year '{year_code}' already exists.", 'warning')
        else:
            year = AcademicYear(year_code=year_code, start_date=start_date, end_date=end_date, status=status)
            db.session.add(year)
            db.session.commit()
            log_action('CREATE_ACADEMIC_YEAR', 'AcademicYear', entity_id=year.id, updated_value={'year_code': year_code, 'status': status})
            flash(f"Academic Year '{year_code}' created successfully.", 'success')
        return redirect(url_for('admin.academic_years'))

    years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    return render_template('admin/academic_years.html', years=years)

@admin_bp.route('/academic-years/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_academic_year(id):
    year = AcademicYear.query.get_or_404(id)
    prev = {'year_code': year.year_code, 'status': year.status}
    year.year_code = request.form.get('year_code', year.year_code).strip()
    year.status = request.form.get('status', year.status)
    db.session.commit()
    log_action('UPDATE_ACADEMIC_YEAR', 'AcademicYear', entity_id=year.id, previous_value=prev, updated_value={'year_code': year.year_code, 'status': year.status})
    flash(f"Academic Year '{year.year_code}' updated.", 'success')
    return redirect(url_for('admin.academic_years'))

# ----------------- PROGRAMMES -----------------
@admin_bp.route('/programmes', methods=['GET', 'POST'])
@login_required
@admin_required
def programmes():
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if Programme.query.filter_by(code=code).first():
            flash(f"Programme code '{code}' already exists.", 'warning')
        else:
            prog = Programme(code=code, name=name, description=description)
            db.session.add(prog)
            db.session.commit()
            log_action('CREATE_PROGRAMME', 'Programme', entity_id=prog.id, updated_value={'code': code, 'name': name})
            flash(f"Programme '{code} - {name}' added successfully.", 'success')
        return redirect(url_for('admin.programmes'))

    progs = Programme.query.order_by(Programme.code.asc()).all()
    return render_template('admin/programmes.html', programmes=progs)

@admin_bp.route('/programmes/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_programme(id):
    prog = Programme.query.get_or_404(id)
    prev = {'name': prog.name, 'is_active': prog.is_active}
    prog.name = request.form.get('name', prog.name).strip()
    prog.description = request.form.get('description', prog.description).strip()
    prog.is_active = bool(request.form.get('is_active'))
    db.session.commit()
    log_action('UPDATE_PROGRAMME', 'Programme', entity_id=prog.id, previous_value=prev, updated_value={'name': prog.name, 'is_active': prog.is_active})
    flash(f"Programme '{prog.code}' updated.", 'success')
    return redirect(url_for('admin.programmes'))

# ----------------- SEMESTERS & SECTIONS -----------------
@admin_bp.route('/semesters')
@login_required
@admin_required
def semesters():
    sems = Semester.query.order_by(Semester.number.asc()).all()
    return render_template('admin/semesters.html', semesters=sems)

@admin_bp.route('/sections', methods=['GET', 'POST'])
@login_required
@admin_required
def sections():
    if request.method == 'POST':
        programme_id = request.form.get('programme_id', type=int)
        academic_year_id = request.form.get('academic_year_id', type=int)
        semester_id = request.form.get('semester_id', type=int)
        name = request.form.get('name', '').strip().upper()

        existing = Section.query.filter_by(
            programme_id=programme_id,
            academic_year_id=academic_year_id,
            semester_id=semester_id,
            name=name
        ).first()

        if existing:
            flash(f"Section '{name}' already exists for this Programme and Semester.", 'warning')
        else:
            sec = Section(
                programme_id=programme_id,
                academic_year_id=academic_year_id,
                semester_id=semester_id,
                name=name
            )
            db.session.add(sec)
            db.session.commit()
            log_action('CREATE_SECTION', 'Section', entity_id=sec.id, updated_value={'section': sec.display_name})
            flash(f"Section '{name}' created successfully.", 'success')
        return redirect(url_for('admin.sections'))

    sections_list = Section.query.join(AcademicYear).order_by(AcademicYear.start_date.desc(), Section.name.asc()).all()
    programmes = Programme.query.filter_by(is_active=True).all()
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    semesters = Semester.query.order_by(Semester.number.asc()).all()

    return render_template(
        'admin/sections.html',
        sections=sections_list,
        programmes=programmes,
        academic_years=years,
        semesters=semesters
    )

# ----------------- FACULTY MANAGEMENT -----------------
@admin_bp.route('/faculty', methods=['GET', 'POST'])
@login_required
@admin_required
def faculty():
    if request.method == 'POST':
        fac_code = request.form.get('faculty_id_code', '').strip().upper()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        dept = request.form.get('department', '').strip()
        designation = request.form.get('designation', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip() or 'Faculty@123'

        if Faculty.query.filter((Faculty.faculty_id_code == fac_code) | (Faculty.email == email)).first():
            flash('Faculty Code or Email already exists.', 'danger')
            return redirect(url_for('admin.faculty'))

        if User.query.filter_by(username=username).first():
            flash(f"Username '{username}' is already in use.", 'danger')
            return redirect(url_for('admin.faculty'))

        fac = Faculty(
            faculty_id_code=fac_code,
            name=name,
            email=email,
            department=dept,
            designation=designation,
            status='Active'
        )
        db.session.add(fac)
        db.session.flush()

        user = User(
            username=username,
            role='faculty',
            faculty_id=fac.id,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        log_action('CREATE_FACULTY', 'Faculty', entity_id=fac.id, updated_value={'code': fac_code, 'name': name, 'user': username})
        flash(f"Faculty '{name}' and login account '{username}' created successfully.", 'success')
        return redirect(url_for('admin.faculty'))

    faculty_list = Faculty.query.order_by(Faculty.name.asc()).all()
    # Compute workload summaries
    workloads = {f.id: get_faculty_workload_analysis(f.id) for f in faculty_list}

    return render_template('admin/faculty.html', faculty_list=faculty_list, workloads=workloads)

@admin_bp.route('/faculty/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_faculty(id):
    fac = Faculty.query.get_or_404(id)
    prev = {'name': fac.name, 'email': fac.email, 'status': fac.status}
    fac.name = request.form.get('name', fac.name).strip()
    fac.email = request.form.get('email', fac.email).strip().lower()
    fac.department = request.form.get('department', fac.department).strip()
    fac.designation = request.form.get('designation', fac.designation).strip()
    fac.status = request.form.get('status', fac.status)

    if fac.user_account:
        fac.user_account.is_active = (fac.status == 'Active')
        new_pwd = request.form.get('new_password', '').strip()
        if new_pwd:
            fac.user_account.set_password(new_pwd)
            flash('Password reset for faculty.', 'info')

    db.session.commit()
    log_action('UPDATE_FACULTY', 'Faculty', entity_id=fac.id, previous_value=prev, updated_value={'name': fac.name, 'status': fac.status})
    flash(f"Faculty '{fac.name}' updated.", 'success')
    return redirect(url_for('admin.faculty'))

# ----------------- SUBJECT MANAGEMENT -----------------
@admin_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def subjects():
    if request.method == 'POST':
        code = request.form.get('subject_code', '').strip().upper()
        name = request.form.get('subject_name', '').strip()
        programme_id = request.form.get('programme_id', type=int)
        semester_id = request.form.get('semester_id', type=int)
        credits = request.form.get('credits', 3, type=int)
        ica_max = request.form.get('ica_max', 50.0, type=float)
        tee_max = request.form.get('tee_max', 100.0, type=float)

        existing = Subject.query.filter_by(subject_code=code, programme_id=programme_id, semester_id=semester_id).first()
        if existing:
            flash(f"Subject '{code}' already exists for this Programme and Semester.", 'warning')
        else:
            subj = Subject(
                subject_code=code,
                subject_name=name,
                programme_id=programme_id,
                semester_id=semester_id,
                credits=credits,
                ica_max=ica_max,
                tee_max=tee_max,
                status='Active'
            )
            db.session.add(subj)
            db.session.commit()
            log_action('CREATE_SUBJECT', 'Subject', entity_id=subj.id, updated_value={'code': code, 'name': name})
            flash(f"Subject '{code} - {name}' created.", 'success')
        return redirect(url_for('admin.subjects'))

    subjects_list = Subject.query.order_by(Subject.programme_id.asc(), Subject.semester_id.asc(), Subject.subject_code.asc()).all()
    programmes = Programme.query.filter_by(is_active=True).all()
    semesters = Semester.query.order_by(Semester.number.asc()).all()

    return render_template('admin/subjects.html', subjects=subjects_list, programmes=programmes, semesters=semesters)

@admin_bp.route('/subjects/<int:id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_subject(id):
    subj = Subject.query.get_or_404(id)
    prev = {'name': subj.subject_name, 'credits': subj.credits, 'ica_max': subj.ica_max, 'tee_max': subj.tee_max, 'status': subj.status}
    subj.subject_name = request.form.get('subject_name', subj.subject_name).strip()
    subj.credits = request.form.get('credits', subj.credits, type=int)
    subj.ica_max = request.form.get('ica_max', subj.ica_max, type=float)
    subj.tee_max = request.form.get('tee_max', subj.tee_max, type=float)
    subj.status = request.form.get('status', subj.status)
    db.session.commit()
    log_action('UPDATE_SUBJECT', 'Subject', entity_id=subj.id, previous_value=prev, updated_value={'name': subj.subject_name, 'status': subj.status})
    flash(f"Subject '{subj.subject_code}' updated.", 'success')
    return redirect(url_for('admin.subjects'))

# ----------------- FACULTY-SUBJECT MAPPING -----------------
@admin_bp.route('/mappings', methods=['GET', 'POST'])
@login_required
@admin_required
def mappings():
    if request.method == 'POST':
        action = request.form.get('action', 'create')

        if action == 'copy_allocations':
            # Copy allocations from a source year & sem to target year & sem
            source_year = request.form.get('source_year_id', type=int)
            source_sem = request.form.get('source_semester_id', type=int)
            target_year = request.form.get('target_year_id', type=int)
            target_sem = request.form.get('target_semester_id', type=int)

            source_maps = FacultySubjectMapping.query.filter_by(
                academic_year_id=source_year,
                semester_id=source_sem,
                status='Active'
            ).all()

            copied_count = 0
            for sm in source_maps:
                # Find matching section in target year
                target_sec = Section.query.filter_by(
                    programme_id=sm.programme_id,
                    academic_year_id=target_year,
                    semester_id=target_sem,
                    name=sm.section.name
                ).first()

                if not target_sec:
                    # Create target section if it doesn't exist yet
                    target_sec = Section(
                        programme_id=sm.programme_id,
                        academic_year_id=target_year,
                        semester_id=target_sem,
                        name=sm.section.name
                    )
                    db.session.add(target_sec)
                    db.session.flush()

                # Check duplicate
                dup = FacultySubjectMapping.query.filter_by(
                    academic_year_id=target_year,
                    programme_id=sm.programme_id,
                    semester_id=target_sem,
                    section_id=target_sec.id,
                    subject_id=sm.subject_id,
                    faculty_id=sm.faculty_id
                ).first()

                if not dup:
                    new_map = FacultySubjectMapping(
                        academic_year_id=target_year,
                        programme_id=sm.programme_id,
                        semester_id=target_sem,
                        section_id=target_sec.id,
                        subject_id=sm.subject_id,
                        faculty_id=sm.faculty_id,
                        status='Active'
                    )
                    db.session.add(new_map)
                    db.session.flush()
                    
                    # Copy assessment structure
                    for old_ass in sm.assessments:
                        new_ass = Assessment(
                            mapping_id=new_map.id,
                            assessment_name=old_ass.assessment_name,
                            assessment_type=old_ass.assessment_type,
                            max_marks=old_ass.max_marks,
                            weightage=old_ass.weightage,
                            order_num=old_ass.order_num
                        )
                        db.session.add(new_ass)
                    copied_count += 1

            db.session.commit()
            log_action('COPY_MAPPINGS', 'FacultySubjectMapping', updated_value={'copied_count': copied_count, 'target_year': target_year})
            flash(f"Successfully cloned {copied_count} allocations and their assessment patterns.", 'success')
            return redirect(url_for('admin.mappings'))

        # Single Mapping creation
        academic_year_id = request.form.get('academic_year_id', type=int)
        programme_id = request.form.get('programme_id', type=int)
        semester_id = request.form.get('semester_id', type=int)
        section_id = request.form.get('section_id', type=int)
        subject_id = request.form.get('subject_id', type=int)
        faculty_id = request.form.get('faculty_id', type=int)

        existing = FacultySubjectMapping.query.filter_by(
            academic_year_id=academic_year_id,
            programme_id=programme_id,
            semester_id=semester_id,
            section_id=section_id,
            subject_id=subject_id,
            faculty_id=faculty_id
        ).first()

        if existing:
            flash('This exact Faculty-Subject-Section allocation already exists.', 'warning')
        else:
            mapping = FacultySubjectMapping(
                academic_year_id=academic_year_id,
                programme_id=programme_id,
                semester_id=semester_id,
                section_id=section_id,
                subject_id=subject_id,
                faculty_id=faculty_id,
                status='Active'
            )
            db.session.add(mapping)
            db.session.flush()

            # Automatically populate standard assessment components per PRD FR-09
            default_assessments = [
                ('Test 1', 'Test', 20.0, 1),
                ('Test 2', 'Test', 20.0, 2),
                ('Assignment', 'Assignment', 10.0, 3),
                ('Quiz 1', 'Quiz', 10.0, 4),
                ('ICA', 'ICA', 50.0, 5),
                ('Term End Examination', 'TEE', 100.0, 6),
            ]
            for a_name, a_type, a_max, a_ord in default_assessments:
                ass = Assessment(
                    mapping_id=mapping.id,
                    assessment_name=a_name,
                    assessment_type=a_type,
                    max_marks=a_max,
                    order_num=a_ord
                )
                db.session.add(ass)

            db.session.commit()
            log_action('CREATE_MAPPING', 'FacultySubjectMapping', entity_id=mapping.id, updated_value={'mapping': mapping.display_title})
            flash('Faculty allocation and default assessment components created successfully.', 'success')

        return redirect(url_for('admin.mappings'))

    # GET mappings with optional filters
    year_id = request.args.get('academic_year_id', type=int)
    prog_id = request.args.get('programme_id', type=int)
    sem_id = request.args.get('semester_id', type=int)
    faculty_filter = request.args.get('faculty_id', type=int)

    query = FacultySubjectMapping.query
    if year_id:
        query = query.filter_by(academic_year_id=year_id)
    if prog_id:
        query = query.filter_by(programme_id=prog_id)
    if sem_id:
        query = query.filter_by(semester_id=sem_id)
    if faculty_filter:
        query = query.filter_by(faculty_id=faculty_filter)

    mappings_list = query.order_by(FacultySubjectMapping.created_at.desc()).all()

    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    programmes = Programme.query.filter_by(is_active=True).all()
    semesters = Semester.query.order_by(Semester.number.asc()).all()
    sections = Section.query.filter_by(is_active=True).all()
    subjects = Subject.query.filter_by(status='Active').all()
    faculty_members = Faculty.query.filter_by(status='Active').order_by(Faculty.name.asc()).all()

    return render_template(
        'admin/mappings.html',
        mappings=mappings_list,
        academic_years=academic_years,
        programmes=programmes,
        semesters=semesters,
        sections=sections,
        subjects=subjects,
        faculty_members=faculty_members,
        selected_filters={'year_id': year_id, 'prog_id': prog_id, 'sem_id': sem_id, 'faculty_id': faculty_filter}
    )

@admin_bp.route('/mappings/<int:id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_mapping_status(id):
    mapping = FacultySubjectMapping.query.get_or_404(id)
    mapping.status = 'Inactive' if mapping.status == 'Active' else 'Active'
    db.session.commit()
    log_action('TOGGLE_MAPPING_STATUS', 'FacultySubjectMapping', entity_id=mapping.id, updated_value={'status': mapping.status})
    flash(f"Mapping status changed to {mapping.status}.", 'info')
    return redirect(url_for('admin.mappings'))

# ----------------- ASSESSMENTS MANAGEMENT -----------------
@admin_bp.route('/assessments')
@login_required
@admin_required
def assessments():
    return redirect(url_for('admin.mappings'))

@admin_bp.route('/mappings/<int:mapping_id>/assessments', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_assessments(mapping_id):
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        if action == 'add':
            name = request.form.get('assessment_name', '').strip()
            atype = request.form.get('assessment_type', 'Test')
            max_m = request.form.get('max_marks', 20.0, type=float)
            weight = request.form.get('weightage', 100.0, type=float)
            ord_n = request.form.get('order_num', 1, type=int)

            if Assessment.query.filter_by(mapping_id=mapping.id, assessment_name=name).first():
                flash(f"Assessment '{name}' already exists for this mapping.", 'warning')
            else:
                ass = Assessment(
                    mapping_id=mapping.id,
                    assessment_name=name,
                    assessment_type=atype,
                    max_marks=max_m,
                    weightage=weight,
                    order_num=ord_n
                )
                db.session.add(ass)
                db.session.commit()
                log_action('ADD_ASSESSMENT', 'Assessment', entity_id=ass.id, updated_value={'name': name, 'max_marks': max_m})
                flash(f"Assessment '{name}' added.", 'success')

        elif action == 'edit':
            ass_id = request.form.get('assessment_id', type=int)
            ass = Assessment.query.get_or_404(ass_id)
            ass.assessment_name = request.form.get('assessment_name', ass.assessment_name).strip()
            ass.assessment_type = request.form.get('assessment_type', ass.assessment_type)
            ass.max_marks = request.form.get('max_marks', ass.max_marks, type=float)
            ass.weightage = request.form.get('weightage', ass.weightage, type=float)
            ass.is_active = bool(request.form.get('is_active'))
            db.session.commit()
            log_action('UPDATE_ASSESSMENT', 'Assessment', entity_id=ass.id, updated_value={'max_marks': ass.max_marks})
            flash(f"Assessment '{ass.assessment_name}' updated.", 'success')

        return redirect(url_for('admin.manage_assessments', mapping_id=mapping.id))

    assessments = Assessment.query.filter_by(mapping_id=mapping.id).order_by(Assessment.order_num.asc()).all()
    return render_template('admin/assessments.html', mapping=mapping, assessments=assessments)

# ----------------- STUDENT MANAGEMENT -----------------
@admin_bp.route('/students', methods=['GET', 'POST'])
@login_required
@admin_required
def students():
    if request.method == 'POST':
        action = request.form.get('action', 'add')

        if action == 'add':
            reg_no = request.form.get('register_number', '').strip().upper()
            name = request.form.get('student_name', '').strip()
            prog_id = request.form.get('programme_id', type=int)
            year_id = request.form.get('academic_year_id', type=int)
            sem_id = request.form.get('semester_id', type=int)
            sec_id = request.form.get('section_id', type=int)
            email = request.form.get('email', '').strip().lower()

            if Student.query.filter_by(register_number=reg_no).first():
                flash(f"Student with Register Number '{reg_no}' already exists.", 'danger')
            else:
                stu = Student(
                    register_number=reg_no,
                    student_id_code=reg_no,
                    student_name=name,
                    programme_id=prog_id,
                    academic_year_id=year_id,
                    current_semester_id=sem_id,
                    section_id=sec_id,
                    email=email,
                    status='Active'
                )
                db.session.add(stu)
                db.session.flush()

                enroll = StudentEnrollment(
                    student_id=stu.id,
                    year_id=year_id,
                    programme_id=prog_id,
                    semester_id=sem_id,
                    section_id=sec_id,
                    status='active'
                )
                db.session.add(enroll)
                db.session.commit()
                log_action('CREATE_STUDENT', 'Student', entity_id=stu.id, updated_value={'reg_no': reg_no, 'name': name})
                flash(f"Student '{name}' ({reg_no}) registered successfully.", 'success')
            return redirect(url_for('admin.students'))

        elif action == 'import_excel':
            file = request.files.get('file')
            prog_id = request.form.get('programme_id', type=int)
            year_id = request.form.get('academic_year_id', type=int)
            sem_id = request.form.get('semester_id', type=int)
            sec_id = request.form.get('section_id', type=int)

            if not file or not file.filename:
                flash('Please select an Excel or CSV file to upload.', 'danger')
                return redirect(url_for('admin.students'))

            try:
                if file.filename.lower().endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)

                # Find register number and name columns
                reg_col = None
                name_col = None
                email_col = None
                for c in df.columns:
                    cup = str(c).upper().strip()
                    if 'REG' in cup:
                        reg_col = c
                    elif 'NAME' in cup:
                        name_col = c
                    elif 'EMAIL' in cup:
                        email_col = c

                if not reg_col or not name_col:
                    flash("File must contain columns for 'Register Number' and 'Student Name'.", 'danger')
                    return redirect(url_for('admin.students'))

                added_count = 0
                dup_count = 0
                for _, row in df.iterrows():
                    r_val = str(row[reg_col]).strip().upper()
                    n_val = str(row[name_col]).strip()
                    e_val = str(row[email_col]).strip().lower() if email_col and pd.notna(row[email_col]) else None
                    if not r_val or r_val == 'NAN':
                        continue

                    if Student.query.filter_by(register_number=r_val).first():
                        dup_count += 1
                        continue

                    stu = Student(
                        register_number=r_val,
                        student_id_code=r_val,
                        student_name=n_val,
                        programme_id=prog_id,
                        academic_year_id=year_id,
                        current_semester_id=sem_id,
                        section_id=sec_id,
                        email=e_val,
                        status='Active'
                    )
                    db.session.add(stu)
                    db.session.flush()

                    enroll = StudentEnrollment(
                        student_id=stu.id,
                        year_id=year_id,
                        programme_id=prog_id,
                        semester_id=sem_id,
                        section_id=sec_id,
                        status='active'
                    )
                    db.session.add(enroll)
                    added_count += 1

                db.session.commit()
                log_action('IMPORT_STUDENTS', 'Student', updated_value={'added': added_count, 'duplicates_skipped': dup_count})
                flash(f"Import complete: {added_count} students added. {dup_count} existing duplicates skipped.", 'success')
            except Exception as e:
                flash(f"Error parsing file: {str(e)}", 'danger')

            return redirect(url_for('admin.students'))

        elif action == 'transfer_section':
            student_id = request.form.get('student_id', type=int)
            new_sec_id = request.form.get('new_section_id', type=int)
            stu = Student.query.get_or_404(student_id)
            prev_sec = stu.section.name
            stu.section_id = new_sec_id

            # BL-11: update or record enrollment
            curr_enroll = StudentEnrollment.query.filter_by(
                student_id=stu.id,
                year_id=stu.academic_year_id,
                semester_id=stu.current_semester_id
            ).first()
            if curr_enroll:
                curr_enroll.section_id = new_sec_id
            else:
                new_enr = StudentEnrollment(
                    student_id=stu.id,
                    year_id=stu.academic_year_id,
                    programme_id=stu.programme_id,
                    semester_id=stu.current_semester_id,
                    section_id=new_sec_id,
                    status='active'
                )
                db.session.add(new_enr)

            db.session.commit()
            log_action('TRANSFER_STUDENT_SECTION', 'Student', entity_id=stu.id, previous_value=prev_sec, updated_value=stu.section.name)
            flash(f"Student {stu.student_name} transferred to Section {stu.section.name}.", 'info')
            return redirect(url_for('admin.students'))

        elif action == 'promote_semester':
            student_id = request.form.get('student_id', type=int)
            new_sem_id = request.form.get('new_semester_id', type=int)
            new_sec_id = request.form.get('new_section_id', type=int)
            stu = Student.query.get_or_404(student_id)
            prev = f"Sem {stu.current_semester.number} Sec {stu.section.name}"
            stu.current_semester_id = new_sem_id
            stu.section_id = new_sec_id

            # BL-10, BL-11: Add or update historical enrollment record for new semester
            existing_prom_enroll = StudentEnrollment.query.filter_by(
                student_id=stu.id,
                year_id=stu.academic_year_id,
                semester_id=new_sem_id
            ).first()
            if existing_prom_enroll:
                existing_prom_enroll.section_id = new_sec_id
                existing_prom_enroll.status = 'active'
            else:
                prom_enroll = StudentEnrollment(
                    student_id=stu.id,
                    year_id=stu.academic_year_id,
                    programme_id=stu.programme_id,
                    semester_id=new_sem_id,
                    section_id=new_sec_id,
                    status='active'
                )
                db.session.add(prom_enroll)

            db.session.commit()
            log_action('PROMOTE_STUDENT', 'Student', entity_id=stu.id, previous_value=prev, updated_value=f"Sem {stu.current_semester.number} Sec {stu.section.name}")
            flash(f"Student {stu.student_name} promoted to Semester {stu.current_semester.number}.", 'success')
            return redirect(url_for('admin.students'))

    # GET with filters & search
    search = request.args.get('search', '').strip()
    prog_id = request.args.get('programme_id', type=int)
    year_id = request.args.get('academic_year_id', type=int)
    sem_id = request.args.get('semester_id', type=int)
    sec_id = request.args.get('section_id', type=int)
    page = request.args.get('page', 1, type=int)

    q = Student.query
    if search:
        q = q.filter((Student.register_number.ilike(f'%{search}%')) | (Student.student_name.ilike(f'%{search}%')))
    if prog_id:
        q = q.filter_by(programme_id=prog_id)
    if year_id:
        q = q.filter_by(academic_year_id=year_id)
    if sem_id:
        q = q.filter_by(current_semester_id=sem_id)
    if sec_id:
        q = q.filter_by(section_id=sec_id)

    students_pagination = q.order_by(Student.register_number.asc()).paginate(page=page, per_page=15, error_out=False)

    programmes = Programme.query.filter_by(is_active=True).all()
    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc()).all()
    semesters = Semester.query.order_by(Semester.number.asc()).all()
    sections = Section.query.filter_by(is_active=True).all()

    return render_template(
        'admin/students.html',
        pagination=students_pagination,
        programmes=programmes,
        academic_years=academic_years,
        semesters=semesters,
        sections=sections,
        search=search,
        selected_filters={'prog_id': prog_id, 'year_id': year_id, 'sem_id': sem_id, 'sec_id': sec_id}
    )

@admin_bp.route('/students/template')
@login_required
@admin_required
def download_student_template():
    output = generate_student_import_template()
    return send_file(
        output,
        download_name="Student_Import_Template.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ----------------- MARKS MONITORING & APPROVAL -----------------
@admin_bp.route('/marks-review')
@login_required
@admin_required
def marks_review():
    status_filter = request.args.get('status', 'all')
    q = Submission.query
    if status_filter != 'all':
        q = q.filter_by(status=status_filter)

    submissions = q.order_by(Submission.submission_date.desc().nullslast(), Submission.id.desc()).all()
    return render_template('admin/marks_review.html', submissions=submissions, status_filter=status_filter)

@admin_bp.route('/submissions/<int:id>/action', methods=['POST'])
@login_required
@admin_required
def process_submission_action(id):
    sub = Submission.query.get_or_404(id)
    action = request.form.get('action') # 'approve' or 'reopen'
    comments = request.form.get('comments', '').strip()

    prev_status = sub.status
    if action == 'approve':
        sub.status = 'Approved'
        sub.reviewed_by_id = current_user.id
        sub.review_date = datetime.utcnow()
        sub.review_comments = comments or 'Approved by Academic Admin'
        db.session.commit()
        log_action('APPROVE_MARKS', 'Submission', entity_id=sub.id, previous_value=prev_status, updated_value='Approved')
        flash(f"Submission for {sub.mapping.display_title} has been APPROVED.", 'success')

    elif action == 'reopen':
        sub.status = 'Reopened'
        sub.reviewed_by_id = current_user.id
        sub.review_date = datetime.utcnow()
        sub.review_comments = comments or 'Reopened for faculty corrections'
        db.session.commit()
        log_action('REOPEN_MARKS', 'Submission', entity_id=sub.id, previous_value=prev_status, updated_value='Reopened')
        flash(f"Submission for {sub.mapping.display_title} has been REOPENED for faculty edits.", 'warning')

    return redirect(url_for('admin.marks_review'))

# ----------------- USER MANAGEMENT -----------------
@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        role = request.form.get('role', 'admin')
        password = request.form.get('password', '').strip()

        if User.query.filter_by(username=username).first():
            flash(f"Username '{username}' already exists.", 'danger')
        else:
            u = User(username=username, role=role, is_active=True)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            log_action('CREATE_USER', 'User', entity_id=u.id, updated_value={'username': username, 'role': role})
            flash(f"User account '{username}' created.", 'success')
        return redirect(url_for('admin.users'))

    users_list = User.query.order_by(User.role.asc(), User.username.asc()).all()
    return render_template('admin/users.html', users=users_list)

@admin_bp.route('/users/<int:id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(id):
    u = User.query.get_or_404(id)
    if u.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin.users'))
    u.is_active = not u.is_active
    db.session.commit()
    log_action('TOGGLE_USER_STATUS', 'User', entity_id=u.id, updated_value={'is_active': u.is_active})
    flash(f"Account for '{u.username}' status toggled to {'Active' if u.is_active else 'Deactivated'}.", 'info')
    return redirect(url_for('admin.users'))

# ----------------- AUDIT LOGS -----------------
@admin_bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    page = request.args.get('page', 1, type=int)
    action_filter = request.args.get('action', '')
    entity_filter = request.args.get('entity_type', '')

    q = AuditLog.query
    if action_filter:
        q = q.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    if entity_filter:
        q = q.filter(AuditLog.entity_type.ilike(f'%{entity_filter}%'))

    pagination = q.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/audit_logs.html', pagination=pagination, action_filter=action_filter, entity_filter=entity_filter)
