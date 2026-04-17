import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'

const HamburgerIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="3" y1="6" x2="21" y2="6"/>
    <line x1="3" y1="12" x2="21" y2="12"/>
    <line x1="3" y1="18" x2="21" y2="18"/>
  </svg>
)

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user } = useAuth()
  const displayDept = user?.username
    ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() || 'Monitor'
    : 'Monitor'

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Overlay for mobile */}
      <div
        className={`sidebar-overlay${sidebarOpen ? ' open' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <main style={{ flex: 1, minWidth: 0, height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Mobile topbar — hidden on desktop via CSS */}
        <div className="mobile-topbar">
          <button className="hamburger" onClick={() => setSidebarOpen(v => !v)} aria-label="Open menu">
            <HamburgerIcon />
          </button>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#1a1a18' }}>{displayDept} Monitor</div>
        </div>

        <div style={{ flex: 1, overflow: 'auto' }}>
          <Outlet />
        </div>

        <footer style={{
          padding: '14px 32px',
          borderTop: '1px solid #e2e0d8',
          background: '#fff',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
          color: '#5a5a54',
          fontSize: 12,
          fontFamily: 'DM Sans, sans-serif',
          textAlign: 'center',
        }}>
          <div style={{ fontWeight: 600, color: '#1a1a18', letterSpacing: '-0.2px' }}>
            &copy; {new Date().getFullYear()} Coimbatore Institute of Technology. All rights reserved.
          </div>
          <div style={{ color: '#d1cdc2' }}>|</div>
          <div style={{ fontWeight: 'bold' }}>
            Developed by Department of Decision and Computing Sciences
          </div>
        </footer>
      </main>
    </div>
  )
}
