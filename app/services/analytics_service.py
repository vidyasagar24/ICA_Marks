from sqlalchemy import func
from app.models import db, Student, Faculty, Subject, FacultySubjectMapping, Assessment, Mark, Submission, AcademicYear, Programme, Section

def get_admin_dashboard_kpis(filters=None):
    """
    Computes summary KPIs for the admin dashboard with optional filtering.
    """
    filters = filters or {}
    year_id = filters.get('academic_year_id')
    prog_id = filters.get('programme_id')
    sem_id = filters.get('semester_id')

    # Base query for mappings
    map_q = FacultySubjectMapping.query
    if year_id:
        map_q = map_q.filter(FacultySubjectMapping.academic_year_id == year_id)
    if prog_id:
        map_q = map_q.filter(FacultySubjectMapping.programme_id == prog_id)
    if sem_id:
        map_q = map_q.filter(FacultySubjectMapping.semester_id == sem_id)

    total_allocations = map_q.count()
    mapping_ids = [m.id for m in map_q.all()]

    # Students count
    stu_q = Student.query.filter_by(status='Active')
    if year_id:
        stu_q = stu_q.filter(Student.academic_year_id == year_id)
    if prog_id:
        stu_q = stu_q.filter(Student.programme_id == prog_id)
    if sem_id:
        stu_q = stu_q.filter(Student.current_semester_id == sem_id)
    total_students = stu_q.count()

    # Total Faculty
    total_faculty = Faculty.query.filter_by(status='Active').count()

    # Total Subjects
    subj_q = Subject.query.filter_by(status='Active')
    if prog_id:
        subj_q = subj_q.filter(Subject.programme_id == prog_id)
    if sem_id:
        subj_q = subj_q.filter(Subject.semester_id == sem_id)
    total_subjects = subj_q.count()

    # Total Sections
    sec_q = Section.query.filter_by(is_active=True)
    if year_id:
        sec_q = sec_q.filter(Section.academic_year_id == year_id)
    if prog_id:
        sec_q = sec_q.filter(Section.programme_id == prog_id)
    if sem_id:
        sec_q = sec_q.filter(Section.semester_id == sem_id)
    total_sections = sec_q.count()

    # Submissions counts
    sub_q = Submission.query
    if mapping_ids:
        sub_q = sub_q.filter(Submission.mapping_id.in_(mapping_ids))
    elif total_allocations == 0:
        sub_q = sub_q.filter(Submission.id == -1)

    all_submissions = sub_q.all()
    submitted_count = sum(1 for s in all_submissions if s.status in ['Submitted', 'Approved', 'Under Review'])
    approved_count = sum(1 for s in all_submissions if s.status == 'Approved')
    under_review_count = sum(1 for s in all_submissions if s.status in ['Submitted', 'Under Review'])
    reopened_count = sum(1 for s in all_submissions if s.status == 'Reopened')

    # Pending submissions count (mappings without approved or submitted submissions)
    submitted_mapping_ids = {s.mapping_id for s in all_submissions if s.status in ['Submitted', 'Approved', 'Under Review']}
    pending_submissions = max(0, total_allocations - len(submitted_mapping_ids))

    return {
        'total_students': total_students,
        'total_faculty': total_faculty,
        'total_subjects': total_subjects,
        'total_sections': total_sections,
        'total_allocations': total_allocations,
        'marks_submitted': submitted_count,
        'approved_count': approved_count,
        'approval_pending': under_review_count,
        'pending_submissions': pending_submissions,
        'reopened_count': reopened_count
    }


