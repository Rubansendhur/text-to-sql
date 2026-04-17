import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE } from '../lib/api.js'
import { FacultyTimetable } from '../components/faculty/FacultyTimetable.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function Faculty() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [faculty,   setFaculty]   = useState([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [selected,  setSelected]  = useState(null)
  const [isAdmin,   setIsAdmin]   = useState(false)
  const [search,    setSearch]    = useState('')
  const [viewMode,  setViewMode]  = useState('cards') // 'cards' | 'timetable'

  useEffect(() => {
    if (user?.role === 'admin') setIsAdmin(true)
  }, [user])

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/faculty`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('no_data'); return r.json() })
      .then(d => { setFaculty(d.faculty || []); setError(null) })
      .catch(() => { setFaculty([]); setError('empty') })
      .finally(() => setLoading(false))
  }, [])

  const filtered = faculty.filter(f =>
    !search ||
    f.full_name.toLowerCase().includes(search.toLowerCase()) ||
    f.designation?.toLowerCase().includes(search.toLowerCase()) ||
    f.email?.toLowerCase().includes(search.toLowerCase())
  )

  const designationColor = (desig) => {
    if (!desig) return { bg: '#f8f7f4', text: '#5a5a54' }
    const d = desig.toLowerCase()
    if (d.includes('professor') && d.includes('associate')) return { bg: '#f0fdf4', text: '#16a34a' }
    if (d.includes('professor') && d.includes('assistant')) return { bg: '#eef2fc', text: '#2d5be3' }
    if (d.includes('professor')) return { bg: '#fdf4ff', text: '#7c3aed' }
    if (d.includes('lecturer')) return { bg: '#fffbeb', text: '#b45309' }
    return { bg: '#f8f7f4', text: '#5a5a54' }
  }

  return (
    <div className="page-container" style={{ maxWidth: 1300, margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3 }}>Faculty Directory</h1>
          <p style={{ fontSize: 13, color: '#5a5a54', marginTop: 3 }}>
            {filtered.length} faculty member{filtered.length !== 1 ? 's' : ''}
            <span style={{ marginLeft: 8, fontSize: 12, color: '#9a9a90' }}>· Click a card to view full profile</span>
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Search */}
          <input
            style={{
              padding: '7px 12px', borderRadius: 8, border: '1px solid #e2e0d8',
              background: '#fff', fontSize: 13, fontFamily: 'DM Sans, sans-serif',
              outline: 'none', width: 200
            }}
            placeholder="Search name, designation…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />

          {/* View mode toggle */}
          <div style={{ display: 'flex', gap: 2, background: '#f0efe9', padding: 3, borderRadius: 10 }}>
            {[{ key: 'cards', label: '⊞ Cards' }, { key: 'timetable', label: '📅 Timetable' }].map(({ key, label }) => {
              const active = viewMode === key
              return (
                <button key={key} onClick={() => setViewMode(key)} style={{
                  padding: '7px 14px', borderRadius: 8, border: 'none',
                  background: active ? '#fff' : 'transparent',
                  color: active ? '#7c3aed' : '#5a5a54',
                  fontWeight: active ? 600 : 400, fontSize: 12,
                  cursor: 'pointer',
                  boxShadow: active ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                  fontFamily: 'DM Sans, sans-serif', transition: 'all 0.12s'
                }}>{label}</button>
              )
            })}
          </div>

          {/* Admin mode toggle (only for admins) */}
          {user?.role === 'admin' && viewMode === 'timetable' && (
            <div style={{ display: 'flex', gap: 2, background: '#f0efe9', padding: 3, borderRadius: 10 }}>
              {['View', 'Edit'].map((label, i) => {
                const active = i === 1 ? isAdmin : !isAdmin
                return (
                  <button key={label} onClick={() => setIsAdmin(i === 1)} style={{
                    padding: '7px 14px', borderRadius: 8, border: 'none',
                    background: active ? '#fff' : 'transparent',
                    color: active ? '#2d5be3' : '#5a5a54',
                    fontWeight: active ? 600 : 400, fontSize: 12,
                    cursor: 'pointer',
                    boxShadow: active ? '0 1px 4px rgba(0,0,0,0.08)' : 'none',
                    fontFamily: 'DM Sans, sans-serif', transition: 'all 0.12s'
                  }}>{label}</button>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {!loading && faculty.length === 0 && (
        <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', color: '#0369a1', padding: '12px 18px', borderRadius: 12, marginBottom: 20, fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>📋</span>
          <span>No faculty data found. Add faculty members via the Data Upload page.</span>
        </div>
      )}

      {/* ── CARDS VIEW ──────────────────────────────────────────────── */}
      {viewMode === 'cards' && (
        <>
          {loading ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
              {[1,2,3,4,5,6].map(i => (
                <div key={i} style={{ height: 160, borderRadius: 14, background: '#f0efe9' }} />
              ))}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
              {filtered.map(f => {
                const dc = designationColor(f.designation)
                const initials = f.full_name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('')
                return (
                  <div
                    key={f.faculty_id}
                    onClick={() => navigate(`/faculty/${f.faculty_id}`)}
                    style={{
                      background: '#fff', borderRadius: 14, border: '1px solid #e2e0d8',
                      padding: '20px', cursor: 'pointer', transition: 'all 0.15s',
                      display: 'flex', flexDirection: 'column', gap: 14,
                      position: 'relative', overflow: 'hidden'
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.borderColor = '#7c3aed'
                      e.currentTarget.style.transform = 'translateY(-2px)'
                      e.currentTarget.style.boxShadow = '0 8px 24px rgba(124,58,237,0.1)'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.borderColor = '#e2e0d8'
                      e.currentTarget.style.transform = ''
                      e.currentTarget.style.boxShadow = ''
                    }}
                  >
                    {/* HoD badge */}
                    {f.is_hod && (
                      <div style={{
                        position: 'absolute', top: 12, right: 12,
                        fontSize: 9, fontWeight: 800, textTransform: 'uppercase',
                        background: '#fef3c7', color: '#b45309',
                        padding: '2px 8px', borderRadius: 20, letterSpacing: '0.05em'
                      }}>HoD</div>
                    )}

                    {/* Avatar + name */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 46, height: 46, borderRadius: '50%',
                        background: 'linear-gradient(135deg, #7c3aed, #2d5be3)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 16, fontWeight: 800, color: '#fff', flexShrink: 0,
                        letterSpacing: -0.5
                      }}>{initials}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 14, color: '#1a1a18', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {f.title} {f.full_name}
                        </div>
                        <span style={{
                          display: 'inline-block', marginTop: 4,
                          fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                          padding: '2px 7px', borderRadius: 5,
                          background: dc.bg, color: dc.text
                        }}>{f.designation}</span>
                      </div>
                    </div>

                    {/* Contact */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {f.email && (
                        <div style={{ fontSize: 11, color: '#9a9a90', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          ✉️ {f.email}
                        </div>
                      )}
                      {f.phone && (
                        <div style={{ fontSize: 11, color: '#9a9a90' }}>📞 {f.phone}</div>
                      )}
                    </div>

                    {/* Footer */}
                    <div style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      paddingTop: 12, borderTop: '1px solid #f0efe9'
                    }}>
                      <span style={{ fontSize: 11, color: '#9a9a90' }}>{f.department_code}</span>
                      <span style={{ fontSize: 12, color: '#7c3aed', fontWeight: 600 }}>View profile →</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* ── TIMETABLE VIEW ──────────────────────────────────────────── */}
      {viewMode === 'timetable' && (
        <div className="faculty-layout" style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 20 }}>
          {/* Faculty list panel */}
          <div className="faculty-list-panel" style={{
            background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8',
            padding: 12, maxHeight: '80vh', overflowY: 'auto'
          }}>
            {/* Search within list */}
            <input
              style={{
                width: '100%', padding: '7px 10px', borderRadius: 8,
                border: '1px solid #e2e0d8', fontSize: 12,
                fontFamily: 'DM Sans, sans-serif', outline: 'none',
                marginBottom: 8, boxSizing: 'border-box'
              }}
              placeholder="Filter faculty…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {loading ? (
              [1,2,3,4,5].map(i => (
                <div key={i} style={{ height: 64, borderRadius: 10, background: '#f0efe9', marginBottom: 8 }} />
              ))
            ) : filtered.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#9a9a90', padding: '24px 0', fontSize: 13 }}>No faculty found.</div>
            ) : filtered.map(f => {
              const active = selected?.faculty_id === f.faculty_id
              return (
                <button key={f.faculty_id} onClick={() => setSelected(f)} style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '10px 12px', borderRadius: 10,
                  border: `1.5px solid ${active ? '#c5b0f8' : 'transparent'}`,
                  background: active ? '#f5f3ff' : 'transparent',
                  cursor: 'pointer', marginBottom: 4,
                  fontFamily: 'DM Sans, sans-serif', transition: 'all 0.1s'
                }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: active ? '#7c3aed' : '#1a1a18' }}>
                    {f.title} {f.full_name}
                  </div>
                  <div style={{ fontSize: 11, color: '#9a9a90', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.designation}
                  </div>
                </button>
              )
            })}
          </div>

          {/* Timetable area */}
          <div>
            {selected ? (
              <div>
                {/* Quick profile link */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#1a1a18' }}>
                    {selected.title} {selected.full_name}
                    <span style={{ fontSize: 12, color: '#9a9a90', fontWeight: 400, marginLeft: 8 }}>{selected.designation}</span>
                  </div>
                  <button
                    onClick={() => navigate(`/faculty/${selected.faculty_id}`)}
                    style={{
                      padding: '6px 14px', borderRadius: 8,
                      border: '1px solid #7c3aed', background: '#f5f3ff',
                      color: '#7c3aed', fontSize: 12, fontWeight: 600,
                      cursor: 'pointer', fontFamily: 'DM Sans, sans-serif'
                    }}
                  >View Full Profile →</button>
                </div>
                <FacultyTimetable faculty={selected} isAdmin={isAdmin} />
              </div>
            ) : (
              <div style={{ height: 400, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8' }}>
                <div style={{ textAlign: 'center', color: '#9a9a90' }}>
                  <div style={{ fontSize: 32, marginBottom: 10 }}>👤</div>
                  <div style={{ fontSize: 14, fontWeight: 500 }}>Select a faculty member</div>
                  <div style={{ fontSize: 12, marginTop: 4 }}>to view their weekly timetable</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}