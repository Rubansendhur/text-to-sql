import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

const SEM = { 1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII',9:'IX',10:'X' }

const sel = {
  padding: '7px 12px', borderRadius: 8, border: '1px solid #e2e0d8',
  background: '#fff', fontSize: 13, fontFamily: 'DM Sans, sans-serif',
  outline: 'none', cursor: 'pointer',
}

export default function Students() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const displayDept = user?.department_code ||
    (user?.username ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() || 'Department' : 'Department')

  const [students,  setStudents]  = useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [status,    setStatus]    = useState('Active')
  const [hostel,    setHostel]    = useState('')
  const [semester,  setSemester]  = useState('')
  const [search,    setSearch]    = useState('')

  useEffect(() => {
    setLoading(true)
    const token = localStorage.getItem('access_token')
    const p = new URLSearchParams()
    if (status)   p.append('status',   status)
    if (hostel)   p.append('hostel',   hostel)
    if (semester) p.append('semester', semester)
    fetch(`${API_BASE}/api/students?${p}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('no_data'); return r.json() })
      .then(d => { setStudents(d.students || []); setError(null) })
      .catch(() => { setStudents([]); setError('empty') })
      .finally(() => setLoading(false))
  }, [status, hostel, semester])

  const filtered = students.filter(s =>
    !search ||
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.register_number.includes(search)
  )

  return (
    <div className="page-container" style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div className="page-header-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3 }}>Students Directory</h1>
          <p style={{ fontSize: 13, color: '#5a5a54', marginTop: 3 }}>
            {displayDept} · {filtered.length} student{filtered.length !== 1 ? 's' : ''}
            {semester && <span style={{ color: '#2d5be3', fontWeight: 600 }}> · Sem {SEM[Number(semester)]}</span>}
            <span style={{ marginLeft: 8, fontSize: 12, color: '#9a9a90' }}>· Click a student to view full profile</span>
          </p>
        </div>
        <div className="filter-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <input
            style={{ ...sel, width: 200 }}
            placeholder="Search name or reg no…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <select style={sel} value={semester} onChange={e => { setSemester(e.target.value); if (e.target.value) setStatus('') }}>
            <option value="">All Semesters</option>
            {[1,2,3,4,5,6,7,8].map(s => <option key={s} value={s}>Semester {SEM[s]}</option>)}
          </select>
          <select style={sel} value={status} onChange={e => setStatus(e.target.value)}>
            <option value="">All Statuses</option>
            <option value="Active">Active</option>
            <option value="Graduated">Graduated</option>
            <option value="Dropout">Dropout</option>
          </select>
          <select style={sel} value={hostel} onChange={e => setHostel(e.target.value)}>
            <option value="">All Living</option>
            <option value="Hosteller">Hosteller</option>
            <option value="Day Scholar">Day Scholar</option>
          </select>
        </div>
      </div>

      {!loading && students.length === 0 && (
        <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', color: '#0369a1', padding: '12px 18px', borderRadius: 12, marginBottom: 20, fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>📋</span>
          <span>No student data found for <strong>{displayDept}</strong>. Upload student records via the Data Upload page to get started.</span>
        </div>
      )}

      <div style={{ background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', overflow: 'hidden' }}>
        <div className="table-scroll-wrap">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, whiteSpace: 'nowrap' }}>
            <thead>
              <tr style={{ background: '#f8f7f4', borderBottom: '1px solid #e2e0d8' }}>
                {['Register No.','Name','Batch / Sem','CGPA','Status','Contact',''].map(h => (
                  <th key={h} style={{ padding: '12px 18px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={emptyCell}>Loading…</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} style={emptyCell}>{students.length === 0 ? `No students in ${displayDept}` : 'No students match your filters.'}</td></tr>
              ) : filtered.map(s => (
                <tr
                  key={s.register_number}
                  style={{ borderBottom: '1px solid #f0efe9', cursor: 'pointer', transition: 'background 0.1s' }}
                  onClick={() => navigate(`/students/${s.register_number}`)}
                  onMouseEnter={e => e.currentTarget.style.background = '#fafaf8'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '13px 18px', fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#5a5a54' }}>{s.register_number}</td>
                  <td style={{ padding: '13px 18px', fontWeight: 600, color: '#1a1a18' }}>{s.name}</td>
                  <td style={{ padding: '13px 18px' }}>
                    <div style={{ fontSize: 13, color: '#1a1a18' }}>{s.admission_year}</div>
                    {s.current_semester > 0 && s.current_semester <= 8 && (
                      <span style={{ fontSize: 10, fontWeight: 700, background: '#eef2fc', color: '#2d5be3', padding: '1px 6px', borderRadius: 4, marginTop: 2, display: 'inline-block' }}>
                        Sem {SEM[s.current_semester]}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '13px 18px', fontFamily: 'DM Mono, monospace', fontWeight: 600, color: s.cgpa > 0 ? '#16a34a' : '#ccc' }}>
                    {s.cgpa > 0 ? Number(s.cgpa).toFixed(2) : '—'}
                  </td>
                  <td style={{ padding: '13px 18px' }}>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <Badge label={s.status} color={s.status === 'Active' ? '#16a34a' : s.status === 'Graduated' ? '#2d5be3' : '#dc2626'} />
                      <Badge label={s.hostel_status} color="#5a5a54" />
                    </div>
                  </td>
                  <td style={{ padding: '13px 18px' }}>
                    <div style={{ fontSize: 13 }}>{s.contact_number || '—'}</div>
                    <div style={{ fontSize: 11, color: '#9a9a90' }}>{s.email || '—'}</div>
                  </td>
                  <td style={{ padding: '13px 18px' }}>
                    <span style={{ fontSize: 12, color: '#9a9a90' }}>View →</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ padding: '12px 18px', borderTop: '1px solid #f0efe9', background: '#fafaf8', fontSize: 12, color: '#9a9a90', textAlign: 'center' }}>
          Showing {filtered.length} of {students.length} students · Click any row for full profile
        </div>
      </div>
    </div>
  )
}

function Badge({ label, color }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
      padding: '2px 7px', borderRadius: 5,
      background: color + '18', color,
    }}>{label}</span>
  )
}

const emptyCell = { padding: '48px', textAlign: 'center', color: '#9a9a90', fontSize: 13 }