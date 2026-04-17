import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { API_BASE } from '../lib/api.js'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']

function Card({ title, children, style = {} }) {
  return (
    <div style={{
      background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8',
      padding: '20px 24px', ...style
    }}>
      {title && (
        <h3 style={{
          margin: '0 0 16px', fontSize: 13, fontWeight: 700, color: '#1a1a18',
          textTransform: 'uppercase', letterSpacing: '0.06em'
        }}>{title}</h3>
      )}
      {children}
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
      padding: '9px 0', borderBottom: '1px solid #f0efe9', fontSize: 13, gap: 16
    }}>
      <span style={{ color: '#9a9a90', fontWeight: 500, flexShrink: 0 }}>{label}</span>
      <span style={{ fontWeight: 600, color: '#1a1a18', textAlign: 'right' }}>{value || '—'}</span>
    </div>
  )
}

// Weekly timetable grid
function WeeklyTimetable({ slots }) {
  if (!slots?.length) {
    return <p style={{ color: '#9a9a90', fontSize: 13, margin: 0 }}>No timetable entries found.</p>
  }

  const hours = [...new Set(slots.map(s => s.hour_number))].sort((a, b) => a - b)
  const grid = {}
  DAYS.forEach(d => { grid[d] = {} })
  slots.forEach(s => { if (grid[s.day_of_week]) grid[s.day_of_week][s.hour_number] = s })

  const subjectColors = {}
  const palette = ['#eef2fc', '#f0fdf4', '#fef9c3', '#fdf4ff', '#fff1f2', '#ecfeff']
  const textColors = ['#2d5be3', '#16a34a', '#b45309', '#7c3aed', '#dc2626', '#0891b2']
  let colorIdx = 0
  slots.forEach(s => {
    if (s.subject_code && !subjectColors[s.subject_code]) {
      subjectColors[s.subject_code] = { bg: palette[colorIdx % palette.length], text: textColors[colorIdx % textColors.length] }
      colorIdx++
    }
  })

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%', minWidth: 600 }}>
        <thead>
          <tr style={{ background: '#f8f7f4', borderBottom: '1px solid #e2e0d8' }}>
            <th style={{ padding: '10px 14px', textAlign: 'left', color: '#9a9a90', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Day</th>
            {hours.map(h => (
              <th key={h} style={{ padding: '10px 12px', color: '#9a9a90', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', minWidth: 110 }}>
                Hour {h}
                {slots.find(s => s.hour_number === h)?.time_range && (
                  <div style={{ fontSize: 9, fontWeight: 400, color: '#b0b0a8', marginTop: 1 }}>
                    {slots.find(s => s.hour_number === h)?.time_range}
                  </div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DAYS.map(day => (
            <tr key={day} style={{ borderBottom: '1px solid #f0efe9' }}>
              <td style={{ padding: '10px 14px', fontWeight: 700, color: '#5a5a54', fontSize: 12, whiteSpace: 'nowrap' }}>{day}</td>
              {hours.map(h => {
                const slot = grid[day]?.[h]
                if (!slot) return (
                  <td key={h} style={{ padding: '8px 10px' }}>
                    <div style={{ color: '#e2e0d8', fontSize: 11, textAlign: 'center' }}>—</div>
                  </td>
                )
                const colors = slot.subject_code ? subjectColors[slot.subject_code] : { bg: '#f0fdf4', text: '#16a34a' }
                return (
                  <td key={h} style={{ padding: '6px 8px', verticalAlign: 'top' }}>
                    <div style={{
                      background: colors?.bg || '#f8f7f4',
                      borderRadius: 8, padding: '7px 9px',
                      border: `1px solid ${(colors?.text || '#9a9a90') + '30'}`
                    }}>
                      {slot.subject_code ? (
                        <>
                          <div style={{ fontWeight: 800, color: colors?.text, fontSize: 11, fontFamily: 'DM Mono, monospace' }}>{slot.subject_code}</div>
                          <div style={{ fontSize: 10, color: '#5a5a54', marginTop: 2, lineHeight: 1.3 }}>{slot.subject_name}</div>
                          {slot.sem_batch && (
                            <div style={{ fontSize: 9, color: '#9a9a90', marginTop: 2 }}>Sem {slot.sem_batch}</div>
                          )}
                        </>
                      ) : (
                        <div style={{ fontSize: 11, fontWeight: 600, color: colors?.text || '#16a34a' }}>{slot.activity}</div>
                      )}
                    </div>
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

export default function FacultyDetail() {
  const { faculty_id } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('overview')

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/faculty/${faculty_id}/profile`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('not_found'); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(() => { setError('Faculty member not found'); setLoading(false) })
  }, [faculty_id])

  if (loading) return (
    <div style={{ padding: 48, textAlign: 'center', color: '#9a9a90' }}>Loading faculty profile…</div>
  )
  if (error) return (
    <div style={{ padding: 40 }}>
      <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '16px 20px', borderRadius: 12 }}>{error}</div>
      <button onClick={() => navigate(-1)} style={{ marginTop: 16, padding: '8px 16px', borderRadius: 8, border: '1px solid #e2e0d8', background: '#fff', cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>← Back</button>
    </div>
  )

  const { faculty, timetable, subjects_taught, workload } = data

  const displayName = `${faculty.title || ''} ${faculty.full_name}`.trim()
  const scholarQuery = encodeURIComponent(`${faculty.full_name} ${faculty.department_name || ''}`)
  const googleScholarUrl = `https://scholar.google.com/scholar?q=${scholarQuery}`
  const orcidUrl = `https://orcid.org/search/?searchQuery=${encodeURIComponent(faculty.full_name)}`
  const researchGateUrl = `https://www.researchgate.net/search?q=${encodeURIComponent(faculty.full_name)}`

  const tabs = ['overview', 'timetable', 'subjects']

  return (
    <div className="page-container" style={{ maxWidth: 1100 }}>

      {/* Back */}
      <button onClick={() => navigate(-1)} style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        marginBottom: 20, padding: '7px 14px', borderRadius: 8,
        border: '1px solid #e2e0d8', background: '#fff',
        fontSize: 13, cursor: 'pointer', color: '#5a5a54', fontFamily: 'DM Sans, sans-serif'
      }}>← Back to Faculty</button>

      {/* Hero */}
      <div style={{
        background: 'linear-gradient(135deg, #1a1a18 0%, #7c3aed 100%)',
        borderRadius: 20, padding: '28px 32px', marginBottom: 24,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24, flexWrap: 'wrap'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          {/* Avatar */}
          <div style={{
            width: 68, height: 68, borderRadius: '50%',
            background: 'rgba(255,255,255,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 30, color: '#fff', flexShrink: 0, border: '2px solid rgba(255,255,255,0.2)'
          }}>👨‍🏫</div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: '#fff', letterSpacing: -0.3 }}>{displayName}</h1>
              {faculty.is_hod && (
                <span style={{ fontSize: 10, fontWeight: 700, background: '#fef3c7', color: '#b45309', padding: '2px 9px', borderRadius: 20, textTransform: 'uppercase' }}>HoD</span>
              )}
            </div>
            <div style={{ marginTop: 4, fontSize: 14, color: 'rgba(255,255,255,0.75)', fontWeight: 500 }}>
              {faculty.designation}
            </div>
            <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{faculty.department_code}</span>
              <span style={{ color: 'rgba(255,255,255,0.3)' }}>·</span>
              <span style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{faculty.department_name}</span>
              {!faculty.is_active && (
                <span style={{ fontSize: 10, background: '#fee2e2', color: '#dc2626', padding: '1px 8px', borderRadius: 20, fontWeight: 700 }}>Inactive</span>
              )}
            </div>

            {/* External research links */}
            <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <a href={googleScholarUrl} target="_blank" rel="noopener noreferrer" style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: 'rgba(255,255,255,0.15)', color: '#fff',
                textDecoration: 'none', border: '1px solid rgba(255,255,255,0.25)',
                transition: 'background 0.15s'
              }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                🎓 Google Scholar
              </a>
              <a href={researchGateUrl} target="_blank" rel="noopener noreferrer" style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: 'rgba(255,255,255,0.15)', color: '#fff',
                textDecoration: 'none', border: '1px solid rgba(255,255,255,0.25)',
                transition: 'background 0.15s'
              }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                🔬 ResearchGate
              </a>
              <a href={orcidUrl} target="_blank" rel="noopener noreferrer" style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                background: 'rgba(255,255,255,0.15)', color: '#fff',
                textDecoration: 'none', border: '1px solid rgba(255,255,255,0.25)',
                transition: 'background 0.15s'
              }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
              >
                🆔 ORCID
              </a>
              {faculty.email && (
                <a href={`mailto:${faculty.email}`} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '5px 12px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                  background: 'rgba(255,255,255,0.15)', color: '#fff',
                  textDecoration: 'none', border: '1px solid rgba(255,255,255,0.25)',
                  transition: 'background 0.15s'
                }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.25)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.15)'}
                >
                  ✉️ Email
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Workload summary */}
        <div style={{
          background: 'rgba(255,255,255,0.1)', borderRadius: 16,
          padding: '18px 24px', display: 'flex', gap: 24, flexWrap: 'wrap'
        }}>
          {[
            { label: 'Teaching Hours/wk', value: workload?.teaching_hours ?? '—', color: '#fff' },
            { label: 'Other Duties/wk', value: workload?.other_hours ?? '—', color: '#fde68a' },
            { label: 'Subjects Taught', value: subjects_taught.length, color: '#a5f3fc' },
          ].map(m => (
            <div key={m.label} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: m.color, fontFamily: 'DM Mono, monospace', lineHeight: 1 }}>{m.value}</div>
              <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)', marginTop: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{m.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: '#f0efe9', padding: 4, borderRadius: 12, width: 'fit-content' }}>
        {[
          { key: 'overview', label: '👤 Overview' },
          { key: 'timetable', label: '📅 Weekly Timetable' },
          { key: 'subjects', label: `📚 Subjects (${subjects_taught.length})` },
        ].map(tab => {
          const active = activeTab === tab.key
          return (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
              padding: '8px 18px', borderRadius: 9, border: 'none',
              background: active ? '#fff' : 'transparent',
              color: active ? '#7c3aed' : '#5a5a54',
              fontWeight: active ? 700 : 400, fontSize: 13,
              cursor: 'pointer', fontFamily: 'DM Sans, sans-serif',
              boxShadow: active ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.12s'
            }}>{tab.label}</button>
          )
        })}
      </div>

      {/* ── OVERVIEW ─────────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <Card title="Personal Details">
            <InfoRow label="Full Name" value={displayName} />
            <InfoRow label="Designation" value={faculty.designation} />
            <InfoRow label="Department" value={`${faculty.department_code} — ${faculty.department_name}`} />
            <InfoRow label="HoD" value={faculty.is_hod ? '✅ Yes' : 'No'} />
            <InfoRow label="Status" value={faculty.is_active ? 'Active' : 'Inactive'} />
          </Card>

          <Card title="Contact Information">
            <InfoRow label="Email" value={
              faculty.email
                ? <a href={`mailto:${faculty.email}`} style={{ color: '#2d5be3', textDecoration: 'none' }}>{faculty.email}</a>
                : '—'
            } />
            <InfoRow label="Phone" value={faculty.phone} />
          </Card>

          <Card title="Research & Academic Profiles" style={{ gridColumn: '1 / -1' }}>
            <p style={{ fontSize: 13, color: '#5a5a54', margin: '0 0 16px' }}>
              These links search for <strong>{displayName}</strong>'s publications and research profiles on external platforms.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
              {[
                { href: googleScholarUrl, icon: '🎓', label: 'Google Scholar', desc: 'Citations, papers & h-index', color: '#2d5be3', bg: '#eef2fc' },
                { href: researchGateUrl, icon: '🔬', label: 'ResearchGate', desc: 'Research publications & network', color: '#16a34a', bg: '#f0fdf4' },
                { href: orcidUrl, icon: '🆔', label: 'ORCID', desc: 'Researcher identifier & works', color: '#b45309', bg: '#fffbeb' },
                {
                  href: `https://www.scopus.com/results/authorNamesList.uri?st1=${encodeURIComponent(faculty.full_name.split(' ').pop())}&st2=${encodeURIComponent(faculty.full_name.split(' ')[0])}`,
                  icon: '📑', label: 'Scopus', desc: 'Peer-reviewed citations', color: '#7c3aed', bg: '#f5f3ff'
                },
              ].map(link => (
                <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer"
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '14px 16px', borderRadius: 12,
                    background: link.bg, border: `1px solid ${link.color}20`,
                    textDecoration: 'none', transition: 'transform 0.15s, box-shadow 0.15s'
                  }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)' }}
                  onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '' }}
                >
                  <span style={{ fontSize: 22 }}>{link.icon}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, color: link.color }}>{link.label}</div>
                    <div style={{ fontSize: 11, color: '#9a9a90', marginTop: 1 }}>{link.desc}</div>
                  </div>
                  <span style={{ marginLeft: 'auto', color: link.color, fontSize: 14 }}>↗</span>
                </a>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── TIMETABLE ────────────────────────────────────────────────── */}
      {activeTab === 'timetable' && (
        <Card title="Weekly Teaching Schedule">
          <WeeklyTimetable slots={timetable} />
          <div style={{ marginTop: 16, fontSize: 12, color: '#9a9a90' }}>
            Total slots: <strong>{workload?.total_slots ?? 0}</strong> · Teaching: <strong>{workload?.teaching_hours ?? 0}</strong> · Other duties: <strong>{workload?.other_hours ?? 0}</strong>
          </div>
        </Card>
      )}

      {/* ── SUBJECTS ─────────────────────────────────────────────────── */}
      {activeTab === 'subjects' && (
        <Card title={`Subjects Currently Assigned (${subjects_taught.length})`}>
          {subjects_taught.length === 0 ? (
            <p style={{ color: '#9a9a90', fontSize: 13, margin: 0 }}>No subjects assigned in the current timetable.</p>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
              {subjects_taught.map(sub => (
                <div key={sub.subject_code} style={{
                  background: '#f8f7f4', borderRadius: 12, padding: '14px 16px',
                  border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 6
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 13, color: '#7c3aed' }}>{sub.subject_code}</span>
                    <span style={{
                      fontSize: 10, fontWeight: 700, textTransform: 'uppercase', padding: '2px 7px', borderRadius: 5,
                      background: sub.subject_type === 'Theory' ? '#eef2fc' : sub.subject_type === 'Practical' ? '#f0fdf4' : '#fffbeb',
                      color: sub.subject_type === 'Theory' ? '#2d5be3' : sub.subject_type === 'Practical' ? '#16a34a' : '#b45309',
                    }}>{sub.subject_type}</span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#1a1a18', lineHeight: 1.3 }}>{sub.subject_name}</div>
                  <div style={{ fontSize: 11, color: '#9a9a90' }}>Semester {sub.semester_number}</div>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}