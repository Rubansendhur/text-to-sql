"""
data/few_shot.py
────────────────
Curated Q → SQL training pairs for the college monitoring RAG pipeline.

Each entry has:
  question  — natural-language question a HOD/staff would ask
  sql       — the correct PostgreSQL query, with {DEPT} as the department
              placeholder. At query time the prompt builder replaces {DEPT}
              with the actual department code for the logged-in user.
  tags      — topic labels used for analytics / coverage checking

NOTE ON {DEPT}:
  - Every example uses {DEPT} wherever a real department code would appear.
  - The seed script (scripts/seed_qdrant.py) stores examples exactly as
    written here — {DEPT} is intentional and stays in the vector DB.
  - At inference time, _build_prompt() in core/rag_engine.py replaces
    every occurrence of {DEPT} with the user's actual department_code before
    passing the examples to the LLM.
  - For central-admin queries (no department scope) the examples are passed
    without substitution (since no filter is needed).

Guidelines used when writing these:
  - Always JOIN departments WHERE department_code = '{DEPT}'
  - timetable columns (day_of_week, slot_id, hour_number, sem_batch) live in
    faculty_timetable / class_timetable, NEVER on the faculty table itself
  - Active arrear = latest attempt per (student, subject) has grade IN ('U','AB')
  - current_semester formula:
      (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
      + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END
"""

