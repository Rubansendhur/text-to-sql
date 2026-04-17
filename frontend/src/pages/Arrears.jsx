import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

const SEM = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X' }

const sel = {
  padding: '7px 12px', borderRadius: 8, border: '1px solid #e2e0d8',
  background: '#fff', fontSize: 13, fontFamily: 'DM Sans, sans-serif', outline: 'none',
}

// ── Subject pill shown inline in the table ────────────────────────────────────
function SubjectPill({ sub }) {
  return (
    <div style={{
      display: 'inline-flex', flexDirection: 'column',
      padding: '4px 9px', borderRadius: 7,
      background: '#fef2f2', border: '1px solid #fecaca',
      fontSize: 11, lineHeight: 1.35,
      gap: 1,
    }}>
      <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 700, color: '#dc2626' }}>
        {sub.subject_code}
      </span>
      <span style={{ color: '#7f1d1d', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {sub.subject_name}
      </span>
      <span style={{ color: '#9ca3af', fontSize: 9, fontFamily: 'DM Mono, monospace' }}>
        Sem {SEM[sub.semester_number] ?? sub.semester_number}
        {' · '}{sub.exam_month} {sub.exam_year}
      </span>
    </div>
  )
}

// ── Expandable subjects cell ──────────────────────────────────────────────────
function SubjectsCell({ subjects }) {
  const [expanded, setExpanded] = useState(false)
  if (!subjects?.length) return <span style={{ color: '#9ca3af', fontSize: 12 }}>—</span>

  const visible = expanded ? subjects : subjects.slice(0, 2)
  const hidden = subjects.length - 2

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'flex-start' }}>
      {visible.map((s, i) => <SubjectPill key={i} sub={s} />)}
      {!expanded && hidden > 0 && (
        <button onClick={() => setExpanded(true)} style={{
          alignSelf: 'center', fontSize: 11, fontWeight: 600,
          color: '#dc2626', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 20, padding: '3px 10px', cursor: 'pointer', fontFamily: 'DM Sans, sans-serif',
        }}>
          +{hidden} more
        </button>
      )}
      {expanded && hidden > 0 && (
        <button onClick={() => setExpanded(false)} style={{
          alignSelf: 'center', fontSize: 11, fontWeight: 600,
          color: '#5a5a54', background: '#f5f4f0', border: '1px solid #e2e0d8',
          borderRadius: 20, padding: '3px 10px', cursor: 'pointer', fontFamily: 'DM Sans, sans-serif',
        }}>
          Show less
        </button>
      )}
    </div>
  )
}

