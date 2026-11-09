import os
from datetime import datetime, date
from app import create_app
from app.models import (
    db, User, Faculty, Student, StudentEnrollment, AcademicYear, Programme, Semester, Section,
    Subject, FacultySubjectMapping, Assessment, Mark, Submission, AuditLog, MarksAudit
)

def seed_database(app=None):
    if app is None:
        app = create_app()
        with app.app_context():
            _do_seed()
    else:
        _do_seed()

def _do_seed():
    print("Creating database schema...")
    db.create_all()

    # Check if already seeded
    if User.query.filter_by(username='admin').first():
        print("Database already contains records. Skipping seed.")
        return

        print("Seeding Academic Years (FR-02)...")
        ay1 = AcademicYear(year_code='2024-25', start_date=date(2024, 7, 1), end_date=date(2025, 6, 30), status='Archived')
        ay2 = AcademicYear(year_code='2025-26', start_date=date(2025, 7, 1), end_date=date(2026, 6, 30), status='Archived')
        ay3 = AcademicYear(year_code='2026-27', start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), status='Active')
        db.session.add_all([ay1, ay2, ay3])
        db.session.flush()

        print("Seeding Programmes (FR-03)...")
        prog_ce = Programme(code='CE', name='Computer Engineering', description='Core Computer Engineering curriculum', is_active=True)
        prog_csd = Programme(code='CSD', name='Computer Science and Data Science', description='Data Science & Analytics specialization', is_active=True)
        prog_cse = Programme(code='CSE', name='Computer Science and Engineering', description='General Computer Science & Software Engineering', is_active=True)
        prog_it = Programme(code='IT', name='Information Technology', description='Applied Information Technology & Systems', is_active=True)
        db.session.add_all([prog_ce, prog_csd, prog_cse, prog_it])
        db.session.flush()

        print("Seeding Semesters (FR-04)...")
        semesters = []
        roman_numerals = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII']
        for num, rom in enumerate(roman_numerals, 1):
            sem = Semester(number=num, name=f'Semester {rom}', is_active=True)
            db.session.add(sem)
            semesters.append(sem)
        db.session.flush()
        sem2 = semesters[1]
        sem4 = semesters[3]

        print("Seeding Sections (FR-04)...")
        # CE Sem II Sec A & B
        sec_ce_a = Section(programme_id=prog_ce.id, academic_year_id=ay3.id, semester_id=sem2.id, name='A')
        sec_ce_b = Section(programme_id=prog_ce.id, academic_year_id=ay3.id, semester_id=sem2.id, name='B')
        # CSD Sem II Sec A
        sec_csd_a = Section(programme_id=prog_csd.id, academic_year_id=ay3.id, semester_id=sem2.id, name='A')
        # CSE Sem IV Sec A & B
        sec_cse_a = Section(programme_id=prog_cse.id, academic_year_id=ay3.id, semester_id=sem4.id, name='A')
        sec_cse_b = Section(programme_id=prog_cse.id, academic_year_id=ay3.id, semester_id=sem4.id, name='B')
        db.session.add_all([sec_ce_a, sec_ce_b, sec_csd_a, sec_cse_a, sec_cse_b])
        db.session.flush()

        print("Seeding Admin User (FR-01)...")
        admin_user = User(username='admin', role='admin', is_active=True)
        admin_user.set_password('Admin@123')
        db.session.add(admin_user)

        print("Seeding Faculty & Logins (FR-06)...")
        fac1 = Faculty(faculty_id_code='FAC001', name='Dr. Ramesh Sharma', email='r.sharma@univ.edu', department='Computer Engineering', designation='Professor & Dean', status='Active')
        fac2 = Faculty(faculty_id_code='FAC002', name='Dr. Priya Sundaram', email='p.sundaram@univ.edu', department='Mathematics & Basic Sciences', designation='Associate Professor', status='Active')
        fac3 = Faculty(faculty_id_code='FAC003', name='Prof. Amit Verma', email='a.verma@univ.edu', department='Computer Engineering', designation='Assistant Professor', status='Active')
        fac4 = Faculty(faculty_id_code='FAC004', name='Prof. Sunita Deshmukh', email='s.deshmukh@univ.edu', department='Data Science & AI', designation='Assistant Professor', status='Active')
        db.session.add_all([fac1, fac2, fac3, fac4])
        db.session.flush()

        # Faculty Login Accounts
        u_fac1 = User(username='faculty_a', role='faculty', faculty_id=fac1.id, is_active=True)
        u_fac1.set_password('Faculty@123')

        u_fac2 = User(username='faculty_b', role='faculty', faculty_id=fac2.id, is_active=True)
        u_fac2.set_password('Faculty@123')

        u_fac3 = User(username='faculty_c', role='faculty', faculty_id=fac3.id, is_active=True)
        u_fac3.set_password('Faculty@123')

        u_fac4 = User(username='faculty_d', role='faculty', faculty_id=fac4.id, is_active=True)
        u_fac4.set_password('Faculty@123')

        # Alias logins for maximum convenience
        u_fac_sharma = User(username='faculty_sharma', role='faculty', faculty_id=fac1.id, is_active=True)
        u_fac_sharma.set_password('Faculty@123')

        u_fac_amit = User(username='amit.sharma', role='faculty', faculty_id=fac1.id, is_active=True)
        u_fac_amit.set_password('Faculty@123')

        u_fac_priya = User(username='priya.patel', role='faculty', faculty_id=fac2.id, is_active=True)
        u_fac_priya.set_password('Faculty@123')

        db.session.add_all([u_fac1, u_fac2, u_fac3, u_fac4, u_fac_sharma, u_fac_amit, u_fac_priya])
        db.session.flush()

        print("Seeding Subjects Master (FR-07)...")
        subj_math = Subject(subject_code='MA201', subject_name='Applied Mathematics II', programme_id=prog_ce.id, semester_id=sem2.id, credits=4, ica_max=50, tee_max=100, status='Active')
        subj_dsa = Subject(subject_code='CE202', subject_name='Data Structures & Algorithms', programme_id=prog_ce.id, semester_id=sem2.id, credits=4, ica_max=50, tee_max=100, status='Active')
        subj_dld = Subject(subject_code='CE203', subject_name='Digital Logic & Computer Organization', programme_id=prog_ce.id, semester_id=sem2.id, credits=3, ica_max=50, tee_max=100, status='Active')
        subj_stats = Subject(subject_code='DS201', subject_name='Statistics & Probability for Data Science', programme_id=prog_csd.id, semester_id=sem2.id, credits=4, ica_max=50, tee_max=100, status='Active')
        subj_os = Subject(subject_code='CS401', subject_name='Operating Systems Concepts', programme_id=prog_cse.id, semester_id=sem4.id, credits=4, ica_max=50, tee_max=100, status='Active')
        subj_db = Subject(subject_code='CS402', subject_name='Database Management Systems', programme_id=prog_cse.id, semester_id=sem4.id, credits=4, ica_max=50, tee_max=100, status='Active')
        db.session.add_all([subj_math, subj_dsa, subj_dld, subj_stats, subj_os, subj_db])
        db.session.flush()

        print("Seeding Students (FR-05)...")
        students_data = [
            # CE Sem II Sec A
            ('2026CE001', 'Aarav Sharma', prog_ce.id, sem2.id, sec_ce_a.id, 'aarav.sharma@univ.edu'),
            ('2026CE002', 'Diya Patel', prog_ce.id, sem2.id, sec_ce_a.id, 'diya.patel@univ.edu'),
            ('2026CE003', 'Rohan Mehta', prog_ce.id, sem2.id, sec_ce_a.id, 'rohan.mehta@univ.edu'),
            ('2026CE004', 'Ananya Gupta', prog_ce.id, sem2.id, sec_ce_a.id, 'ananya.gupta@univ.edu'),
            ('2026CE005', 'Kabir Verma', prog_ce.id, sem2.id, sec_ce_a.id, 'kabir.verma@univ.edu'),
            ('2026CE006', 'Ishaan Malhotra', prog_ce.id, sem2.id, sec_ce_a.id, 'ishaan.m@univ.edu'),
            # CE Sem II Sec B
            ('2026CE007', 'Meera Nair', prog_ce.id, sem2.id, sec_ce_b.id, 'meera.nair@univ.edu'),
            ('2026CE008', 'Arjun Kapoor', prog_ce.id, sem2.id, sec_ce_b.id, 'arjun.kapoor@univ.edu'),
            ('2026CE009', 'Sneha Kulkarni', prog_ce.id, sem2.id, sec_ce_b.id, 'sneha.k@univ.edu'),
            ('2026CE010', 'Aditya Joshi', prog_ce.id, sem2.id, sec_ce_b.id, 'aditya.joshi@univ.edu'),
            # CSD Sem II Sec A
            ('2026CSD01', 'Kavya Singhania', prog_csd.id, sem2.id, sec_csd_a.id, 'kavya.s@univ.edu'),
            ('2026CSD02', 'Devendra Roy', prog_csd.id, sem2.id, sec_csd_a.id, 'devendra.roy@univ.edu'),
            ('2026CSD03', 'Pooja Hegde', prog_csd.id, sem2.id, sec_csd_a.id, 'pooja.hegde@univ.edu'),
            ('2026CSD04', 'Siddharth Rao', prog_csd.id, sem2.id, sec_csd_a.id, 'sid.rao@univ.edu'),
            # CSE Sem IV Sec A
            ('2025CSE01', 'Neha Chawla', prog_cse.id, sem4.id, sec_cse_a.id, 'neha.c@univ.edu'),
            ('2025CSE02', 'Vikramaditya Bose', prog_cse.id, sem4.id, sec_cse_a.id, 'vikram.b@univ.edu'),
            ('2025CSE03', 'Ritu Saxena', prog_cse.id, sem4.id, sec_cse_a.id, 'ritu.saxena@univ.edu'),
            ('2025CSE04', 'Manish Pandey', prog_cse.id, sem4.id, sec_cse_a.id, 'manish.p@univ.edu'),
            ('2025CSE05', 'Tanya Agarwal', prog_cse.id, sem4.id, sec_cse_a.id, 'tanya.a@univ.edu'),
        ]
        stu_objs = []
        for reg, name, pid, smid, scid, email in students_data:
            st = Student(
                register_number=reg,
                student_id_code=reg,
                student_name=name,
                programme_id=pid,
                academic_year_id=ay3.id,
                current_semester_id=smid,
                section_id=scid,
                email=email,
                status='Active'
            )
            db.session.add(st)
            db.session.flush()

            enroll = StudentEnrollment(
                student_id=st.id,
                year_id=ay3.id,
                programme_id=pid,
                semester_id=smid,
                section_id=scid,
                status='active'
            )
            db.session.add(enroll)
            stu_objs.append(st)
        db.session.flush()

        print("Seeding Faculty-Subject-Section Mappings (PRD FR-08 Allocations)...")
        # Allocation 1: Year 2026-27, Sem II, CE, Sec A, Mathematics -> Faculty A
        map1 = FacultySubjectMapping(academic_year_id=ay3.id, programme_id=prog_ce.id, semester_id=sem2.id, section_id=sec_ce_a.id, subject_id=subj_math.id, faculty_id=fac1.id, status='Active')
        # Allocation 2: Year 2026-27, Sem II, CE, Sec B, Mathematics -> Faculty B
        map2 = FacultySubjectMapping(academic_year_id=ay3.id, programme_id=prog_ce.id, semester_id=sem2.id, section_id=sec_ce_b.id, subject_id=subj_math.id, faculty_id=fac2.id, status='Active')
        # Allocation 3: Year 2026-27, Sem II, CE, Sec A, Data Structures -> Faculty C
        map3 = FacultySubjectMapping(academic_year_id=ay3.id, programme_id=prog_ce.id, semester_id=sem2.id, section_id=sec_ce_a.id, subject_id=subj_dsa.id, faculty_id=fac3.id, status='Active')
        # Allocation 4: Year 2026-27, Sem II, CSD, Sec A, Statistics -> Faculty A
        map4 = FacultySubjectMapping(academic_year_id=ay3.id, programme_id=prog_csd.id, semester_id=sem2.id, section_id=sec_csd_a.id, subject_id=subj_stats.id, faculty_id=fac1.id, status='Active')
        # Allocation 5: Year 2026-27, Sem IV, CSE, Sec A, Operating Systems -> Faculty D
        map5 = FacultySubjectMapping(academic_year_id=ay3.id, programme_id=prog_cse.id, semester_id=sem4.id, section_id=sec_cse_a.id, subject_id=subj_os.id, faculty_id=fac4.id, status='Active')
        db.session.add_all([map1, map2, map3, map4, map5])
        db.session.flush()

        print("Seeding Assessments & Max Marks (FR-09)...")
        mappings_list = [map1, map2, map3, map4, map5]
        for m in mappings_list:
            ass_configs = [
                ('Test 1', 'Test', 20.0, 1),
                ('Test 2', 'Test', 20.0, 2),
                ('Assignment', 'Assignment', 10.0, 3),
                ('Quiz 1', 'Quiz', 10.0, 4),
                ('ICA', 'ICA', 50.0, 5),
                ('Term End Examination', 'TEE', 100.0, 6)
            ]
            for a_name, a_type, a_max, a_ord in ass_configs:
                ass = Assessment(mapping_id=m.id, assessment_name=a_name, assessment_type=a_type, max_marks=a_max, order_num=a_ord)
                db.session.add(ass)
        db.session.flush()

        print("Seeding Marks & Transactions (FR-10, FR-12)...")
        # Let's seed marks for map1 (CE Sec A - Mathematics - Faculty A)
        # Students in Sec A: 2026CE001 to 2026CE006
        sec_a_students = Student.query.filter_by(section_id=sec_ce_a.id).all()
        map1_assessments = {a.assessment_name: a for a in Assessment.query.filter_by(mapping_id=map1.id).all()}

        sample_scores = [
            # Aarav: High achiever
            (sec_a_students[0], {'Test 1': (18.0, 'Present'), 'Test 2': (19.0, 'Present'), 'Assignment': (10.0, 'Present'), 'Quiz 1': (9.0, 'Present'), 'ICA': (47.0, 'Present'), 'Term End Examination': (92.0, 'Present')}),
            # Diya: Good
            (sec_a_students[1], {'Test 1': (16.0, 'Present'), 'Test 2': (17.5, 'Present'), 'Assignment': (9.0, 'Present'), 'Quiz 1': (8.5, 'Present'), 'ICA': (42.0, 'Present'), 'Term End Examination': (84.0, 'Present')}),
            # Rohan: Average
            (sec_a_students[2], {'Test 1': (14.0, 'Present'), 'Test 2': (13.0, 'Present'), 'Assignment': (8.0, 'Present'), 'Quiz 1': (7.0, 'Present'), 'ICA': (36.0, 'Present'), 'Term End Examination': (68.0, 'Present')}),
            # Ananya: Absent in Test 2
            (sec_a_students[3], {'Test 1': (15.0, 'Present'), 'Test 2': (None, 'Absent'), 'Assignment': (8.5, 'Present'), 'Quiz 1': (8.0, 'Present'), 'ICA': (38.0, 'Present'), 'Term End Examination': (76.0, 'Present')}),
            # Kabir: Struggling (<40%)
            (sec_a_students[4], {'Test 1': (7.0, 'Present'), 'Test 2': (6.5, 'Present'), 'Assignment': (4.0, 'Present'), 'Quiz 1': (3.0, 'Present'), 'ICA': (18.0, 'Present'), 'Term End Examination': (32.0, 'Present')}),
            # Ishaan: Exempted in Quiz
            (sec_a_students[5], {'Test 1': (17.0, 'Present'), 'Test 2': (18.0, 'Present'), 'Assignment': (9.0, 'Present'), 'Quiz 1': (None, 'Exempted'), 'ICA': (44.0, 'Present'), 'Term End Examination': (88.0, 'Present')}),
        ]

        for stu, marks_dict in sample_scores:
            for ass_name, (score_val, status_val) in marks_dict.items():
                ass_obj = map1_assessments[ass_name]
                mark = Mark(
                    student_id=stu.id,
                    assessment_id=ass_obj.id,
                    mapping_id=map1.id,
                    score=score_val,
                    status=status_val
                )
                db.session.add(mark)

        # Map 1 submission is Approved
        sub1 = Submission(
            mapping_id=map1.id,
            submitted_by_id=u_fac1.id,
            status='Approved',
            submission_date=datetime(2026, 10, 15, 14, 30),
            reviewed_by_id=admin_user.id,
            review_date=datetime(2026, 10, 16, 10, 0),
            review_comments='Verified and confirmed against internal exam logs.'
        )
        db.session.add(sub1)

        # Map 3 (Data Structures - Faculty C): Submitted and Pending Review
        map3_assessments = {a.assessment_name: a for a in Assessment.query.filter_by(mapping_id=map3.id).all()}
        for stu in sec_a_students[:4]:
            db.session.add(Mark(student_id=stu.id, assessment_id=map3_assessments['Test 1'].id, mapping_id=map3.id, score=16.0, status='Present'))
            db.session.add(Mark(student_id=stu.id, assessment_id=map3_assessments['Test 2'].id, mapping_id=map3.id, score=15.0, status='Present'))
            db.session.add(Mark(student_id=stu.id, assessment_id=map3_assessments['Assignment'].id, mapping_id=map3.id, score=9.0, status='Present'))

        sub3 = Submission(
            mapping_id=map3.id,
            submitted_by_id=u_fac3.id,
            status='Submitted',
            submission_date=datetime(2026, 11, 2, 11, 15),
            review_comments=None
        )
        db.session.add(sub3)

        # Map 4 (CSD Statistics - Faculty A): Draft status
        map4_assessments = {a.assessment_name: a for a in Assessment.query.filter_by(mapping_id=map4.id).all()}
        csd_students = Student.query.filter_by(section_id=sec_csd_a.id).all()
        for stu in csd_students[:2]:
            db.session.add(Mark(student_id=stu.id, assessment_id=map4_assessments['Test 1'].id, mapping_id=map4.id, score=18.0, status='Present'))
            db.session.add(Mark(student_id=stu.id, assessment_id=map4_assessments['Quiz 1'].id, mapping_id=map4.id, score=9.5, status='Present'))

        # Map 2 (CE Sec B Mathematics - Faculty B): Reopened for correction
        sub2 = Submission(
            mapping_id=map2.id,
            submitted_by_id=u_fac2.id,
            status='Reopened',
            submission_date=datetime(2026, 10, 20, 16, 0),
            reviewed_by_id=admin_user.id,
            review_date=datetime(2026, 10, 21, 9, 30),
            review_comments='Please recheck Quiz 1 maximum marks and re-enter missing entries for student Sneha Kulkarni.'
        )
        db.session.add(sub2)

        # Seed initial Audit Logs
        log1 = AuditLog(user_id=admin_user.id, user_name='admin', role='admin', action='SYSTEM_INIT', entity_type='System', entity_id='1', updated_value='Database schema and academic master data seeded successfully')
        log2 = AuditLog(user_id=u_fac1.id, user_name='faculty_a', role='faculty', action='SUBMIT_MARKS', entity_type='Submission', entity_id=str(sub1.id), updated_value='Submitted MA201 marks for Section A')
        log3 = AuditLog(user_id=admin_user.id, user_name='admin', role='admin', action='APPROVE_MARKS', entity_type='Submission', entity_id=str(sub1.id), updated_value='Approved MA201 Section A marks')
        db.session.add_all([log1, log2, log3])

        db.session.commit()
        print("Database seeded successfully with all PRD sample data!")

if __name__ == '__main__':
    seed_database()
