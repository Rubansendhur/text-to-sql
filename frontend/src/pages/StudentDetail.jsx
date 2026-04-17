import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { API_BASE } from '../lib/api.js'

const SEM = { 1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII',9:'IX',10:'X' }
const DAYS = ['Mon','Tue','Wed','Thu','Fri']

function Badge({ label, color }) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
      padding: '3px 9px', borderRadius: 6,
      background: color + '18', color,
    }}>{label}</span>
  )
}

function Card({ title, children, style = {} }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8',
      padding: '20px 24px', ...style
    }}>
      {title && <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 700, color: '#1a1a18', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title}</h3>}
      {children}
    </div>
  )
}

function GpaBar({ gpa, max = 10 }) {
  const pct = Math.min((gpa / max) * 100, 100)
  const color = gpa >= 8 ? '#16a34a' : gpa >= 6 ? '#2d5be3' : gpa >= 5 ? '#b45309' : '#dc2626'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ flex: 1, height: 8, background: '#f0efe9', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.4s' }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color, fontFamily: 'DM Mono, monospace', minWidth: 36 }}>
        {Number(gpa).toFixed(2)}
      </span>
    </div>
  )
}

// Mini weekly timetable grid
function MiniTimetable({ slots }) {
  if (!slots?.length) return <p style={{ color: '#9a9a90', fontSize: 13 }}>No timetable data for this semester.</p>

  // Build map: day → hour → slot
  const grid = {}
  const hours = [...new Set(slots.map(s => s.hour_number))].sort((a,b)=>a-b)
  DAYS.forEach(d => { grid[d] = {} })
  slots.forEach(s => { if (grid[s.day_of_week]) grid[s.day_of_week][s.hour_number] = s })

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%' }}>
        <thead>
          <tr style={{ background: '#f8f7f4' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left', color: '#9a9a90', fontWeight: 600, whiteSpace: 'nowrap' }}>Day</th>
            {hours.map(h => (
              <th key={h} style={{ padding: '8px 10px', color: '#9a9a90', fontWeight: 600, minWidth: 90 }}>Hour {h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DAYS.map(day => (
            <tr key={day} style={{ borderTop: '1px solid #f0efe9' }}>
              <td style={{ padding: '8px 12px', fontWeight: 700, color: '#5a5a54', fontSize: 12 }}>{day}</td>
              {hours.map(h => {
                const slot = grid[day]?.[h]
                return (
                  <td key={h} style={{ padding: '6px 8px', verticalAlign: 'top' }}>
                    {slot?.subject_code ? (
                      <div style={{ background: '#eef2fc', borderRadius: 6, padding: '4px 7px' }}>
                        <div style={{ fontWeight: 700, color: '#2d5be3', fontSize: 10 }}>{slot.subject_code}</div>
                        <div style={{ color: '#5a5a54', fontSize: 9, marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 80 }}>{slot.faculty_name}</div>
                      </div>
                    ) : slot?.activity ? (
                      <div style={{ background: '#f0fdf4', borderRadius: 6, padding: '4px 7px', color: '#16a34a', fontSize: 10, fontWeight: 600 }}>{slot.activity}</div>
                    ) : (
                      <div style={{ color: '#e2e0d8', fontSize: 10 }}>—</div>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function StudentDetail() {
  const { register_number } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/students/${register_number}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('not_found'); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(() => { setError('Student not found'); setLoading(false) })
  }, [register_number])

  if (loading) return (
    <div style={{ padding: 40, textAlign: 'center', color: '#9a9a90' }}>Loading student profile…</div>
  )
  if (error) return (
    <div style={{ padding: 40 }}>
      <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '16px 20px', borderRadius: 12 }}>{error}</div>
      <button onClick={() => navigate(-1)} style={{ marginTop: 16, padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e0d8', background: '#fff', cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>← Back</button>
    </div>
  )

  const { student, gpa_history, arrears, attempt_history, timetable } = data

  const cgpaColor = student.cgpa >= 8 ? '#16a34a' : student.cgpa >= 6 ? '#2d5be3' : student.cgpa >= 5 ? '#b45309' : '#dc2626'
  const tabs = ['overview','academics','arrears','timetable']

  return (
    <div className="page-container" style={{ maxWidth: 1100 }}>

      {/* Back button */}
      <button onClick={() => navigate(-1)} style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        marginBottom: 20, padding: '7px 14px', borderRadius: 8,
        border: '1px solid #e2e0d8', background: '#fff',
        fontSize: 13, cursor: 'pointer', color: '#5a5a54', fontFamily: 'DM Sans, sans-serif'
      }}>← Back to Students</button>

      {/* Hero header */}
      <div style={{
        background: 'linear-gradient(135deg, #1a1a18 0%, #2d5be3 100%)',
        borderRadius: 20, padding: '28px 32px', marginBottom: 24,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap'
      }}>
        {/* Avatar + name */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%',
            background: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 28, color: '#fff', flexShrink: 0
          }}>
            {student.gender === 'Female' ? '👩‍🎓' : '👨‍🎓'}
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3 }}>{student.name}</h1>
            <div style={{ marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>{student.register_number}</span>
              <span style={{ color: 'rgba(255,255,255,0.4)' }}>·</span>
              <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>{student.department_code}</span>
              <span style={{ color: 'rgba(255,255,255,0.4)' }}>·</span>
              <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>{student.admission_year} Batch</span>
              {student.current_semester > 0 && student.current_semester <= 10 && (
                <>
                  <span style={{ color: 'rgba(255,255,255,0.4)' }}>·</span>
                  <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)' }}>Sem {SEM[student.current_semester]}</span>
                </>
              )}
            </div>
            <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', padding: '2px 9px', borderRadius: 20, background: student.status === 'active' ? '#dcfce7' : '#f3f4f6', color: student.status === 'active' ? '#16a34a' : '#5a5a54' }}>
                {student.status}
              </span>
              <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', padding: '2px 9px', borderRadius: 20, background: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.9)' }}>
                {student.hostel_status}
              </span>
              {arrears.length > 0 && (
                <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', padding: '2px 9px', borderRadius: 20, background: '#fee2e2', color: '#dc2626' }}>
                  {arrears.length} Arrear{arrears.length > 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* CGPA ring */}
        <div style={{
          textAlign: 'center', background: 'rgba(255,255,255,0.1)',
          borderRadius: 16, padding: '18px 28px'
        }}>
          <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>CGPA</div>
          <div style={{ fontSize: 42, fontWeight: 900, color: '#fff', fontFamily: 'DM Mono, monospace', lineHeight: 1 }}>
            {student.cgpa > 0 ? Number(student.cgpa).toFixed(2) : '—'}
          </div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>out of 10.00</div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: '#f0efe9', padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {tabs.map(tab => {
          const active = activeTab === tab
          const label = tab === 'overview' ? '👤 Overview' : tab === 'academics' ? '📊 Academics' : tab === 'arrears' ? `⚠️ Arrears${arrears.length ? ` (${arrears.length})` : ''}` : '📅 Timetable'
          return (
            <button key={tab} onClick={() => setActiveTab(tab)} style={{
              padding: '8px 18px', borderRadius: 9, border: 'none',
              background: active ? '#fff' : 'transparent',
              color: active ? '#2d5be3' : '#5a5a54',
              fontWeight: active ? 700 : 400, fontSize: 13,
              cursor: 'pointer', fontFamily: 'DM Sans, sans-serif',
              boxShadow: active ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.12s'
            }}>{label}</button>
          )
        })}
      </div>

      {/* ── OVERVIEW TAB ─────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Card title="Personal Info">
            {[
              ['Full Name', student.name],
              ['Register No.', student.register_number],
              ['Gender', student.gender],
              ['Date of Birth', student.date_of_birth ? new Date(student.date_of_birth).toLocaleDateString('en-IN') : '—'],
              ['Department', `${student.department_code} — ${student.department_name}`],
              ['Section', student.section || '—'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0efe9', fontSize: 13 }}>
                <span style={{ color: '#9a9a90', fontWeight: 500 }}>{k}</span>
                <span style={{ fontWeight: 600, color: '#1a1a18' }}>{v}</span>
              </div>
            ))}
          </Card>

          <Card title="Contact & Status">
            {[
              ['Email', student.email || '—'],
              ['Phone', student.contact_number || '—'],
              ['Hostel', student.hostel_status],
              ['Status', student.status],
              ['Admission Year', student.admission_year],
              ['Current Semester', student.current_semester > 0 ? `Sem ${SEM[student.current_semester]} (${student.current_semester})` : '—'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f0efe9', fontSize: 13 }}>
                <span style={{ color: '#9a9a90', fontWeight: 500 }}>{k}</span>
                <span style={{ fontWeight: 600, color: '#1a1a18' }}>{v}</span>
              </div>
            ))}
          </Card>

          {/* Quick stats */}
          <Card title="Quick Stats" style={{ gridColumn: '1 / -1' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
              {[
                { label: 'CGPA', value: student.cgpa > 0 ? Number(student.cgpa).toFixed(2) : '—', color: cgpaColor, bg: cgpaColor + '18' },
                { label: 'Active Arrears', value: arrears.length, color: arrears.length > 0 ? '#dc2626' : '#16a34a', bg: arrears.length > 0 ? '#fef2f2' : '#f0fdf4' },
                { label: 'Semesters Completed', value: gpa_history.length, color: '#2d5be3', bg: '#eef2fc' },
                { label: 'Total Attempts', value: attempt_history.length, color: '#7c3aed', bg: '#f5f3ff' },
              ].map(m => (
                <div key={m.label} style={{ background: m.bg, borderRadius: 12, padding: '16px 18px' }}>
                  <div style={{ fontSize: 11, color: m.color, fontWeight: 600, marginBottom: 6, opacity: 0.8 }}>{m.label}</div>
                  <div style={{ fontSize: 28, fontWeight: 800, color: m.color, fontFamily: 'DM Mono, monospace' }}>{m.value}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── ACADEMICS TAB ────────────────────────────────────────────── */}
      {activeTab === 'academics' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card title="Semester-wise GPA">
            {gpa_history.length === 0 ? (
              <p style={{ color: '#9a9a90', fontSize: 13 }}>No GPA data uploaded yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {gpa_history.map(g => (
                  <div key={g.semester_number} style={{ display: 'grid', gridTemplateColumns: '80px 1fr 120px', gap: 12, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#5a5a54' }}>Sem {SEM[g.semester_number]}</span>
                    <GpaBar gpa={g.gpa} />
                    <div style={{ fontSize: 11, color: '#9a9a90', textAlign: 'right' }}>
                      CGPA: <strong style={{ color: '#1a1a18' }}>{Number(g.cgpa_upto || 0).toFixed(2)}</strong>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Subject Attempt History">
            {attempt_history.length === 0 ? (
              <p style={{ color: '#9a9a90', fontSize: 13 }}>No attempt history found.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8f7f4' }}>
                      {['Sem', 'Subject Code', 'Subject Name', 'Year', 'Month', 'Grade'].map(h => (
                        <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {attempt_history.map((a, i) => {
                      const fail = ['U','AB'].includes(a.grade)
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid #f0efe9' }}>
                          <td style={{ padding: '10px 14px', color: '#5a5a54', fontSize: 12 }}>{SEM[a.semester_number]}</td>
                          <td style={{ padding: '10px 14px', fontFamily: 'DM Mono, monospace', fontSize: 12, fontWeight: 700, color: '#2d5be3' }}>{a.subject_code}</td>
                          <td style={{ padding: '10px 14px', color: '#1a1a18' }}>{a.subject_name}</td>
                          <td style={{ padding: '10px 14px', color: '#5a5a54' }}>{a.exam_year}</td>
                          <td style={{ padding: '10px 14px', color: '#5a5a54' }}>{a.exam_month}</td>
                          <td style={{ padding: '10px 14px' }}>
                            <span style={{
                              fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 13,
                              color: fail ? '#dc2626' : '#16a34a',
                              background: fail ? '#fef2f2' : '#f0fdf4',
                              padding: '2px 8px', borderRadius: 5
                            }}>{a.grade}</span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── ARREARS TAB ──────────────────────────────────────────────── */}
      {activeTab === 'arrears' && (
        <Card title={`Active Arrears (${arrears.length})`}>
          {arrears.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🎉</div>
              <div style={{ fontWeight: 600, color: '#16a34a' }}>No active arrears!</div>
              <div style={{ fontSize: 13, color: '#9a9a90', marginTop: 4 }}>This student has cleared all subjects.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {arrears.map((a, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 12, padding: '14px 18px'
                }}>
                  <div style={{ width: 36, height: 36, borderRadius: 9, background: '#fee2e2', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>⚠️</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 13, color: '#dc2626' }}>{a.subject_code}</div>
                    <div style={{ fontSize: 13, color: '#1a1a18', fontWeight: 600, marginTop: 1 }}>{a.subject_name}</div>
                    <div style={{ fontSize: 11, color: '#9a9a90', marginTop: 2 }}>
                      Semester {SEM[a.semester_number]} · Last attempt: {a.exam_month} {a.exam_year} · Grade: <strong style={{ color: '#dc2626' }}>{a.grade}</strong>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* ── TIMETABLE TAB ────────────────────────────────────────────── */}
      {activeTab === 'timetable' && (
        <Card title={`Current Semester Timetable — Sem ${SEM[student.current_semester] || student.current_semester}, Section ${student.section}`}>
          <MiniTimetable slots={timetable} />
        </Card>
      )}
    </div>
  )
}