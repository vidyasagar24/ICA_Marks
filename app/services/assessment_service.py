"""
Assessment Configuration & ICA Distribution Service
Supports faculty-configurable ICA mark distributions (Test1, Test2, Quiz, Assignment, Lab, etc.)
and balanced defaults per subject ICA/TEE limits.
"""
from app.models import db, Assessment, Mark


def _alloc_weights(total_max, ratios):
    """Allocate total_max cleanly across ratios so parts sum exactly to total_max."""
    total_max = float(total_max or 50.0)
    parts = [round(total_max * r, 1) for r in ratios[:-1]]
    last = round(total_max - sum(parts), 1)
    parts.append(max(0.5, last))
    return [int(p) if float(p).is_integer() else p for p in parts]


def get_ica_presets(ica_max=50.0):
    """Return standard ICA distribution presets scaled to subject.ica_max."""
    m = float(ica_max or 50.0)
    w4 = _alloc_weights(m, [0.30, 0.30, 0.20, 0.20])
    w3 = _alloc_weights(m, [0.40, 0.40, 0.20])
    w_mid = _alloc_weights(m, [0.50, 0.20, 0.30])
    return [
        {
            'key': 'standard_4',
            'label': 'Test1 + Test2 + Quiz + Assignment',
            'items': [
                {'name': 'Test 1', 'type': 'Test', 'max_marks': w4[0]},
                {'name': 'Test 2', 'type': 'Test', 'max_marks': w4[1]},
                {'name': 'Quiz', 'type': 'Quiz', 'max_marks': w4[2]},
                {'name': 'Assignment', 'type': 'Assignment', 'max_marks': w4[3]},
            ],
        },
        {
            'key': 'standard_3',
            'label': 'Test1 + Test2 + Assignment',
            'items': [
                {'name': 'Test 1', 'type': 'Test', 'max_marks': w3[0]},
                {'name': 'Test 2', 'type': 'Test', 'max_marks': w3[1]},
                {'name': 'Assignment', 'type': 'Assignment', 'max_marks': w3[2]},
            ],
        },
        {
            'key': 'midterm_continuous',
            'label': 'Mid-Term + Quiz + Assignment',
            'items': [
                {'name': 'Mid-Term Exam', 'type': 'Mid-Term', 'max_marks': w_mid[0]},
                {'name': 'Quiz', 'type': 'Quiz', 'max_marks': w_mid[1]},
                {'name': 'Assignment', 'type': 'Assignment', 'max_marks': w_mid[2]},
            ],
        },
        {
            'key': 'lab_integrated',
            'label': 'Test1 + Test2 + Lab + Quiz',
            'items': [
                {'name': 'Test 1', 'type': 'Test', 'max_marks': w4[0]},
                {'name': 'Test 2', 'type': 'Test', 'max_marks': w4[1]},
                {'name': 'Lab / Practical', 'type': 'Lab', 'max_marks': w4[2]},
                {'name': 'Quiz', 'type': 'Quiz', 'max_marks': w4[3]},
            ],
        },
        {
            'key': 'direct_ica',
            'label': f'Direct Single ICA ({int(m) if m.is_integer() else m})',
            'items': [
                {'name': 'ICA', 'type': 'ICA', 'max_marks': m},
            ],
        },
    ]


def seed_default_assessments_for_mapping(mapping):
    """Attach default ICA distribution + TEE components matching subject max marks."""
    ica_max = float(mapping.subject.ica_max if mapping.subject else 50.0) or 50.0
    tee_max = float(mapping.subject.tee_max if mapping.subject else 100.0) or 100.0
    w = _alloc_weights(ica_max, [0.30, 0.30, 0.20, 0.20])

    defaults = [
        ('Test 1', 'Test', w[0], 1),
        ('Test 2', 'Test', w[1], 2),
        ('Quiz 1', 'Quiz', w[2], 3),
        ('Assignment', 'Assignment', w[3], 4),
        ('Term End Examination', 'TEE', tee_max, 5),
    ]
    for a_name, a_type, a_max, a_ord in defaults:
        db.session.add(Assessment(
            mapping_id=mapping.id,
            assessment_name=a_name,
            assessment_type=a_type,
            max_marks=a_max,
            order_num=a_ord,
            is_active=True
        ))


