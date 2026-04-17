import { useState, useRef } from 'react'
import { API_BASE } from '../lib/api.js'

const TYPES = [
  {
    value: 'students', label: 'Master Student Data', color: '#2d5be3', bg: '#eef2fc', border: '#c5d3f8',
    desc: 'Add or update student + parent records. Safe to re-upload anytime.',
    endpoint: '/api/upload/students',
    required: ['register_number','name','department_code','admission_year'],
    optional: ['gender','date_of_birth','contact_number','email','section','hostel_status','status','father_name','mother_name','father_contact_number','mother_contact_number','address'],
    notes: ['department_code → DCS or AIML','hostel_status → Day Scholar / Hosteller','status → Active / Graduated / Dropout','date_of_birth → DD/MM/YYYY'],
    sample: `register_number,name,gender,date_of_birth,contact_number,email,department_code,admission_year,hostel_status,status,father_name,mother_name
71762233001,ADITYA G,Male,29/12/2004,8838491019,aditya@cit.edu.in,DCS,2022,Day Scholar,Active,Ganesan,Meena
71762233002,ANEEZ I,Male,22/04/2004,9876543210,aneez@cit.edu.in,DCS,2022,Day Scholar,Active,Ibrahim,Fathima`,
  },
  {
    value: 'semester', label: 'Semester Exam Results', color: '#16a34a', bg: '#f0fdf4', border: '#86efac',
    desc: 'Upload after each semester result. Stores GPA is automatically calculated and auto-tracks U grades as arrears.',
    endpoint: '/api/upload/semester',
    required: ['register_number','semester','subject_code','grade'],
    optional: [],
    notes: ['One row per student = GPA only (Format A)','Multiple rows with subject_code+grade = full results (Format B)','Grade U is auto-stored as active arrear','Grades: O / A+ / A / B+ / B / C / U / AB'],
    sample: `register_number,semester,subject_code,grade
71762233001,4,22MDC41,A+
71762233001,4,22MDC42,O
71762233001,4,22MDC43,U
71762233002,4,22MDC41,A`,
  },
  {
    value: 'arrear', label: 'Arrear Exam Results', color: '#b45309', bg: '#fef3c7', border: '#fcd34d',
    desc: 'Upload after arrear exams. Include ALL grades — passed students auto-clear the arrear.',
    endpoint: '/api/upload/arrear',
    required: ['register_number','subject_code','exam_year','exam_month','grade'],
    optional: [],
    notes: ['exam_month → MAY or NOV','Upload BOTH passed and failed students','If latest grade ≠ U, arrear auto-clears','Full attempt history is always preserved'],
    sample: `register_number,subject_code,exam_year,exam_month,grade
71762233009,22MDC41,2026,NOV,A+
71762233015,22MDC41,2026,NOV,U
71762233022,22MDC42,2026,NOV,B`,
  },
  {
    value: 'faculty', label: 'Faculty Data', color: '#7c3aed', bg: '#f5f3ff', border: '#c4b5fd',
    desc: 'Add or update faculty records for the department.',
    endpoint: '/api/upload/faculty',
    required: ['title','full_name'],
    optional: ['email','phone','designation','is_hod','department_code'],
    notes: ['title → Dr. / Ms. / Mr. / Mrs. / Prof.','designation → Professor / Associate Professor / Assistant Professor','is_hod → true or false'],
    sample: `title,full_name,email,phone,designation,is_hod
Dr.,A.G.Aruna,aruna@cit.edu.in,9876543210,Assistant Professor,false
Ms.,K.Vani,vani@cit.edu.in,9876543211,Assistant Professor,false`,
  },
  {
    value: 'subjects', label: 'Subjects Master', color: '#0891b2', bg: '#ecfeff', border: '#a5f3fc',
    desc: 'Add or update the subject/course list.',
    endpoint: '/api/upload/subjects',
    required: ['subject_code','subject_name','department_code','semester_number'],
    optional: ['subject_type','lecture_hrs','tutorial_hrs','practical_hrs','credits'],
    notes: ['subject_type → Theory / Practical / Elective / Elective Practical','L T P C columns for credit structure'],
    sample: `subject_code,subject_name,department_code,semester_number,subject_type,lecture_hrs,tutorial_hrs,practical_hrs,credits
22MDC41,Predictive Analytics,DCS,4,Theory,3,0,0,3
22MDC46,Predictive Analytics Lab,DCS,4,Practical,0,0,4,2`,
  },
]

