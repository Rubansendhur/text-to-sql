=== TABLES & VIEWS ===
  BASE TABLE           chat_messages
  BASE TABLE           class_timetable
  BASE TABLE           departments
  BASE TABLE           faculty
  BASE TABLE           faculty_timetable
  BASE TABLE           parents
  BASE TABLE           student_semester_gpa
  BASE TABLE           student_subject_attempts
  BASE TABLE           student_subject_results
  BASE TABLE           students
  BASE TABLE           subjects
  BASE TABLE           time_slots
  BASE TABLE           users
  VIEW                 vw_arrear_count
  VIEW                 vw_student_gpa_summary
  VIEW                 vw_timetable

--- chat_messages ---
  id                                  integer           NOT NULL DEFAULT nextval('chat_messages_id_seq'::regclass)
  user_id                             character varying(100)      NOT NULL
  session_id                          character varying(100)      NOT NULL
  timestamp                           timestamp with time zone           NULL     DEFAULT CURRENT_TIMESTAMP
  question                            text           NOT NULL
  sql                                 text           NULL    
  response                            text           NOT NULL
  results_json                        text           NULL    
  result_count                        integer           NULL     DEFAULT 0
  model_used                          character varying(100)      NULL    
  confidence                          character varying(20)       NULL    
  execution_ms                        integer           NULL     DEFAULT 0
  error                               text           NULL    
  department_code                     character varying(20)       NULL    
  referenced_entities                 jsonb           NULL    

--- class_timetable ---
  id                                  integer           NOT NULL DEFAULT nextval('class_timetable_id_seq'::regclass)
  sem_batch                           integer           NOT NULL
  day_of_week                         character varying(10)       NOT NULL
  hour_number                         integer           NOT NULL
  subject_id                          integer           NULL    
  faculty_id                          integer           NULL    
  activity                            character varying(100)      NULL    
  department_id                       integer           NULL    
  section                             character varying(5)        NOT NULL DEFAULT 'A'::character varying

--- departments ---
  department_id                       integer           NOT NULL DEFAULT nextval('departments_department_id_seq'::regclass)
  department_code                     character varying(10)       NOT NULL
  department_name                     character varying(100)      NOT NULL
  created_at                          timestamp without time zone           NULL     DEFAULT CURRENT_TIMESTAMP

--- faculty ---
  faculty_id                          integer           NOT NULL DEFAULT nextval('faculty_faculty_id_seq'::regclass)
  title                               character varying(10)       NOT NULL DEFAULT 'Dr.'::character varying
  full_name                           character varying(150)      NOT NULL
  email                               character varying(150)      NULL    
  phone                               character varying(15)       NULL    
  department_id                       integer           NULL    
  designation                         character varying(60)       NULL     DEFAULT 'Assistant Professor'::character varying
  is_hod                              boolean           NULL     DEFAULT false
  is_active                           boolean           NULL     DEFAULT true
  created_at                          timestamp without time zone           NULL     DEFAULT CURRENT_TIMESTAMP

--- faculty_timetable ---
  tt_id                               integer           NOT NULL DEFAULT nextval('faculty_timetable_tt_id_seq'::regclass)
  faculty_id                          integer           NOT NULL
  day_of_week                         character varying(3)        NOT NULL
  slot_id                             integer           NOT NULL
  subject_id                          integer           NULL    
  activity                            character varying(50)       NULL    
  sem_batch                           smallint           NULL    
  updated_at                          timestamp without time zone           NULL     DEFAULT CURRENT_TIMESTAMP
  department_id                       integer           NULL    

--- parents ---
  parent_id                           integer           NOT NULL DEFAULT nextval('parents_parent_id_seq'::regclass)
  student_id                          integer           NOT NULL
  father_name                         character varying(100)      NULL    
  mother_name                         character varying(100)      NULL    
  father_contact_number               character varying(15)       NULL    
  mother_contact_number               character varying(15)       NULL    
  address                             text           NULL    

