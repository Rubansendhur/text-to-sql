import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function Dashboard() {
  const { user } = useAuth();
  const displayDept = user?.department_code || (user?.username ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() || 'Department' : 'Department');

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const ROLES = {
    ADMIN: 'admin',
    CENTRAL_ADMIN: 'central-admin',
    HOD: 'hod',
    STAFF: 'staff',
  }

  function hasAccess(userRole, allowedRoles) {
    return allowedRoles.includes(userRole)
  }

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/summary`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('no_data'); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(() => { setData({}); setLoading(false) })
  }, [])

  const metrics = [
    { label: 'Active Students', value: data?.active_students ?? '—', bg: '#eef2fc', color: '#2d5be3' },
    { label: 'Hostellers', value: data?.hostellers ?? '—', bg: '#f0fdf4', color: '#16a34a' },
    { label: 'Avg GPA', value: data?.dept_avg_gpa ?? '—', bg: '#fef9c3', color: '#b45309' },
    { label: 'Active Arrears', value: data?.students_with_arrears ?? '—', bg: '#fef2f2', color: '#dc2626' },
    { label: 'Total Faculty', value: data?.total_faculty ?? '—', bg: '#f5f3ff', color: '#7c3aed' },
  ]

  return (
    <div className="page-container" style={{ maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5, marginBottom: 4 }}>
          Department Dashboard
        </h1>
        <p style={{ fontSize: 13, color: '#5a5a54' }}>
          Overview · {displayDept} · CIT
        </p>
      </div>

      {!loading && data && (data.active_students === 0 && data.total_faculty === 0) && (
        <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', color: '#0369a1', padding: '12px 18px', borderRadius: 12, marginBottom: 24, fontSize: 13, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 18 }}>📋</span>
          <span>No data has been uploaded for <strong>{displayDept}</strong> yet. Upload student and faculty records to see live metrics here.</span>
        </div>
      )}

      <div className="metrics-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 40 }}>
        {metrics.map((m, i) => (
          <div key={i} style={{
            background: loading ? '#f5f4f0' : m.bg,
            borderRadius: 16, padding: '24px 20px',
            border: '1px solid rgba(0,0,0,0.04)',
            transition: 'transform 0.15s',
            cursor: 'default',
          }}
            onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
            onMouseLeave={e => e.currentTarget.style.transform = 'translateY(0)'}
          >
            <div style={{ fontSize: 11, fontWeight: 500, color: loading ? '#ccc' : m.color, marginBottom: 8, opacity: 0.8 }}>
              {m.label}
            </div>
            <div style={{ fontSize: 36, fontWeight: 800, color: loading ? '#ddd' : m.color, letterSpacing: -1, fontFamily: 'DM Mono, monospace' }}>
              {loading ? '…' : m.value}
            </div>
          </div>
        ))}
      </div>

      <div className="quickaccess-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {hasAccess(user?.role, [ROLES.ADMIN, ROLES.HOD]) && (
          <a href="/students" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#2d5be3'} onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#eef2fc', color: '#2d5be3', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>👨‍🎓</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>Manage Students</div>
              <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>View directory, filter by status or hostel, and check CGPA.</div>
            </div>
          </a>)}

        {hasAccess(user?.role, [ROLES.ADMIN, ROLES.HOD]) && (
          <a href="/faculty" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#7c3aed'} onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#f5f3ff', color: '#7c3aed', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>👨‍🏫</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>Faculty Directory</div>
              <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>Browse faculty members, designations, and assign classes.</div>
            </div>
          </a>)}

        {hasAccess(user?.role, [ROLES.ADMIN, ROLES.HOD]) && (
          <a href="/subjects" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#f59e0b'} onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#fffbeb', color: '#b45309', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>📚</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>View Subjects</div>
              <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>Explore the curriculum, view subject codes, and credit info.</div>
            </div>
          </a>)}

        {hasAccess(user?.role, [ROLES.ADMIN, ROLES.HOD]) && (
          <a href="/timetable" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#16a34a'} onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>📅</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>Timetable Builder</div>
              <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>Drag & drop interface to build and manage class schedules.</div>
            </div>
          </a>)}

        {hasAccess(user?.role, [ROLES.ADMIN, ROLES.HOD]) && (
          <a href="/arrears" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#dc2626'} onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#fef2f2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>⚠️</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>Track Arrears</div>
              <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>Identify students needing intervention across all semesters.</div>
            </div>
          </a>)}


        {hasAccess(user?.role, [ROLES.ADMIN]) && (
          <a href="/upload" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#0891b2'}
            onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: '#ecfeff', color: '#0891b2', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>☁️</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>Data Upload</div>
              <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>Batch upload CSV data for students, faculty, and results.</div>
            </div>
          </a>
        )}

        <a href="/chat" style={{ textDecoration: 'none', background: '#fff', borderRadius: 16, padding: '24px', border: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12, transition: 'all 0.2s', color: 'inherit' }}
          onMouseEnter={e => e.currentTarget.style.borderColor = '#b45309'} onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: 'linear-gradient(135deg,#fcd34d,#f59e0b)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>✦</div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, color: '#1a1a18' }}>Ask AI</div>
            <div style={{ fontSize: 13, color: '#5a5a54', lineHeight: 1.4 }}>Query the department database directly using natural language.</div>
          </div>
        </a>

        {hasAccess(user?.role, [ROLES.CENTRAL_ADMIN]) && (
          <a href="/users"
            style={{
              textDecoration: 'none',
              background: '#fff',
              borderRadius: 16,
              padding: '24px',
              border: '1px solid #e2e0d8',
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
              transition: 'all 0.2s',
              color: 'inherit'
            }}
            onMouseEnter={e => e.currentTarget.style.borderColor = '#2563eb'}
            onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}
          >
            {/* Icon */}
            <div style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: '#eff6ff',
              color: '#2563eb',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>

            {/* Text */}
            <div>
              <div style={{
                fontWeight: 600,
                fontSize: 15,
                marginBottom: 4,
                color: '#1a1a18'
              }}>
                Manage Users
              </div>
              <div style={{
                fontSize: 13,
                color: '#5a5a54',
                lineHeight: 1.4
              }}>
                Create, update, and control access for all departments and roles.
              </div>
            </div>
          </a>
        )}
      </div>
    </div>
  )
}