def split_ica_assessments(assessments):
    """Separate active assessments into (internal_components, explicit_ica_ass, tee_ass)."""
    explicit_ica = next(
        (a for a in assessments if a.assessment_type == 'ICA' or a.assessment_name.strip().upper() == 'ICA'),
        None
    )
    tee_ass = next(
        (a for a in assessments if a.assessment_type == 'TEE' or 'TEE' in a.assessment_name.upper() or 'TERM END' in a.assessment_name.upper()),
        None
    )
    internals = [a for a in assessments if a != explicit_ica and a != tee_ass]
    return internals, explicit_ica, tee_ass


def save_faculty_ica_distribution(mapping, components, include_tee=True, tee_max=None):
    """
    Persist faculty-chosen ICA distribution components for a mapping while preserving
    any existing marks for kept/renamed assessments or deactivating unused ones safely.
    """
    existing_all = Assessment.query.filter_by(mapping_id=mapping.id).all()
    by_id = {a.id: a for a in existing_all}
    by_name = {a.assessment_name.strip().upper(): a for a in existing_all}

    kept_ids = set()
    seen_names = set()
    order_counter = 1

    for comp in components:
        name = (comp.get('name') or '').strip()
        if not name:
            continue
        upper_name = name.upper()
        if upper_name in seen_names:
            raise ValueError(f"Duplicate component name '{name}'. Each component name must be unique.")
        seen_names.add(upper_name)

        max_m = float(comp.get('max_marks') or 0)
        if max_m <= 0:
            raise ValueError(f"Maximum marks for '{name}' must be greater than 0.")

        atype = (comp.get('type') or 'Test').strip()
        comp_id = comp.get('id')

        target = None
        if comp_id and int(comp_id) in by_id:
            candidate = by_id[int(comp_id)]
            # Prevent collision if renaming to another existing record's name
            conflict = by_name.get(upper_name)
            if conflict and conflict.id != candidate.id:
                target = conflict
            else:
                target = candidate
        elif upper_name in by_name:
            target = by_name[upper_name]

        if target:
            old_upper = target.assessment_name.strip().upper()
            target.assessment_name = name
            target.assessment_type = atype
            target.max_marks = max_m
            target.order_num = order_counter
            target.is_active = True
            by_name.pop(old_upper, None)
            by_name[upper_name] = target
        else:
            target = Assessment(
                mapping_id=mapping.id,
                assessment_name=name,
                assessment_type=atype,
                max_marks=max_m,
                order_num=order_counter,
                is_active=True
            )
            db.session.add(target)
            db.session.flush()
            by_id[target.id] = target
            by_name[upper_name] = target

        kept_ids.add(target.id)
        order_counter += 1

    # Handle TEE component
    tee_existing = next(
        (a for a in existing_all if a.assessment_type == 'TEE' or 'TERM END' in a.assessment_name.upper() or a.assessment_name.strip().upper() == 'TEE'),
        None
    )
    resolved_tee_max = float(tee_max if tee_max and float(tee_max) > 0 else (mapping.subject.tee_max or 100.0))
    if include_tee:
        if tee_existing:
            if tee_existing.id not in kept_ids:
                tee_existing.order_num = order_counter
                tee_existing.max_marks = resolved_tee_max
                tee_existing.is_active = True
                kept_ids.add(tee_existing.id)
        else:
            tee_new = Assessment(
                mapping_id=mapping.id,
                assessment_name='Term End Examination',
                assessment_type='TEE',
                max_marks=resolved_tee_max,
                order_num=order_counter,
                is_active=True
            )
            db.session.add(tee_new)
            db.session.flush()
            kept_ids.add(tee_new.id)

    # Remove or deactivate unselected components (including redundant standalone ICA if unused)
    for ass in existing_all:
        if ass.id not in kept_ids:
            has_marks = Mark.query.filter_by(assessment_id=ass.id).first() is not None
            if has_marks:
                ass.is_active = False
            else:
                db.session.delete(ass)

    db.session.commit()
