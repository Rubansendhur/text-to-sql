import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext.jsx'
import ChangePasswordModal from './ChangePasswordModal.jsx'

const ROLES = {
  ADMIN: 'admin',
  CENTRAL_ADMIN: 'central-admin',
  HOD: 'hod',
  STAFF: 'staff',
}

const NAV = [
  {
    to: '/dashboard', label: 'Dashboard',
    roles: Object.values(ROLES),
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg>,
  },
  {
    to: '/students', label: 'Students',
    roles: [ROLES.ADMIN, ROLES.HOD],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>,
  },
  {
    to: '/faculty', label: 'Faculty',
    roles: [ROLES.ADMIN, ROLES.HOD],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" /></svg>,
  },
  {
    to: '/subjects', label: 'Subjects',
    roles: [ROLES.ADMIN, ROLES.HOD],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" /></svg>,
  },
  {
    to: '/arrears', label: 'Arrears',
    roles: [ROLES.ADMIN, ROLES.HOD],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>,
  },
  {
    to: '/timetable', label: 'Timetable',
    roles: [ROLES.ADMIN, ROLES.HOD],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>,
  },
  {
    to: '/upload', label: 'Data Upload',
    roles: [ROLES.ADMIN],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></svg>,
  },
  {
    to: '/chat', label: 'Ask AI',
    roles: Object.values(ROLES),
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
  },
  {
    to: '/users', label: 'Users',
    roles: [ROLES.CENTRAL_ADMIN],
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /></svg>,
  },

  {
    to: 'stats',
    label: 'Stats',
    roles: ['central-admin'], // 🔥 only admin can see
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <line x1="4" y1="20" x2="4" y2="10" />
        <line x1="10" y1="20" x2="10" y2="4" />
        <line x1="16" y1="20" x2="16" y2="14" />
        <line x1="22" y1="20" x2="22" y2="8" />
      </svg>
    ),
  }
]


export default function Sidebar({ open, onClose }) {
  const { user, logout } = useAuth()
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const location = useLocation()

  const userDept = user?.username ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() : ''
  const displayDept = userDept || 'Department'

  // Close sidebar on route change (mobile)
  useEffect(() => { onClose?.() }, [location.pathname])

  return (
    <>
      <aside
        className={`sidebar-main${open ? ' sidebar-open' : ''}`}
        style={{
          width: 200, flexShrink: 0,
          background: '#fff',
          borderRight: '1px solid #e2e0d8',
          display: 'flex', flexDirection: 'column',
          minHeight: '100vh', position: 'sticky', top: 0, height: '100vh',
        }}
      >
        {/* Brand */}
        <div style={{ padding: '18px 20px 16px', borderBottom: '1px solid #e2e0d8' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 30, height: 30, borderRadius: 8,
              background: '#2d5be3', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 700, letterSpacing: 0.5,
            }}>{displayDept.slice(0, 2)}</div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.2 }}>{displayDept} Monitor</div>
              <div style={{ fontSize: 10, color: '#9a9a90', fontFamily: 'DM Mono, monospace', marginTop: 1 }}>CIT · {user?.username?.split('@')[0] || 'Admin'}</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '12px 10px', overflowY: 'auto' }}>
          <div style={{ fontSize: 9, fontFamily: 'DM Mono, monospace', color: '#9a9a90', letterSpacing: '0.1em', textTransform: 'uppercase', padding: '8px 10px 6px' }}>
            Menu
          </div>
          {NAV.map(item => {
            if (!item.roles?.includes(user?.role)) return null
            return (
              <NavLink
                key={item.to}
                to={item.to}
                style={({ isActive }) => ({
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 12px', borderRadius: 10, marginBottom: 2,
                  fontSize: 13, fontWeight: 500, textDecoration: 'none',
                  transition: 'all 0.12s',
                  background: isActive ? '#eef2fc' : 'transparent',
                  color: isActive ? '#2d5be3' : '#5a5a54',
                })}
              >
                {({ isActive }) => (
                  <>
                    <span style={{ color: isActive ? '#2d5be3' : '#9a9a90', display: 'flex' }}>{item.icon}</span>
                    {item.label}
                  </>
                )}
              </NavLink>
            )
          })}
        </nav>

        {/* Footer */}
        <div style={{ padding: '14px 20px', borderTop: '1px solid #e2e0d8', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#1a1a18' }}>{user.username.split('@')[0]}</span>
                <button
                  onClick={() => setShowPasswordModal(true)}
                  style={{ background: 'none', border: 'none', color: '#2d5be3', fontSize: 10, fontWeight: 500, cursor: 'pointer', padding: 0, textAlign: 'left' }}
                >
                  Change Password
                </button>
              </div>
              <button
                onClick={logout}
                style={{ background: 'none', border: 'none', color: '#dc2626', fontSize: 11, fontWeight: 600, cursor: 'pointer', padding: 0 }}
              >
                Sign out
              </button>
            </div>
          )}
          <div style={{ fontSize: 10, fontFamily: 'DM Mono, monospace', color: '#9a9a90', textAlign: 'center' }}>v1.0 · {displayDept}</div>
        </div>
      </aside>

      {showPasswordModal && <ChangePasswordModal onClose={() => setShowPasswordModal(false)} />}
    </>
  )
}