FEW_SHOTS = [

    # ══════════════════════════════════════════════════════════
    # STUDENTS — basic
    # ══════════════════════════════════════════════════════════
    {
        "question": "How many active students are there?",
        "sql": """\
SELECT COUNT(*) AS active_students
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active';""",
        "tags": ["students", "count", "active"],
    },
    {
        "question": "List all students",
        "sql": """\
SELECT s.register_number, s.name, s.gender, s.admission_year,
       s.hostel_status, s.status
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
ORDER BY s.register_number
LIMIT 100;""",
        "tags": ["students", "list"],
    },
    {
        "question": "Show all female students",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year, s.hostel_status, s.status
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.gender = 'Female'
ORDER BY s.name
LIMIT 100;""",
        "tags": ["students", "gender"],
    },
    {
        "question": "How many male and female students are there?",
        "sql": """\
SELECT s.gender, COUNT(*) AS count
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
GROUP BY s.gender
ORDER BY s.gender;""",
        "tags": ["students", "gender", "count"],
    },
    {
        "question": "List all students admitted in 2022",
        "sql": """\
SELECT s.register_number, s.name, s.gender, s.hostel_status, s.status
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.admission_year = 2022
ORDER BY s.register_number
LIMIT 100;""",
        "tags": ["students", "batch", "admission_year"],
    },
    {
        "question": "Show students in 8th semester",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year,
       (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
       + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END AS current_semester
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
      + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 8
ORDER BY s.register_number
LIMIT 100;""",
        "tags": ["students", "semester"],
    },
    {
        "question": "Show students in 6th semester",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year,
       (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
       + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END AS current_semester
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
      + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 6
ORDER BY s.register_number
LIMIT 100;""",
        "tags": ["students", "semester"],
    },
    {
        "question": "How many hostellers and day scholars are there?",
        "sql": """\
SELECT s.hostel_status, COUNT(*) AS count
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
GROUP BY s.hostel_status
ORDER BY s.hostel_status;""",
        "tags": ["students", "hostel", "count"],
    },
    {
        "question": "List all hostellers",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year, s.contact_number
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.hostel_status = 'Hosteller'
  AND s.status = 'Active'
ORDER BY s.name
LIMIT 100;""",
        "tags": ["students", "hostel"],
    },
    {
        "question": "Find student with register number 71762233001",
        "sql": """\
SELECT s.register_number, s.name, s.gender, s.date_of_birth,
       s.contact_number, s.email, s.admission_year, s.hostel_status, s.status
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.register_number = '71762233001';""",
        "tags": ["students", "lookup"],
    },
    {
        "question": "Show contact details of all students",
        "sql": """\
SELECT s.register_number, s.name, s.contact_number, s.email
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
ORDER BY s.name
LIMIT 100;""",
        "tags": ["students", "contact"],
    },
    {
        "question": "Can you retrieve all the relevant information regarding Bhavatharini C?",
        "sql": """\
SELECT s.register_number, s.name, s.gender, s.date_of_birth,
       s.contact_number, s.email, s.admission_year, s.section,
       s.hostel_status, s.status, s.cgpa,
       (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
       + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END AS current_semester
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.name ILIKE '%Bhavatharini C%'
LIMIT 20;""",
        "tags": ["students", "profile", "lookup", "name"],
    },
    {
        "question": "Can you retrieve all the relevant information regarding Bhavatharaini?",
        "sql": """\
SELECT s.register_number, s.name, s.gender, s.date_of_birth,
       s.contact_number, s.email, s.admission_year, s.section,
       s.hostel_status, s.status, s.cgpa,
       (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
       + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END AS current_semester
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.name ILIKE '%Bhavatharaini%'
LIMIT 20;""",
        "tags": ["students", "profile", "lookup", "name", "misspelling"],
    },
  {
    "question": "Show parent phone numbers of Ruban S in 8th semester",
    "sql": """\
SELECT s.register_number, s.name,
     p.father_name, p.father_contact_number,
     p.mother_name, p.mother_contact_number
FROM students s
JOIN parents p ON p.student_id = s.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND LOWER(s.name) LIKE LOWER('%Ruban S%')
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 8
ORDER BY s.register_number;""",
    "tags": ["students", "parents", "contact", "semester"],
  },
  {
    "question": "Can you fetch parents phone number of Surya and Ann in 8th sem students?",
    "sql": """\
SELECT s.register_number, s.name,
     p.father_name, p.father_contact_number,
     p.mother_name, p.mother_contact_number
FROM students s
JOIN parents p ON p.student_id = s.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND (
    LOWER(s.name) LIKE LOWER('%surya%')
    OR LOWER(s.name) LIKE LOWER('%ann%')
  )
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 8
ORDER BY s.register_number;""",
    "tags": ["students", "parents", "contact", "semester", "multi-name"],
  },
  {
    "question": "Get father and mother contact numbers for Ruban S, Surya, Ann, Saran from 8th semester",
    "sql": """\
SELECT s.register_number, s.name,
     p.father_name, p.father_contact_number,
     p.mother_name, p.mother_contact_number
FROM students s
JOIN parents p ON p.student_id = s.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND (
    LOWER(s.name) LIKE LOWER('%ruban%')
    OR LOWER(s.name) LIKE LOWER('%surya%')
    OR LOWER(s.name) LIKE LOWER('%ann%')
    OR LOWER(s.name) LIKE LOWER('%saran%')
  )
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 8
ORDER BY s.register_number
LIMIT 100;""",
    "tags": ["students", "parents", "contact", "semester", "multi-name"],
  },
    {
        "question": "How many students graduated?",
        "sql": """\
SELECT COUNT(*) AS graduated_count
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Graduated';""",
        "tags": ["students", "status", "graduated"],
    },

    # ══════════════════════════════════════════════════════════
    # GPA / ACADEMIC PERFORMANCE
    # ══════════════════════════════════════════════════════════
    {
        "question": "What is the average GPA of students?",
        "sql": """\
SELECT ROUND(AVG(g.gpa)::numeric, 2) AS dept_avg_gpa
FROM student_semester_gpa g
JOIN students s ON s.student_id = g.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}';""",
        "tags": ["gpa", "average"],
    },
    {
        "question": "Who are the top 10 students by CGPA?",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year,
       ROUND(AVG(g.gpa)::numeric, 2) AS cgpa
FROM students s
JOIN departments d ON s.department_id = d.department_id
JOIN student_semester_gpa g ON g.student_id = s.student_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
GROUP BY s.student_id, s.register_number, s.name, s.admission_year
ORDER BY cgpa DESC
LIMIT 10;""",
        "tags": ["gpa", "top", "rank"],
    },
    {
        "question": "Show GPA of all semesters for student 71762233001",
        "sql": """\
SELECT g.semester_number, g.gpa, g.cgpa_upto
FROM student_semester_gpa g
JOIN students s ON s.student_id = g.student_id
WHERE s.register_number = '71762233001'
ORDER BY g.semester_number;""",
        "tags": ["gpa", "student", "history"],
    },
    {
        "question": "Which students have CGPA below 6?",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year,
       ROUND(AVG(g.gpa)::numeric, 2) AS cgpa
FROM students s
JOIN departments d ON s.department_id = d.department_id
JOIN student_semester_gpa g ON g.student_id = s.student_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
GROUP BY s.student_id, s.register_number, s.name, s.admission_year
HAVING AVG(g.gpa) < 6
ORDER BY cgpa ASC
LIMIT 100;""",
        "tags": ["gpa", "low", "filter"],
    },
    {
        "question": "What is the average GPA for 4th semester?",
        "sql": """\
SELECT ROUND(AVG(g.gpa)::numeric, 2) AS avg_gpa
FROM student_semester_gpa g
JOIN students s ON s.student_id = g.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND g.semester_number = 4;""",
        "tags": ["gpa", "semester", "average"],
    },
    {
        "question": "Show semester-wise average GPA trend",
        "sql": """\
SELECT g.semester_number,
       ROUND(AVG(g.gpa)::numeric, 2) AS avg_gpa,
       COUNT(DISTINCT g.student_id)  AS students_count
FROM student_semester_gpa g
JOIN students s ON s.student_id = g.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
GROUP BY g.semester_number
ORDER BY g.semester_number;""",
        "tags": ["gpa", "semester", "trend"],
    },
    {
        "question": "List students who scored above 9 GPA in any semester",
        "sql": """\
SELECT DISTINCT s.register_number, s.name, g.semester_number, g.gpa
FROM students s
JOIN departments d ON s.department_id = d.department_id
JOIN student_semester_gpa g ON g.student_id = s.student_id
WHERE d.department_code = '{DEPT}'
  AND g.gpa > 9
ORDER BY g.gpa DESC
LIMIT 100;""",
        "tags": ["gpa", "high", "distinction"],
    },

    # ══════════════════════════════════════════════════════════
    # ARREARS
    # ══════════════════════════════════════════════════════════
    {
        "question": "How many students have active arrears?",
        "sql": """\
SELECT COUNT(DISTINCT a.student_id) AS students_with_arrears
FROM (
    SELECT student_id, subject_id, grade,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month = 'NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
) a
JOIN students s ON s.student_id = a.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE a.rn = 1
  AND a.grade IN ('U', 'AB')
  AND d.department_code = '{DEPT}';""",
        "tags": ["arrears", "count"],
    },
    {
        "question": "Which students have more than 2 active arrears?",
        "sql": """\
SELECT s.register_number, s.name, s.admission_year,
       COUNT(*) AS active_arrear_count
FROM (
    SELECT student_id, subject_id, grade,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month = 'NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
) latest
JOIN students s ON s.student_id = latest.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE latest.rn = 1
  AND latest.grade IN ('U', 'AB')
  AND d.department_code = '{DEPT}'
GROUP BY s.student_id, s.register_number, s.name, s.admission_year
HAVING COUNT(*) > 2
ORDER BY active_arrear_count DESC;""",
        "tags": ["arrears", "multiple", "filter"],
    },
  {
    "question": "Which 8th semester students have active arrears?",
    "sql": """\
SELECT s.register_number, s.name, s.admission_year,
     (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
     + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END AS current_semester,
     COUNT(*) AS active_arrear_count
FROM (
  SELECT student_id, subject_id, grade,
       ROW_NUMBER() OVER (
         PARTITION BY student_id, subject_id
         ORDER BY exam_year DESC,
            CASE WHEN exam_month = 'NOV' THEN 2 ELSE 1 END DESC
       ) AS rn
  FROM student_subject_attempts
) latest
JOIN students s ON s.student_id = latest.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE latest.rn = 1
  AND latest.grade IN ('U', 'AB')
  AND d.department_code = '{DEPT}'
  AND s.status = 'Active'
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 8
GROUP BY s.student_id, s.register_number, s.name, s.admission_year
ORDER BY active_arrear_count DESC, s.register_number;""",
    "tags": ["arrears", "semester", "active", "current_semester"],
  },
  {
    "question": "How many 8th semester students have active arrears?",
    "sql": """\
SELECT COUNT(DISTINCT s.student_id) AS students_with_arrears
FROM (
  SELECT student_id, subject_id, grade,
       ROW_NUMBER() OVER (
         PARTITION BY student_id, subject_id
         ORDER BY exam_year DESC,
            CASE WHEN exam_month = 'NOV' THEN 2 ELSE 1 END DESC
       ) AS rn
  FROM student_subject_attempts
) latest
JOIN students s ON s.student_id = latest.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE latest.rn = 1
  AND latest.grade IN ('U', 'AB')
  AND d.department_code = '{DEPT}'
  AND s.status = 'Active'
  AND (EXTRACT(YEAR FROM CURRENT_DATE)::int - s.admission_year) * 2
    + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END = 8;""",
    "tags": ["arrears", "count", "semester", "current_semester"],
  },
    {
        "question": "Show all active arrear subjects for student 71762233015",
        "sql": """\
SELECT sub.subject_code, sub.subject_name, sub.semester_number,
       a.exam_year, a.exam_month, a.grade
FROM (
    SELECT student_id, subject_id, grade, exam_year, exam_month,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month = 'NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
) a
JOIN students s   ON s.student_id   = a.student_id
JOIN subjects sub ON sub.subject_id = a.subject_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.register_number = '71762233015'
  AND a.rn = 1
  AND a.grade IN ('U', 'AB')
ORDER BY sub.semester_number, sub.subject_code;""",
        "tags": ["arrears", "student", "subjects"],
    },
    {
        "question": "Which subject has the most arrears?",
        "sql": """\
SELECT sub.subject_code, sub.subject_name, sub.semester_number,
       COUNT(*) AS arrear_count
FROM (
    SELECT student_id, subject_id, grade,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month = 'NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
) a
JOIN subjects sub ON sub.subject_id = a.subject_id
JOIN students s   ON s.student_id   = a.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE a.rn = 1
  AND a.grade IN ('U', 'AB')
  AND d.department_code = '{DEPT}'
GROUP BY sub.subject_id, sub.subject_code, sub.subject_name, sub.semester_number
ORDER BY arrear_count DESC
LIMIT 10;""",
        "tags": ["arrears", "subject", "worst"],
    },
    {
        "question": "Show full exam history of student 71762233009",
        "sql": """\
SELECT sub.subject_code, sub.subject_name,
       a.exam_year, a.exam_month, a.grade,
       CASE WHEN a.grade IN ('U','AB') THEN 'Fail' ELSE 'Pass' END AS result
FROM student_subject_attempts a
JOIN students s   ON s.student_id   = a.student_id
JOIN subjects sub ON sub.subject_id = a.subject_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.register_number = '71762233009'
ORDER BY a.exam_year,
         CASE WHEN a.exam_month='MAY' THEN 1 ELSE 2 END,
         sub.subject_code;""",
        "tags": ["arrears", "history", "student"],
    },
    {
        "question": "How many students cleared their arrear in NOV 2024?",
        "sql": """\
SELECT COUNT(DISTINCT a.student_id) AS cleared_count
FROM student_subject_attempts a
JOIN students s   ON s.student_id   = a.student_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND a.exam_year  = 2024
  AND a.exam_month = 'NOV'
  AND a.grade NOT IN ('U', 'AB');""",
        "tags": ["arrears", "cleared", "history"],
    },
    {
        "question": "List students who failed in subject 22MDC41",
        "sql": """\
SELECT s.register_number, s.name,
       a.exam_year, a.exam_month, a.grade
FROM student_subject_attempts a
JOIN students s   ON s.student_id   = a.student_id
JOIN subjects sub ON sub.subject_id = a.subject_id
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND sub.subject_code = '22MDC41'
  AND a.grade IN ('U', 'AB')
ORDER BY a.exam_year DESC, a.exam_month;""",
        "tags": ["arrears", "subject", "fail"],
    },

    # ══════════════════════════════════════════════════════════
    # FACULTY
    # ══════════════════════════════════════════════════════════
    {
        "question": "List all faculty members",
        "sql": """\
SELECT f.title, f.full_name, f.designation, f.email, f.phone
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND f.is_active = TRUE
ORDER BY f.full_name;""",
        "tags": ["faculty", "list"],
    },
    {
        "question": "How many faculty members are there?",
        "sql": """\
SELECT COUNT(*) AS total_faculty
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND f.is_active = TRUE;""",
        "tags": ["faculty", "count"],
    },
    {
        "question": "Who is the HOD?",
        "sql": """\
SELECT f.title, f.full_name, f.email, f.phone
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND f.is_hod = TRUE;""",
        "tags": ["faculty", "hod"],
    },
    {
        "question": "List all assistant professors",
        "sql": """\
SELECT f.title, f.full_name, f.email, f.phone
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND f.designation = 'Assistant Professor'
  AND f.is_active = TRUE
ORDER BY f.full_name;""",
        "tags": ["faculty", "designation"],
    },
    {
        "question": "Which subjects does Dr. Yamuna teach?",
        "sql": """\
SELECT DISTINCT sub.subject_code, sub.subject_name,
                sub.semester_number, sub.subject_type,
                ft.day_of_week, ts.hour_number
FROM faculty_timetable ft
JOIN faculty    f   ON ft.faculty_id  = f.faculty_id
JOIN departments d  ON f.department_id = d.department_id
JOIN subjects   sub ON ft.subject_id  = sub.subject_id
JOIN time_slots ts  ON ft.slot_id     = ts.slot_id
WHERE d.department_code = '{DEPT}'
  AND f.full_name ILIKE '%Yamuna%'
ORDER BY sub.semester_number, sub.subject_code;""",
        "tags": ["faculty", "subjects", "timetable"],
    },
    {
        "question": "What are all the subjects Dr. Manju is currently handling?",
        "sql": """\
    SELECT DISTINCT sub.subject_code, sub.subject_name,
        sub.semester_number, sub.subject_type
FROM faculty_timetable ft
JOIN faculty    f   ON ft.faculty_id  = f.faculty_id
JOIN departments d  ON f.department_id = d.department_id
JOIN subjects   sub ON ft.subject_id  = sub.subject_id
WHERE d.department_code = '{DEPT}'
  AND f.full_name ILIKE '%Manju%'
ORDER BY sub.semester_number, sub.subject_code;""",
      "tags": ["faculty", "subjects", "current"],
    },
    {
        "question": "Which subjects are currently handled by Dr. Manju?",
        "sql": """\
    SELECT DISTINCT sub.subject_code, sub.subject_name,
        sub.semester_number, sub.subject_type
FROM faculty_timetable ft
JOIN faculty    f   ON ft.faculty_id  = f.faculty_id
JOIN departments d  ON f.department_id = d.department_id
JOIN subjects   sub ON ft.subject_id  = sub.subject_id
WHERE d.department_code = '{DEPT}'
  AND f.full_name ILIKE '%Manju%'
ORDER BY sub.semester_number, sub.subject_code;""",
      "tags": ["faculty", "subjects", "current"],
    },
        {
      "question": "Which subjects does Dr. Yamuna currently handle?",
      "sql": """\
    SELECT DISTINCT sub.subject_code, sub.subject_name,
        sub.semester_number, sub.subject_type
    FROM faculty_timetable ft
    JOIN faculty    f   ON ft.faculty_id  = f.faculty_id
    JOIN departments d  ON f.department_id = d.department_id
    JOIN subjects   sub ON ft.subject_id  = sub.subject_id
    WHERE d.department_code = '{DEPT}'
      AND f.full_name ILIKE '%Yamuna%'
    ORDER BY sub.semester_number, sub.subject_code;""",
      "tags": ["faculty", "subjects", "current"],
        },
    {
        "question": "Show the timetable of Dr. Aruna",
        "sql": """\
SELECT ft.day_of_week, ts.hour_number, ts.start_time, ts.end_time,
       sub.subject_code, sub.subject_name, ft.sem_batch, ft.activity
FROM faculty_timetable ft
JOIN faculty    f   ON ft.faculty_id  = f.faculty_id
JOIN departments d  ON f.department_id = d.department_id
JOIN time_slots ts  ON ft.slot_id     = ts.slot_id
LEFT JOIN subjects sub ON ft.subject_id = sub.subject_id
WHERE d.department_code = '{DEPT}'
  AND f.full_name ILIKE '%Aruna%'
ORDER BY
  CASE ft.day_of_week WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                      WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 END,
  ts.hour_number;""",
        "tags": ["faculty", "timetable", "schedule"],
    },
    {
        "question": "Which faculty are free on Monday hour 3?",
        "sql": """\
SELECT f.title, f.full_name, f.designation
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND f.is_active = TRUE
  AND f.faculty_id NOT IN (
      SELECT ft.faculty_id
      FROM faculty_timetable ft
      JOIN time_slots ts ON ft.slot_id = ts.slot_id
      WHERE ft.day_of_week = 'Mon'
        AND ts.hour_number = 3
  )
ORDER BY f.full_name;""",
        "tags": ["faculty", "free", "timetable"],
    },
    {
        "question": "Which faculty are free on Wednesday hour 5?",
        "sql": """\
SELECT f.title, f.full_name, f.designation
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND f.is_active = TRUE
  AND f.faculty_id NOT IN (
      SELECT ft.faculty_id
      FROM faculty_timetable ft
      JOIN time_slots ts ON ft.slot_id = ts.slot_id
      WHERE ft.day_of_week = 'Wed'
        AND ts.hour_number = 5
  )
ORDER BY f.full_name;""",
        "tags": ["faculty", "free", "timetable"],
    },
  {
    "question": "When is Dr. A.Kannammal free on Monday?",
    "sql": """\
SELECT 'Mon' AS day_of_week, ts.hour_number, ts.start_time, ts.end_time,
     'FREE' AS activity
FROM time_slots ts
WHERE NOT EXISTS (
  SELECT 1
  FROM faculty_timetable ft
  JOIN faculty f   ON ft.faculty_id = f.faculty_id
  JOIN departments d ON f.department_id = d.department_id
  WHERE d.department_code = '{DEPT}'
    AND f.full_name ILIKE '%A.Kannammal%'
    AND ft.day_of_week = 'Mon'
    AND ft.slot_id = ts.slot_id
)
ORDER BY ts.hour_number;""",
    "tags": ["faculty", "free", "timetable", "day"],
  },
  {
    "question": "Is Dr. A.Kannammal free on Monday 3rd hour?",
    "sql": """\
SELECT CASE WHEN NOT EXISTS (
  SELECT 1
  FROM faculty_timetable ft
  JOIN faculty f   ON ft.faculty_id = f.faculty_id
  JOIN departments d ON f.department_id = d.department_id
  JOIN time_slots ts ON ft.slot_id = ts.slot_id
  WHERE d.department_code = '{DEPT}'
    AND f.full_name ILIKE '%A.Kannammal%'
    AND ft.day_of_week = 'Mon'
    AND ts.hour_number = 3
) THEN 'Yes' ELSE 'No' END AS is_free;""",
    "tags": ["faculty", "free", "timetable", "hour"],
  },
  {
    "question": "Show free periods for Dr. A.Kannammal on Tuesday",
    "sql": """\
SELECT 'Tue' AS day_of_week, ts.hour_number, ts.start_time, ts.end_time,
     'FREE' AS activity
FROM time_slots ts
WHERE NOT EXISTS (
  SELECT 1
  FROM faculty_timetable ft
  JOIN faculty f   ON ft.faculty_id = f.faculty_id
  JOIN departments d ON f.department_id = d.department_id
  WHERE d.department_code = '{DEPT}'
    AND f.full_name ILIKE '%A.Kannammal%'
    AND ft.day_of_week = 'Tue'
    AND ft.slot_id = ts.slot_id
)
ORDER BY ts.hour_number;""",
    "tags": ["faculty", "free", "timetable", "day"],
  },
    {
        "question": "Which faculty teach in 4th semester?",
        "sql": """\
SELECT DISTINCT f.title, f.full_name, f.designation,
                sub.subject_code, sub.subject_name
FROM faculty_timetable ft
JOIN faculty    f   ON ft.faculty_id   = f.faculty_id
JOIN subjects   sub ON ft.subject_id   = sub.subject_id
JOIN departments d  ON f.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND ft.sem_batch = 4
ORDER BY f.full_name;""",
        "tags": ["faculty", "semester", "timetable"],
    },
    {
        "question": "How many hours does each faculty teach per week?",
        "sql": """\
SELECT f.title, f.full_name, f.designation,
       COUNT(ft.id) AS weekly_teaching_hours
FROM faculty f
JOIN departments d ON f.department_id = d.department_id
LEFT JOIN faculty_timetable ft ON ft.faculty_id = f.faculty_id
                               AND ft.subject_id IS NOT NULL
WHERE d.department_code = '{DEPT}'
  AND f.is_active = TRUE
GROUP BY f.faculty_id, f.title, f.full_name, f.designation
ORDER BY weekly_teaching_hours DESC;""",
        "tags": ["faculty", "workload"],
    },
    {
        "question": "Who teaches Predictive Analytics?",
        "sql": """\
SELECT DISTINCT f.title, f.full_name, ft.sem_batch
FROM faculty_timetable ft
JOIN faculty    f   ON ft.faculty_id  = f.faculty_id
JOIN departments d  ON f.department_id = d.department_id
JOIN subjects   sub ON ft.subject_id  = sub.subject_id
WHERE d.department_code = '{DEPT}'
  AND sub.subject_name ILIKE '%Predictive Analytics%'
ORDER BY f.full_name;""",
        "tags": ["faculty", "subject", "who_teaches"],
    },

    # ══════════════════════════════════════════════════════════
    # TIMETABLE / CLASS SCHEDULE
    # ══════════════════════════════════════════════════════════
    {
        "question": "Show the class timetable for 4th semester",
        "sql": """\
SELECT ct.day_of_week, ct.hour_number,
       sub.subject_code, sub.subject_name, sub.subject_type,
       f.title || ' ' || f.full_name AS faculty_name,
       ct.activity
FROM class_timetable ct
JOIN departments d   ON ct.department_id = d.department_id
LEFT JOIN subjects sub ON sub.subject_id = ct.subject_id
LEFT JOIN faculty  f   ON f.faculty_id   = ct.faculty_id
WHERE d.department_code = '{DEPT}'
  AND ct.sem_batch = 4
ORDER BY
  CASE ct.day_of_week WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
                       WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 END,
  ct.hour_number;""",
        "tags": ["timetable", "class", "semester"],
    },
    {
        "question": "What subject is taught on Monday hour 2 for 6th semester?",
        "sql": """\
SELECT sub.subject_code, sub.subject_name, sub.subject_type,
       f.title || ' ' || f.full_name AS faculty_name
FROM class_timetable ct
JOIN departments d   ON ct.department_id = d.department_id
LEFT JOIN subjects sub ON sub.subject_id = ct.subject_id
LEFT JOIN faculty  f   ON f.faculty_id   = ct.faculty_id
WHERE d.department_code = '{DEPT}'
  AND ct.sem_batch   = 6
  AND ct.day_of_week = 'Mon'
  AND ct.hour_number = 2;""",
        "tags": ["timetable", "class", "slot"],
    },
    {
        "question": "Who is handling subject 22MDC81 for 8th semester students?",
        "sql": """\
SELECT DISTINCT sub.subject_code, sub.subject_name,
       ct.sem_batch, ct.day_of_week, ct.hour_number,
       f.title || ' ' || f.full_name AS faculty_name
FROM class_timetable ct
JOIN departments d ON ct.department_id = d.department_id
JOIN subjects sub ON ct.subject_id = sub.subject_id
LEFT JOIN faculty f ON ct.faculty_id = f.faculty_id
WHERE d.department_code = '{DEPT}'
  AND ct.sem_batch = 8
  AND sub.subject_code = '22MDC81'
ORDER BY ct.day_of_week, ct.hour_number;""",
        "tags": ["timetable", "class", "subject", "faculty", "semester"],
    },
    {
        "question": "Show all practical labs scheduled this week",
        "sql": """\
SELECT ct.sem_batch, ct.day_of_week, ct.hour_number,
       sub.subject_code, sub.subject_name,
       f.title || ' ' || f.full_name AS faculty_name
FROM class_timetable ct
JOIN departments d   ON ct.department_id = d.department_id
JOIN subjects sub    ON sub.subject_id   = ct.subject_id
LEFT JOIN faculty f  ON f.faculty_id     = ct.faculty_id
WHERE d.department_code = '{DEPT}'
  AND sub.subject_type IN ('Practical', 'Elective Practical')
ORDER BY ct.sem_batch, ct.day_of_week, ct.hour_number;""",
        "tags": ["timetable", "practical", "lab"],
    },

    # ══════════════════════════════════════════════════════════
    # SUBJECTS
    # ══════════════════════════════════════════════════════════
    {
        "question": "List all subjects in 4th semester",
        "sql": """\
SELECT subject_code, subject_name, subject_type,
       lecture_hrs, tutorial_hrs, practical_hrs, credits
FROM subjects
WHERE semester_number = 4
  AND department_id = (
      SELECT department_id FROM departments WHERE department_code = '{DEPT}'
  )
ORDER BY subject_code;""",
        "tags": ["subjects", "semester", "list"],
    },
    {
        "question": "How many theory subjects are there in 6th semester?",
        "sql": """\
SELECT COUNT(*) AS theory_count
FROM subjects
WHERE semester_number = 6
  AND subject_type = 'Theory'
  AND department_id = (
      SELECT department_id FROM departments WHERE department_code = '{DEPT}'
  );""",
        "tags": ["subjects", "theory", "count"],
    },
    {
        "question": "List all elective subjects",
        "sql": """\
SELECT subject_code, subject_name, semester_number, credits
FROM subjects
WHERE subject_type IN ('Elective', 'Elective Practical')
  AND department_id = (
      SELECT department_id FROM departments WHERE department_code = '{DEPT}'
  )
ORDER BY semester_number, subject_code;""",
        "tags": ["subjects", "elective"],
    },
    {
        "question": "What is the total credit load for 4th semester?",
        "sql": """\
SELECT SUM(credits) AS total_credits
FROM subjects
WHERE semester_number = 4
  AND department_id = (
      SELECT department_id FROM departments WHERE department_code = '{DEPT}'
  );""",
        "tags": ["subjects", "credits", "semester"],
    },

    # ══════════════════════════════════════════════════════════
    # SUMMARY / DASHBOARD
    # ══════════════════════════════════════════════════════════
    {
        "question": "Give me a summary of the department",
        "sql": """\
SELECT
    (SELECT COUNT(*) FROM students s JOIN departments d ON s.department_id = d.department_id
     WHERE d.department_code = '{DEPT}' AND s.status = 'Active')        AS active_students,
    (SELECT COUNT(*) FROM students s JOIN departments d ON s.department_id = d.department_id
     WHERE d.department_code = '{DEPT}' AND s.hostel_status = 'Hosteller'
       AND s.status = 'Active')                                          AS hostellers,
    (SELECT COUNT(*) FROM faculty f JOIN departments d ON f.department_id = d.department_id
     WHERE d.department_code = '{DEPT}' AND f.is_active = TRUE)         AS total_faculty,
    (SELECT ROUND(AVG(g.gpa)::numeric,2)
     FROM student_semester_gpa g
     JOIN students s ON s.student_id = g.student_id
     JOIN departments d ON s.department_id = d.department_id
     WHERE d.department_code = '{DEPT}')                                 AS avg_gpa;""",
        "tags": ["summary", "dashboard"],
    },
    {
        "question": "How many students are in each batch?",
        "sql": """\
SELECT s.admission_year, s.status, COUNT(*) AS count
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
GROUP BY s.admission_year, s.status
ORDER BY s.admission_year DESC, s.status;""",
        "tags": ["students", "batch", "summary"],
    },

    # ══════════════════════════════════════════════════════════
    # COMBINED / COMPLEX QUERIES
    # ══════════════════════════════════════════════════════════
    {
        "question": "Which active students have both arrears and CGPA below 6?",
        "sql": """\
WITH latest AS (
    SELECT student_id, subject_id, grade,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month='NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
),
arrear_students AS (
    SELECT student_id, COUNT(*) AS arrear_count
    FROM latest
    WHERE rn = 1 AND grade IN ('U','AB')
    GROUP BY student_id
),
low_gpa AS (
    SELECT student_id, ROUND(AVG(gpa)::numeric,2) AS cgpa
    FROM student_semester_gpa
    GROUP BY student_id
    HAVING AVG(gpa) < 6
)
SELECT s.register_number, s.name, s.admission_year,
       a.arrear_count, l.cgpa
FROM students s
JOIN departments d ON s.department_id = d.department_id
JOIN arrear_students a ON a.student_id = s.student_id
JOIN low_gpa        l ON l.student_id  = s.student_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
ORDER BY a.arrear_count DESC, l.cgpa ASC;""",
        "tags": ["arrears", "gpa", "at_risk", "combined"],
    },
    {
        "question": "Show me students who are hostellers and have arrears",
        "sql": """\
WITH latest AS (
    SELECT student_id, subject_id, grade,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month='NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
)
SELECT DISTINCT s.register_number, s.name, s.admission_year,
       COUNT(*) OVER (PARTITION BY s.student_id) AS active_arrear_count
FROM students s
JOIN departments d ON s.department_id = d.department_id
JOIN latest l ON l.student_id = s.student_id
WHERE d.department_code = '{DEPT}'
  AND s.hostel_status = 'Hosteller'
  AND s.status = 'Active'
  AND l.rn = 1
  AND l.grade IN ('U','AB')
ORDER BY active_arrear_count DESC;""",
        "tags": ["students", "hostel", "arrears", "combined"],
    },
    {
        "question": "Which 2022 batch students have no arrears?",
        "sql": """\
WITH latest AS (
    SELECT student_id, subject_id, grade,
           ROW_NUMBER() OVER (
               PARTITION BY student_id, subject_id
               ORDER BY exam_year DESC,
                        CASE WHEN exam_month='NOV' THEN 2 ELSE 1 END DESC
           ) AS rn
    FROM student_subject_attempts
),
students_with_arrears AS (
    SELECT DISTINCT student_id
    FROM latest
    WHERE rn = 1 AND grade IN ('U','AB')
)
SELECT s.register_number, s.name, s.hostel_status
FROM students s
JOIN departments d ON s.department_id = d.department_id
WHERE d.department_code = '{DEPT}'
  AND s.admission_year  = 2022
  AND s.status          = 'Active'
  AND s.student_id NOT IN (SELECT student_id FROM students_with_arrears)
ORDER BY s.register_number;""",
        "tags": ["students", "arrears", "clean", "batch"],
    },
    {
        "question": "Compare hosteller vs day scholar average GPA",
        "sql": """\
SELECT s.hostel_status,
       ROUND(AVG(g.gpa)::numeric, 2) AS avg_gpa,
       COUNT(DISTINCT s.student_id)  AS student_count
FROM students s
JOIN departments d ON s.department_id = d.department_id
JOIN student_semester_gpa g ON g.student_id = s.student_id
WHERE d.department_code = '{DEPT}'
  AND s.status = 'Active'
GROUP BY s.hostel_status
ORDER BY avg_gpa DESC;""",
        "tags": ["gpa", "hostel", "compare"],
    },
]

# ── Quick sanity check ──────────────────────────────────────────────────────
if __name__ == "__main__":
    tags: dict[str, int] = {}
    for ex in FEW_SHOTS:
        for t in ex["tags"]:
            tags[t] = tags.get(t, 0) + 1
        # Verify {DEPT} placeholder is present in every sql that should be dept-scoped
        if "department_code" in ex["sql"] and "{DEPT}" not in ex["sql"]:
            print(f"WARNING: missing {{DEPT}} placeholder in: {ex['question'][:60]}")
    print(f"Total examples : {len(FEW_SHOTS)}")
    print("Tag distribution:")
    for t, c in sorted(tags.items(), key=lambda x: -x[1]):
        print(f"  {t:30s} {c}")