def get_section_analysis(mapping_id, threshold_pct=40.0):
    """
    Computes Section-wise analysis:
    - Average marks by assessment
    - Highest and lowest marks
    - Number of students below threshold
    - Pass percentage
    - Distribution
    """
    mapping = FacultySubjectMapping.query.get_or_404(mapping_id)
    students = Student.query.filter_by(section_id=mapping.section_id, status='Active').all()
    assessments = Assessment.query.filter_by(mapping_id=mapping.id, is_active=True).order_by(Assessment.order_num.asc()).all()

    marks_map = {}
    for m in Mark.query.filter_by(mapping_id=mapping.id).all():
        marks_map[(m.student_id, m.assessment_id)] = m

    ass_stats = []
    total_students_count = len(students)

    for ass in assessments:
        scores = []
        absent_count = 0
        exempt_count = 0

        for stu in students:
            m = marks_map.get((stu.id, ass.id))
            if m:
                if m.status == 'Absent':
                    absent_count += 1
                elif m.status == 'Exempted':
                    exempt_count += 1
                elif m.score is not None:
                    scores.append(m.score)

        tested_count = len(scores)
        avg_score = (sum(scores) / tested_count) if tested_count > 0 else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0
        
        pass_cutoff = ass.max_marks * (threshold_pct / 100.0)
        passed_count = sum(1 for s in scores if s >= pass_cutoff)
        below_count = sum(1 for s in scores if s < pass_cutoff)
        pass_pct = (passed_count / tested_count * 100) if tested_count > 0 else 0

        ass_stats.append({
            'assessment_id': ass.id,
            'name': ass.assessment_name,
            'max_marks': ass.max_marks,
            'average': round(avg_score, 2),
            'highest': round(max_score, 2),
            'lowest': round(min_score, 2),
            'below_threshold_count': below_count,
            'pass_percentage': round(pass_pct, 1),
            'tested_count': tested_count,
            'absent_count': absent_count,
            'exempt_count': exempt_count,
            'missing_count': max(0, total_students_count - (tested_count + absent_count + exempt_count))
        })

    # Overall student performance distribution
    grade_distribution = {'Distinction (>=80%)': 0, 'First Class (60-79%)': 0, 'Second Class (50-59%)': 0, 'Pass (40-49%)': 0, 'Fail (<40%)': 0}
    max_total = sum(a.max_marks for a in assessments)

    for stu in students:
        total_score = 0.0
        has_scores = False
        for ass in assessments:
            m = marks_map.get((stu.id, ass.id))
            if m and m.score is not None:
                total_score += m.score
                has_scores = True

        if has_scores and max_total > 0:
            pct = (total_score / max_total) * 100
            if pct >= 80:
                grade_distribution['Distinction (>=80%)'] += 1
            elif pct >= 60:
                grade_distribution['First Class (60-79%)'] += 1
            elif pct >= 50:
                grade_distribution['Second Class (50-59%)'] += 1
            elif pct >= 40:
                grade_distribution['Pass (40-49%)'] += 1
            else:
                grade_distribution['Fail (<40%)'] += 1

    return {
        'mapping': mapping,
        'assessments': ass_stats,
        'grade_distribution': grade_distribution,
        'total_enrolled': total_students_count
    }


