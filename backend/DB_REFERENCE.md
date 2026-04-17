# Database Schema Reference

*Auto-generated from PostgreSQL live schema.*

## 1. Core Tables

### `departments`
- `department_id` (PK) - Integer
- `department_code` - VARCHAR(10) (e.g., 'DCS', 'ECE')
- `department_name` - VARCHAR(100)
- `created_at` - TIMESTAMP

### `users`
- `user_id` (PK) - Integer
- `username` - VARCHAR(255)
- `password` - VARCHAR(255)
- `role` - VARCHAR(50) (e.g., 'hod', 'staff', 'admin')
- `department_code` - VARCHAR(50) — Used for scoping data access

### `time_slots`
- `slot_id` (PK) - Integer
- `hour_number` - SMALLINT (e.g., 1, 2, 3 ... 8) — Represents the period/hour of the day
- `start_time` - TIME
- `end_time` - TIME
- `label` - VARCHAR(20)

---

## 2. Students & Academics

### `students`
- `student_id` (PK) - Integer
- `register_number` - VARCHAR(20) (Unique identifier)
- `name` - VARCHAR(100)
- `gender` - VARCHAR(10)
- `date_of_birth` - DATE
- `contact_number` - VARCHAR(15)
- `email` - VARCHAR(100)
- `department_id` (FK -> departments)
- `admission_year` - Integer (e.g., 2021) — Used to calculate current semester
- `section` - VARCHAR(10)
- `hostel_status` - VARCHAR(20) ('Day Scholar' or 'Hosteller')
- `status` - VARCHAR(20) ('Active', 'Graduated', 'Dropout')
- `cgpa` - NUMERIC (Overall CGPA)
- `created_at` - TIMESTAMP

### `parents`
- `parent_id` (PK) - Integer
- `student_id` (FK -> students)
- `father_name` - VARCHAR(100)
- `mother_name` - VARCHAR(100)
- `father_contact_number` - VARCHAR(15)
- `mother_contact_number` - VARCHAR(15)
- `address` - TEXT

### `subjects`
- `subject_id` (PK) - Integer
- `subject_code` - VARCHAR(20)
- `subject_name` - VARCHAR(150)
- `department_id` (FK -> departments)
- `semester_number` - Integer (The semester this subject is taught in)
- `subject_type` - VARCHAR(50) (e.g., 'Theory', 'Practical')
- `lecture_hrs` - Integer (Default 0)
- `tutorial_hrs` - Integer (Default 0)
- `practical_hrs` - Integer (Default 0)
- `credits` - Integer (Default 0)

### `student_semester_gpa`
- `student_id` (PK) (FK -> students)
- `semester_number` (PK) - Integer
- `gpa` - NUMERIC (GPA for this specific semester)
- `total_credits` - Integer (NOTE: There is NO `cgpa_upto` column)

### `student_subject_attempts`
- `attempt_id` (PK) - Integer
- `student_id` (FK -> students)
- `subject_id` (FK -> subjects)
- `exam_year` - Integer
- `exam_month` - VARCHAR(10) (e.g., 'NOV', 'MAY')
- `grade` - VARCHAR(5) (e.g., 'O', 'A+', 'A', 'B+', 'B', 'C', 'U', 'AB')
- *Note*: 'U' and 'AB' indicate a fail/arrear.

### `student_subject_results`
- `id` (PK) - Integer
- `student_id` (FK -> students)
- `subject_id` (FK -> subjects)
- `semester_number` - Integer
- `grade` - VARCHAR(2)
- `exam_year` - Integer
- `exam_month` - VARCHAR(10)

---

## 3. Faculty & Timetables

### `faculty`
- `faculty_id` (PK) - Integer
- `title` - VARCHAR(10) (e.g., 'Dr.', 'Mr.')
- `full_name` - VARCHAR(150)
- `email` - VARCHAR(150)
- `phone` - VARCHAR(15)
- `department_id` (FK -> departments)
- `designation` - VARCHAR(60)
- `is_hod` - BOOLEAN
- `is_active` - BOOLEAN
- *CRITICAL*: The `faculty` table has NO columns for time/scheduling (`day_of_week`, `slot_id`, `hour_number`).

### `faculty_timetable`
- `tt_id` (PK) - Integer
- `faculty_id` (FK -> faculty)
- `day_of_week` - VARCHAR(3) (e.g., 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')
- `slot_id` (FK -> time_slots)
- `subject_id` (FK -> subjects) (Nullable for non-academic activities)
- `activity` - VARCHAR(50)
- `sem_batch` - SMALLINT (The semester being taught)
- `department_id` (FK -> departments) - Copied from the class context

### `class_timetable`
- `id` (PK) - Integer
- `sem_batch` - Integer (The semester number)
- `day_of_week` - VARCHAR(10) ('Mon', 'Tue', etc.)
- `hour_number` - Integer
- `subject_id` (FK -> subjects)
- `faculty_id` (FK -> faculty)
- `activity` - VARCHAR(100)
- `department_id` (FK -> departments)
- `section` - VARCHAR(5)

---

## 4. System Tables

### `chat_messages`
- `id` (PK) - Integer
- `user_id` - VARCHAR(100)
- `session_id` - VARCHAR(100)
- `question` - TEXT
- `sql` - TEXT
- `response` - TEXT
- `results_json` - TEXT
- `result_count` - Integer
- `model_used` - VARCHAR(100)
- `confidence` - VARCHAR(20)
- `execution_ms` - Integer
- `error` - TEXT
- `department_code` - VARCHAR(20)
- `timestamp` - TIMESTAMP
- `intent` - VARCHAR(50) (Added in v2)
- `validation_errors` - JSONB (Added in v2)
- `referenced_entities` - JSONB

---

## 5. Views

### `vw_arrear_count`
- `register_number` - VARCHAR(20)
- `name` - VARCHAR(100)
- `status` - VARCHAR(20)
- `active_arrear_count` - BIGINT (Counts 'U' and 'AB' grades from `student_subject_attempts`)

### `vw_timetable`
   -- use class_timetable.id (not tt_id) and class_timetable.hour_number (not slot_id)
- `semester_number` - SMALLINT (`sem_batch`)

## Common SQL Pitfalls & Rules

1. **Timetable Lookups**: To finding out what a faculty teaches or when they are free, ALWAYS join `faculty_timetable` (alias `ft`) and `time_slots` (alias `ts`). Let `ts.hour_number` match the 1st/2nd/nth hour query.
2. **Faculty Aliasing**: DO NOT put `day_of_week` or `slot_id` on the `faculty` table (`f.day_of_week` is INVALID).
3. **Current Semester**: Compute using `admission_year`: `(EXTRACT(YEAR FROM CURRENT_DATE)::int - admission_year) * 2 + CASE WHEN EXTRACT(MONTH FROM CURRENT_DATE) >= 7 THEN 1 ELSE 0 END`.
4. **Primary Keys**:
   - `student_subject_attempts` PK is `attempt_id` (not `id`).
   - `faculty_timetable` PK is `tt_id` (not `id`).
5. **No `cgpa_upto`**: Do not use `cgpa_upto` in `student_semester_gpa`, use `gpa` and `total_credits`.