export default function Arrears() {
  const { user } = useAuth()
  const displayDept = user?.department_code || (user?.username ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() || 'Department' : 'Department');
  const [students, setStudents] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [minCount, setMinCount] = useState(1)
  const [semester, setSemester] = useState('')
  const [search, setSearch] = useState('')
  const [subjectOptions, setSubjectOptions] = useState([])
  const [subjectFilter, setSubjectFilter] = useState('')

  // Load subject filter options once
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/arrears/subjects`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(d => setSubjectOptions(d.subjects || []))
      .catch(() => {})
  }, [])

  // Reload students when filters change
  useEffect(() => {
    setLoading(true)
    const token = localStorage.getItem('access_token')
    const p = new URLSearchParams()
    p.append('min_count', String(minCount))
    if (semester) p.append('semester', semester)

    fetch(`${API_BASE}/api/arrears?${p}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('no_data'); return r.json() })
      .then(d => {
        const rows = (d.students || []).map(s => ({
          ...s,
          arrear_subjects: typeof s.arrear_subjects === 'string'
            ? JSON.parse(s.arrear_subjects)
            : (s.arrear_subjects ?? []),
        }))
        setStudents(rows)
        setTotal(d.total || 0)
        setError(null)
      })
      .catch(() => { setStudents([]); setError('empty') })
      .finally(() => setLoading(false))
  }, [minCount, semester])

  // Client-side filters: name/reg search + subject filter
  const filtered = students.filter(s => {
    if (search && !s.name.toLowerCase().includes(search.toLowerCase()) && !s.register_number.includes(search)) return false
    if (subjectFilter && !s.arrear_subjects?.some(sub => sub.subject_code === subjectFilter)) return false
    return true
  })

  return (
    <div className="page-container" style={{ maxWidth: 1200 }}>

      {/* Header */}
      <div className="page-header-row" style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3 }}>Arrear Tracking</h1>
          <p style={{ fontSize: 13, color: '#5a5a54', marginTop: 3 }}>
            Students with pending supplementary exams
            {semester && <span style={{ color: '#b45309', fontWeight: 600 }}> · Sem {SEM[Number(semester)]}</span>}
          </p>
        </div>

        <div className="filter-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <input
            style={{ ...sel, width: 180 }}
            placeholder="Search name or reg…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />

          <select style={sel} value={subjectFilter} onChange={e => setSubjectFilter(e.target.value)}>
            <option value="">All Subjects</option>
            {subjectOptions.map(s => (
              <option key={s.subject_code} value={s.subject_code}>
                {s.subject_code} — {s.subject_name}
              </option>
            ))}
          </select>

          <select style={sel} value={semester} onChange={e => setSemester(e.target.value)}>
            <option value="">All Semesters</option>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(s => <option key={s} value={s}>Semester {SEM[s]}</option>)}
          </select>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', border: '1px solid #e2e0d8', padding: '6px 12px', borderRadius: 8 }}>
            <label style={{ fontSize: 12, color: '#5a5a54', fontWeight: 500 }}>Min Arrears</label>
            <input
              type="number" min="1" value={minCount}
              onChange={e => setMinCount(parseInt(e.target.value) || 1)}
              style={{ width: 48, border: '1px solid #e2e0d8', borderRadius: 6, padding: '3px 6px', fontSize: 13, fontWeight: 700, textAlign: 'center', fontFamily: 'DM Mono, monospace', outline: 'none' }}
            />
          </div>
        </div>
      </div>

      {!loading && students.length === 0 && (
        <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', color: '#0369a1', padding: '12px 18px', borderRadius: 12, marginBottom: 20, fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>📋</span>
          <span>No arrear data found for <strong>{displayDept}</strong>. This section will populate once student exam results are uploaded.</span>
        </div>
      )}

      {/* Table */}
      <div style={{ background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', overflow: 'hidden' }}>

        {/* Summary bar */}
        <div style={{ padding: '13px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ width: 34, height: 34, borderRadius: '50%', background: '#fef3c7', border: '1px solid #fde68a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 15, color: '#b45309', flexShrink: 0 }}>
            {filtered.length}
          </div>
          <span style={{ fontSize: 13, fontWeight: 500, color: '#92400e' }}>
            {filtered.length === total
              ? `${total} student${total !== 1 ? 's' : ''} with ${minCount}+ active arrear${minCount !== 1 ? 's' : ''}`
              : `${filtered.length} of ${total} students (filtered)`}
          </span>
          {subjectFilter && (
            <span style={{ fontSize: 12, background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '2px 10px', borderRadius: 20, fontFamily: 'DM Mono, monospace' }}>
              Subject: {subjectFilter}
            </span>
          )}
        </div>

        <div className="table-scroll-wrap">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8f7f4', borderBottom: '1px solid #e2e0d8' }}>
                {['Count', 'Register No.', 'Student Name', 'Batch / Sem', 'Status', 'Active Arrear Subjects'].map(h => (
                  <th key={h} style={{ padding: '12px 18px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ padding: 48, textAlign: 'center', color: '#9a9a90' }}>Loading…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={6} style={{ padding: 48, textAlign: 'center', color: '#9a9a90' }}>{students.length === 0 ? `No arrears recorded in ${displayDept}` : 'No students match your filters.'}</td></tr>
              ) : filtered.map(s => (
                <tr key={s.register_number} style={{ borderBottom: '1px solid #f0efe9' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#fffdf5'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  {/* Count badge */}
                  <td style={{ padding: '14px 18px', whiteSpace: 'nowrap' }}>
                    <div style={{
                      width: 34, height: 34, borderRadius: 9,
                      background: s.active_arrear_count >= 3 ? '#fef2f2' : '#fffbeb',
                      border: `1px solid ${s.active_arrear_count >= 3 ? '#fecaca' : '#fde68a'}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 15,
                      color: s.active_arrear_count >= 3 ? '#dc2626' : '#b45309',
                    }}>
                      {s.active_arrear_count}
                    </div>
                  </td>

                  {/* Register no */}
                  <td style={{ padding: '14px 18px', fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#5a5a54', whiteSpace: 'nowrap' }}>
                    {s.register_number}
                  </td>

                  {/* Name */}
                  <td style={{ padding: '14px 18px', fontWeight: 600, whiteSpace: 'nowrap' }}>
                    {s.name}
                  </td>

                  {/* Batch / Sem */}
                  <td style={{ padding: '14px 18px', whiteSpace: 'nowrap' }}>
                    <div style={{ fontSize: 13 }}>{s.admission_year} Batch</div>
                    {s.current_semester > 0 && s.current_semester <= 8 && (
                      <span style={{ fontSize: 10, fontWeight: 700, background: '#fffbeb', color: '#b45309', padding: '1px 6px', borderRadius: 4, marginTop: 2, display: 'inline-block' }}>
                        Sem {SEM[s.current_semester]}
                      </span>
                    )}
                  </td>

                  {/* Status */}
                  <td style={{ padding: '14px 18px', whiteSpace: 'nowrap' }}>
                    <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', padding: '2px 8px', borderRadius: 5, background: s.status === 'Active' ? '#f0fdf4' : '#f8f7f4', color: s.status === 'Active' ? '#16a34a' : '#5a5a54' }}>
                      {s.status}
                    </span>
                  </td>

                  {/* Arrear subjects */}
                  <td style={{ padding: '12px 18px', maxWidth: 520 }}>
                    <SubjectsCell subjects={s.arrear_subjects} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ padding: '12px 18px', borderTop: '1px solid #f0efe9', background: '#fafaf8', fontSize: 12, color: '#9a9a90', textAlign: 'center' }}>
          Showing {filtered.length} of {students.length} students · Active arrear = latest exam attempt grade is U or AB
        </div>
      </div>

      {/* Legend */}
      <div style={{ marginTop: 16, padding: '14px 18px', background: '#fff', borderRadius: 12, border: '1px solid #e2e0d8', fontSize: 12, color: '#5a5a54', lineHeight: 1.8 }}>
        <strong style={{ color: '#1a1a18', marginRight: 8 }}>How arrear status is determined:</strong>
        Each subject is checked independently. The <em>latest</em> attempt (by year + month) decides the status.
        If it's <code style={{ background: '#fef2f2', color: '#dc2626', padding: '1px 5px', borderRadius: 4 }}>U</code> or
        <code style={{ background: '#fef2f2', color: '#dc2626', padding: '1px 5px', borderRadius: 4, marginLeft: 4 }}>AB</code> → active arrear.
        If it's any pass grade → cleared (history preserved). Re-uploading arrear results with a passing grade auto-clears it.
      </div>
    </div>
  )
}