--- student_semester_gpa ---
  student_id                          integer           NOT NULL
  semester_number                     integer           NOT NULL
  gpa                                 numeric           NULL    
  total_credits                       integer           NULL    

--- student_subject_attempts ---
  attempt_id                          integer           NOT NULL DEFAULT nextval('student_subject_attempts_attempt_id_seq':
  student_id                          integer           NOT NULL
  subject_id                          integer           NOT NULL
  exam_year                           integer           NOT NULL
  exam_month                          character varying(10)       NOT NULL
  grade                               character varying(5)        NOT NULL
  created_at                          timestamp without time zone           NULL     DEFAULT CURRENT_TIMESTAMP

--- student_subject_results ---
  id                                  integer           NOT NULL DEFAULT nextval('student_subject_results_id_seq'::regclass
  student_id                          integer           NULL    
  subject_id                          integer           NULL    
  semester_number                     integer           NULL    
  grade                               character varying(2)        NULL    
  exam_year                           integer           NULL    
  exam_month                          character varying(10)       NULL    
  created_at                          timestamp without time zone           NULL     DEFAULT now()

--- students ---
  student_id                          integer           NOT NULL DEFAULT nextval('students_student_id_seq'::regclass)
  register_number                     character varying(20)       NOT NULL
  name                                character varying(100)      NOT NULL
  gender                              character varying(10)       NULL    
  date_of_birth                       date           NULL    
  contact_number                      character varying(15)       NULL    
  email                               character varying(100)      NULL    
  department_id                       integer           NOT NULL
  admission_year                      integer           NOT NULL
  section                             character varying(10)       NULL    
  hostel_status                       character varying(20)       NULL    
  status                              character varying(20)       NULL    
  created_at                          timestamp without time zone           NULL     DEFAULT CURRENT_TIMESTAMP
  cgpa                                numeric           NULL    

--- subjects ---
  subject_id                          integer           NOT NULL DEFAULT nextval('subjects_subject_id_seq'::regclass)
  subject_code                        character varying(20)       NOT NULL
  subject_name                        character varying(150)      NOT NULL
  department_id                       integer           NOT NULL
  semester_number                     integer           NULL    
  created_at                          timestamp without time zone           NULL     DEFAULT CURRENT_TIMESTAMP
  subject_type                        character varying(50)       NULL     DEFAULT 'Theory'::character varying
  lecture_hrs                         integer           NULL     DEFAULT 0
  tutorial_hrs                        integer           NULL     DEFAULT 0
  practical_hrs                       integer           NULL     DEFAULT 0
  credits                             integer           NULL     DEFAULT 0

--- time_slots ---
  slot_id                             integer           NOT NULL DEFAULT nextval('time_slots_slot_id_seq'::regclass)
  hour_number                         smallint           NOT NULL
  start_time                          time without time zone           NOT NULL
  end_time                            time without time zone           NOT NULL
  label                               character varying(20)       NULL    

--- users ---
  user_id                             integer           NOT NULL DEFAULT nextval('users_user_id_seq'::regclass)
  username                            character varying(255)      NOT NULL
  password                            character varying(255)      NOT NULL
  role                                character varying(50)       NOT NULL
  department_code                     character varying(50)       NULL     DEFAULT 'DCS'::character varying

--- vw_arrear_count ---
  register_number                     character varying(20)       NULL    
  name                                character varying(100)      NULL    
  status                              character varying(20)       NULL    
  active_arrear_count                 bigint           NULL    

--- vw_student_gpa_summary ---
  student_id                          integer           NULL    
  sems_completed                      integer           NULL    
  avg_gpa                             numeric           NULL    

--- vw_timetable ---
  day_of_week                         character varying(3)        NULL    
  hour_number                         smallint           NULL    
  time_range                          character varying(20)       NULL    
  code                                character varying(20)       NULL    
  subject                             character varying           NULL    
  subject_type                        text           NULL    
  faculty_name                        character varying(150)      NULL    
  lecture_hall                        text           NULL    
  notes                               text           NULL    
  semester_number                     smallint           NULL    

=== PRIMARY KEYS ===
  chat_messages                  PK: id
  class_timetable                PK: id
  departments                    PK: department_id
  faculty                        PK: faculty_id
  faculty_timetable              PK: tt_id
  parents                        PK: parent_id
  student_semester_gpa           PK: student_id
  student_semester_gpa           PK: semester_number
  student_subject_attempts       PK: attempt_id
  student_subject_results        PK: id
  students                       PK: student_id
  subjects                       PK: subject_id
  time_slots                     PK: slot_id
  users                          PK: user_id

=== FOREIGN KEYS ===
  class_timetable.department_id  -->  departments.department_id
  class_timetable.faculty_id  -->  faculty.faculty_id
  class_timetable.subject_id  -->  subjects.subject_id
  faculty.department_id  -->  departments.department_id
  faculty_timetable.slot_id  -->  time_slots.slot_id
  faculty_timetable.subject_id  -->  subjects.subject_id
  faculty_timetable.department_id  -->  departments.department_id
  faculty_timetable.faculty_id  -->  faculty.faculty_id
  parents.student_id  -->  students.student_id
  student_semester_gpa.student_id  -->  students.student_id
  student_subject_attempts.subject_id  -->  subjects.subject_id
  student_subject_attempts.student_id  -->  students.student_id
  student_subject_results.subject_id  -->  subjects.subject_id
  student_subject_results.student_id  -->  students.student_id
  students.department_id  -->  departments.department_id
  subjects.department_id  -->  departments.department_id

=== VIEW DEFINITIONS ===

-- VIEW: vw_arrear_count --
 WITH latest_attempts AS (
         SELECT student_subject_attempts.student_id,
            student_subject_attempts.subject_id,
            student_subject_attempts.grade,
            row_number() OVER (PARTITION BY student_subject_attempts.student_id, student_subject_attempts.subject_id ORDER BY student_subject_attempts.exam_year DESC,
                CASE
                    WHEN ((student_subject_attempts.exam_month)::text = 'NOV'::text) THEN 2
                    ELSE 1
                END DESC) AS rn
           FROM student_subject_attempts
        )
 SELECT s.register_number,
    s.name,
    s.status,
    count(
        CASE
            WHEN ((a.grade)::text = ANY ((ARRAY['U'::character varying, 'AB'::character varying])::text[])) THEN 1
            ELSE NULL::integer
        END) A

-- VIEW: vw_student_gpa_summary --
 SELECT student_id,
    0 AS sems_completed,
    0.0 AS avg_gpa
   FROM students;

-- VIEW: vw_timetable --
 SELECT ft.day_of_week,
    ts.hour_number,
    ts.label AS time_range,
    s.subject_code AS code,
    COALESCE(s.subject_name, ft.activity) AS subject,
        CASE
            WHEN (s.subject_id IS NOT NULL) THEN 'Theory'::text
            ELSE 'Activity'::text
        END AS subject_type,
    f.full_name AS faculty_name,
    'TBD'::text AS lecture_hall,
    ''::text AS notes,
    ft.sem_batch AS semester_number
   FROM (((faculty_timetable ft
     JOIN time_slots ts ON ((ft.slot_id = ts.slot_id)))
     LEFT JOIN subjects s ON ((ft.subject_id = s.subject_id)))
     JOIN faculty f ON ((ft.faculty_id = f.faculty_id)));

=== ROW COUNTS ===
  chat_messages                  35 rows
  class_timetable                35 rows
  departments                    4 rows
  faculty                        10 rows
  faculty_timetable              29 rows
  parents                        35 rows
  student_semester_gpa           35 rows
  student_subject_attempts       23 rows
  student_subject_results        224 rows
  students                       35 rows
  subjects                       44 rows
  time_slots                     7 rows
  users                          4 rows