import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function Subjects() {
  const { user } = useAuth();
  const displayDept = user?.department_code || (user?.username ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() || 'Department' : 'Department');

  const [subjects,  setSubjects]  = useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [search,    setSearch]    = useState('')
  const [type,      setType]      = useState('')
  const [semester,  setSemester]  = useState('')

  useEffect(() => {
    setLoading(true)
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/subjects/all`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('no_data'); return r.json() })
      .then(d => { setSubjects(d.subjects || []); setError(null) })
      .catch(() => { setSubjects([]); setError('empty') })
      .finally(() => setLoading(false))
  }, [])

  const filtered = subjects.filter(s => {
    if (search && !(s.subject_name.toLowerCase().includes(search.toLowerCase()) || s.subject_code.toLowerCase().includes(search.toLowerCase()))) return false
    if (type && s.subject_type !== type) return false
    if (semester && s.semester_number !== Number(semester)) return false
    return true
  })

  // Group by semester for cleaner display when not filtered by semester
  const grouped = filtered.reduce((acc, s) => {
    const sem = s.semester_number || 0
    if (!acc[sem]) acc[sem] = []
    acc[sem].push(s)
    return acc
  }, {})

  const semesters = Object.keys(grouped).sort((a,b) => Number(a)-Number(b))

  const sel = {
    padding: '7px 12px', borderRadius: 8, border: '1px solid #e2e0d8',
    background: '#fff', fontSize: 13, fontFamily: 'DM Sans, sans-serif',
    outline: 'none', cursor: 'pointer',
  }

  return (
    <div className="page-container" style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div className="page-header-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3 }}>Subject Database</h1>
          <p style={{ fontSize: 13, color: '#5a5a54', marginTop: 3 }}>
            {displayDept} Curriculum · {filtered.length} subjects
          </p>
        </div>
        <div className="filter-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <input
            style={{ ...sel, width: 220 }}
            placeholder="Search code or name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <select style={sel} value={semester} onChange={e => setSemester(e.target.value)}>
            <option value="">All Semesters</option>
            {[1,2,3,4,5,6,7,8,9,10].map(s => <option key={s} value={s}>Semester {s}</option>)}
          </select>
          <select style={sel} value={type} onChange={e => setType(e.target.value)}>
            <option value="">All Types</option>
            <option value="Theory">Theory</option>
            <option value="Practical">Practical</option>
            <option value="Elective">Elective</option>
            <option value="Elective Practical">Elective Practical</option>
          </select>
        </div>
      </div>

      {error === 'empty' && (
        <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', color: '#0369a1', padding: '10px 16px', borderRadius: 12, marginBottom: 20, fontSize: 13 }}>
          📋 No subjects have been added for <strong>{displayDept}</strong> yet.
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', color: '#9a9a90', padding: 48, fontSize: 13 }}>Loading curriculum…</div>
      ) : filtered.length === 0 && !error ? (
        <div style={{ textAlign: 'center', color: '#9a9a90', padding: 48, fontSize: 13, background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8' }}>No subjects match the current filters.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {semesters.map(semStr => {
            const sem = Number(semStr)
            const list = grouped[sem]
            return (
              <div key={sem} style={{ background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', overflow: 'hidden' }}>
                <div style={{ padding: '12px 20px', background: '#fafaf8', borderBottom: '1px solid #e2e0d8', fontWeight: 600, fontSize: 14, color: '#1a1a18' }}>
                  {sem === 0 ? 'General / Custom Electives' : `Semester ${sem}`}
                  <span style={{ fontWeight: 400, color: '#9a9a90', fontSize: 12, marginLeft: 8 }}>· {list.length} courses</span>
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, whiteSpace: 'nowrap' }}>
                    <thead>
                      <tr style={{ background: '#fcfcfb', borderBottom: '1px solid #f0efe9' }}>
                        <th style={thStyle}>Code</th>
                        <th style={{ ...thStyle, width: '40%' }}>Subject Name</th>
                        <th style={thStyle}>Type</th>
                        <th style={thStyle}>L T P C</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map(s => (
                        <tr key={s.subject_id} style={{ borderBottom: '1px solid #f0efe9' }}>
                          <td style={{ padding: '12px 20px', fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#2d5be3', fontWeight: 500 }}>{s.subject_code}</td>
                          <td style={{ padding: '12px 20px', fontWeight: 500, color: '#1a1a18', whiteSpace: 'normal', minWidth: 200, lineHeight: 1.4 }}>{s.subject_name}</td>
                          <td style={{ padding: '12px 20px' }}><Badge type={s.subject_type || 'Theory'} /></td>
                          <td style={{ padding: '12px 20px', fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#5a5a54' }}>
                            {s.lecture_hrs || 0} - {s.tutorial_hrs || 0} - {s.practical_hrs || 0} : <span style={{ fontWeight: 700, color: '#1a1a18' }}>{s.credits || 0}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function Badge({ type }) {
  let color = '#5a5a54'; let bg = '#f5f4f0'
  if (type === 'Theory') { color = '#2d5be3'; bg = '#eef2fc' }
  else if (type === 'Practical') { color = '#16a34a'; bg = '#f0fdf4' }
  else if (type.includes('Elective')) { color = '#b45309'; bg = '#fffbeb' }
  return (
    <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '2px 8px', borderRadius: 6, background: bg, color }}>
      {type}
    </span>
  )
}

const thStyle = { padding: '10px 20px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.06em' }