def get_faculty_workload_analysis(faculty_id):
    """
    Computes Faculty-wise analysis:
    - Subjects handled
    - Sections handled
    - Total students assigned
    - Marks entry completion percentage
    - Pending submissions
    """
    faculty = Faculty.query.get_or_404(faculty_id)
    mappings = FacultySubjectMapping.query.filter_by(faculty_id=faculty.id, status='Active').all()

    total_allocations = len(mappings)
    unique_subjects = {m.subject_id for m in mappings}
    unique_sections = {m.section_id for m in mappings}

    total_students_assigned = 0
    total_possible_marks = 0
    entered_marks = 0
    pending_submissions = 0

    allocation_details = []

    for m in mappings:
        students = Student.query.filter_by(section_id=m.section_id, status='Active').all()
        stu_count = len(students)
        total_students_assigned += stu_count

        assessments = Assessment.query.filter_by(mapping_id=m.id, is_active=True).all()
        ass_count = len(assessments)
        
        possible_slots = stu_count * ass_count
        total_possible_marks += possible_slots

        # Entered marks count
        filled_slots = Mark.query.filter_by(mapping_id=m.id).filter(
            (Mark.score.isnot(None)) | (Mark.status.in_(['Absent', 'Exempted']))
        ).count()
        entered_marks += filled_slots

        # Submission status
        sub = Submission.query.filter_by(mapping_id=m.id).order_by(Submission.id.desc()).first()
        status = sub.status if sub else 'Draft'
        if status in ['Draft', 'Reopened']:
            pending_submissions += 1

        completion_pct = (filled_slots / possible_slots * 100) if possible_slots > 0 else 0
        allocation_details.append({
            'mapping': m,
            'students_count': stu_count,
            'assessments_count': ass_count,
            'completion_pct': round(completion_pct, 1),
            'submission_status': status,
            'submission_badge': sub.badge_class if sub else 'secondary'
        })

    overall_completion = (entered_marks / total_possible_marks * 100) if total_possible_marks > 0 else 0
    draft_marks_count = sum(1 for a in allocation_details if a['submission_status'] in ['Draft', 'Reopened'])
    submitted_marks_count = sum(1 for a in allocation_details if a['submission_status'] in ['Submitted', 'Approved', 'Under Review'])
    pending_assessments = sum(a['assessments_count'] for a in allocation_details if a['submission_status'] in ['Draft', 'Reopened'])

    return {
        'faculty': faculty,
        'subjects_count': len(unique_subjects),
        'sections_count': len(unique_sections),
        'total_allocations': total_allocations,
        'total_students': total_students_assigned,
        'overall_completion': round(overall_completion, 1),
        'pending_submissions': pending_submissions,
        'draft_marks_count': draft_marks_count,
        'submitted_marks_count': submitted_marks_count,
        'pending_assessments': pending_assessments,
        'allocations': allocation_details
    }


def get_subject_wise_analysis(subject_id, academic_year_id=None):
    """
    Computes Subject-wise analysis:
    - Compare sections for this subject
    - Test 1 vs Test 2 comparison
    - ICA vs TEE comparison
    - Subject average across sections
    """
    subject = Subject.query.get_or_404(subject_id)
    map_q = FacultySubjectMapping.query.filter_by(subject_id=subject.id, status='Active')
    if academic_year_id:
        map_q = map_q.filter_by(academic_year_id=academic_year_id)
    mappings = map_q.all()

    section_comparisons = []
    test1_scores = []
    test2_scores = []
    ica_scores = []
    tee_scores = []

    for m in mappings:
        assessments = Assessment.query.filter_by(mapping_id=m.id, is_active=True).all()
        marks = Mark.query.filter_by(mapping_id=m.id).filter(Mark.score.isnot(None)).all()
        
        stu_scores = [mk.score for mk in marks]
        avg = (sum(stu_scores) / len(stu_scores)) if stu_scores else 0

        section_comparisons.append({
            'section_name': m.section.name,
            'faculty_name': m.faculty.name,
            'student_count': Student.query.filter_by(section_id=m.section_id, status='Active').count(),
            'average_score': round(avg, 2)
        })

        for mk in marks:
            ass_name = mk.assessment.assessment_name.upper()
            if 'TEST 1' in ass_name or 'TEST1' in ass_name:
                test1_scores.append(mk.score)
            elif 'TEST 2' in ass_name or 'TEST2' in ass_name:
                test2_scores.append(mk.score)
            elif 'ICA' in ass_name or 'INTERNAL' in ass_name:
                ica_scores.append(mk.score)
            elif 'TEE' in ass_name or 'TERM END' in ass_name or 'FINAL' in ass_name:
                tee_scores.append(mk.score)

    test1_avg = (sum(test1_scores) / len(test1_scores)) if test1_scores else 0
    test2_avg = (sum(test2_scores) / len(test2_scores)) if test2_scores else 0
    ica_avg = (sum(ica_scores) / len(ica_scores)) if ica_scores else 0
    tee_avg = (sum(tee_scores) / len(tee_scores)) if tee_scores else 0

    return {
        'subject': subject,
        'section_comparisons': section_comparisons,
        'test1_avg': round(test1_avg, 2),
        'test2_avg': round(test2_avg, 2),
        'ica_avg': round(ica_avg, 2),
        'tee_avg': round(tee_avg, 2)
    }