const card = { background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', padding: 24, marginBottom: 16 }

export default function Upload() {
  const [selected,   setSelected]   = useState('')
  const [file,       setFile]       = useState(null)
  const [status,     setStatus]     = useState('idle')
  const [result,     setResult]     = useState(null)
  const [showSample, setShowSample] = useState(false)
  const [dragOver,   setDragOver]   = useState(false)
  const inputRef = useRef(null)

  const ut = TYPES.find(t => t.value === selected)

  function pickFile(f) { setFile(f); setStatus('idle'); setResult(null) }

  function reset() {
    setFile(null); setStatus('idle'); setResult(null); setShowSample(false)
    if (inputRef.current) inputRef.current.value = ''
  }

  function handleTypeChange(val) { setSelected(val); reset() }

  async function upload() {
    if (!file || !ut) return
    setStatus('uploading'); setResult(null)
    const form = new FormData()
    form.append('file', file)
    try {
      const res  = await fetch(`${API_BASE}${ut.endpoint}`, { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setResult(data); setStatus('done')
    } catch (e) {
      setResult({ inserted: 0, updated: 0, skipped: 0, errors: [e.message || 'Upload failed'] })
      setStatus('error')
    }
  }

  return (
    <div style={{ padding: '32px 40px', maxWidth: 720, margin: '0 auto' }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3, marginBottom: 6 }}>Data Upload</h1>
        <p style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.6 }}>
          Upload CSV or Excel files to update the department database. All uploads are upsert — safe to re-run.
        </p>
      </div>

      {/* Step 1 — type */}
      <div style={card}>
        <StepHeader n={1} label="What are you uploading?" active />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
          {TYPES.map(t => {
            const active = selected === t.value
            return (
              <button key={t.value} onClick={() => handleTypeChange(t.value)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderRadius: 12, border: `1.5px solid ${active ? t.border : '#e2e0d8'}`, background: active ? t.bg : '#fff', cursor: 'pointer', textAlign: 'left', width: '100%', fontFamily: 'DM Sans, sans-serif', transition: 'all 0.12s' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: active ? t.color : '#1a1a18' }}>{t.label}</div>
                  <div style={{ fontSize: 12, color: '#5a5a54', marginTop: 2 }}>{t.desc}</div>
                </div>
                {active && <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={t.color} strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Step 2 — file */}
      {ut && (
        <div style={card}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <StepHeader n={2} label="Select file" active />
            <button onClick={() => setShowSample(v => !v)} style={{ fontSize: 12, color: ut.color, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'DM Mono, monospace' }}>
              {showSample ? 'Hide' : 'View'} CSV format
            </button>
          </div>

          {/* Column chips */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
            {ut.required.map(c => <span key={c} style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', padding: '2px 8px', borderRadius: 6, background: ut.bg, color: ut.color, border: `1px solid ${ut.border}` }}>{c}</span>)}
            {ut.optional.map(c => <span key={c} style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', padding: '2px 8px', borderRadius: 6, background: '#f5f4f0', color: '#9a9a90', border: '1px solid #e2e0d8' }}>{c}?</span>)}
          </div>
          {ut.notes.map((n, i) => <div key={i} style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', color: '#5a5a54', padding: '1px 0' }}>· {n}</div>)}

          {showSample && (
            <pre style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', background: '#f5f4f0', border: '1px solid #e2e0d8', borderRadius: 10, padding: '14px 16px', overflowX: 'auto', color: '#5a5a54', lineHeight: 1.7, marginTop: 14 }}>
              {ut.sample}
            </pre>
          )}

          {/* Drop zone */}
          <div
            style={{ marginTop: 18, border: `2px dashed ${dragOver ? ut.border : file ? '#86efac' : '#e2e0d8'}`, borderRadius: 14, padding: '32px 24px', textAlign: 'center', cursor: 'pointer', background: dragOver ? ut.bg : file ? '#f0fdf4' : '#fafaf8', transition: 'all 0.12s' }}
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) pickFile(f) }}
            onClick={() => inputRef.current?.click()}
          >
            <input ref={inputRef} type="file" accept=".csv,.xlsx,.xls" style={{ display: 'none' }} onChange={e => { if (e.target.files?.[0]) pickFile(e.target.files[0]) }} />
            {file ? (
              <>
                <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{file.name}</div>
                <div style={{ fontSize: 12, color: '#5a5a54', marginTop: 4 }}>{(file.size / 1024).toFixed(1)} KB</div>
                <button onClick={e => { e.stopPropagation(); reset() }} style={{ marginTop: 10, fontSize: 12, color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}>Remove</button>
              </>
            ) : (
              <>
                <div style={{ fontSize: 28, marginBottom: 10 }}>☁️</div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>Drop file here or <span style={{ color: ut.color }}>browse</span></div>
                <div style={{ fontSize: 12, color: '#9a9a90', marginTop: 4 }}>CSV or Excel · Max 10 MB</div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Step 3 — upload */}
      {file && ut && status !== 'done' && (
        <div style={card}>
          <StepHeader n={3} label="Upload" active />
          <button onClick={upload} disabled={status === 'uploading'} style={{ width: '100%', padding: 13, borderRadius: 12, border: 'none', marginTop: 16, background: status === 'uploading' ? '#9ab0f5' : ut.color, color: '#fff', fontSize: 14, fontWeight: 500, cursor: status === 'uploading' ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontFamily: 'DM Sans, sans-serif' }}>
            {status === 'uploading' ? <><SpinSVG /> Uploading…</> : <><UploadSVG /> Upload {ut.label}</>}
          </button>
        </div>
      )}

      {/* Result */}
      {result && (
        <div style={{ borderRadius: 16, border: `1.5px solid ${status === 'done' ? '#86efac' : '#fca5a5'}`, background: status === 'done' ? '#f0fdf4' : '#fef2f2', padding: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <span style={{ fontSize: 18 }}>{status === 'done' ? '✅' : '❌'}</span>
            <span style={{ fontSize: 14, fontWeight: 600, color: status === 'done' ? '#15803d' : '#dc2626' }}>
              {status === 'done' ? 'Upload complete' : 'Upload failed'}
            </span>
          </div>
          {status === 'done' && (
            <div style={{ display: 'flex', gap: 32, marginBottom: result.errors?.length ? 16 : 0 }}>
              {[['Inserted', result.inserted, '#16a34a'], ['Updated', result.updated, '#2d5be3'], ['Skipped', result.skipped, '#b45309']].map(([label, val, color]) => (
                <div key={label}>
                  <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'DM Mono, monospace', color }}>{val}</div>
                  <div style={{ fontSize: 12, color: '#5a5a54' }}>{label}</div>
                </div>
              ))}
            </div>
          )}
          {result.errors?.length > 0 && (
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: '#dc2626', marginBottom: 8 }}>{result.errors.length} issue{result.errors.length > 1 ? 's' : ''}:</div>
              <div style={{ background: '#fff', borderRadius: 10, border: '1px solid #fca5a5', padding: '10px 14px', maxHeight: 150, overflowY: 'auto' }}>
                {result.errors.map((e, i) => <div key={i} style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', color: '#dc2626', padding: '2px 0' }}>{e}</div>)}
              </div>
            </div>
          )}
          <button onClick={reset} style={{ marginTop: 16, fontSize: 13, color: '#2d5be3', background: 'none', border: 'none', cursor: 'pointer' }}>
            Upload another file →
          </button>
        </div>
      )}
    </div>
  )
}

function StepHeader({ n, label, active }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ width: 24, height: 24, borderRadius: '50%', background: active ? '#2d5be3' : '#e2e0d8', color: active ? '#fff' : '#9a9a90', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{n}</div>
      <span style={{ fontSize: 13, fontWeight: 600 }}>{label}</span>
    </div>
  )
}

function SpinSVG() {
  return <svg style={{ animation: 'spin 1s linear infinite' }} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
}
function UploadSVG() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
}
