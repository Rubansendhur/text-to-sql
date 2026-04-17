import { useState, useEffect } from 'react'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function UserManagement() {
  const { user } = useAuth()
  const token = user?.token
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [departments, setDepartments] = useState([])

  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState('hod')
  const [newDept, setNewDept] = useState('')
  const [adding, setAdding] = useState(false)
  const [addMsg, setAddMsg] = useState(null)

  useEffect(() => {
    fetchUsers()
    fetchDepartments()
  }, [])

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to fetch users')
      const data = await res.json()
      setUsers(data.users || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchDepartments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/departments/all`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })

      if (!res.ok) throw new Error("Failed to fetch departments")

      const data = await res.json()
      setDepartments(data.departments || [])

    } catch (err) {
      console.error(err)
    }
  }

  const handleAddUser = async (e) => {
    e.preventDefault()
    setAdding(true)
    setAddMsg(null)
    try {
      const res = await fetch(`${API_BASE}/api/users`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ username: newUsername, password: newPassword, role: newRole, department_code: newDept })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to add user')

      setAddMsg({ type: 'success', text: 'User added successfully!' })
      setNewUsername('')
      setNewPassword('')
      fetchUsers()
    } catch (err) {
      setAddMsg({ type: 'error', text: err.message })
    } finally {
      setAdding(false)
    }
  }

  return (
    <div style={{ padding: '32px 40px', maxWidth: 1000, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5, marginBottom: 24 }}>System Users</h1>

      {error && <div style={{ background: '#fef2f2', color: '#dc2626', padding: '12px 16px', borderRadius: 8, marginBottom: 20 }}>{error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 1fr) 2fr', gap: 24, alignItems: 'start' }}>
        {/* Add User Form */}
        <form onSubmit={handleAddUser} style={{ background: '#fff', padding: 24, borderRadius: 16, border: '1px solid #e2e0d8', boxShadow: '0 2px 8px rgba(0,0,0,0.02)' }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Add New User</h2>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>Email / Username</label>
            <input required type="email" value={newUsername} onChange={e => setNewUsername(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e0d8', borderRadius: 8, fontFamily: 'inherit' }} />
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>Temporary Password</label>
            <input required type="text" value={newPassword} onChange={e => setNewPassword(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e0d8', borderRadius: 8, fontFamily: 'inherit' }} />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>Role</label>
            <select value={newRole} onChange={e => setNewRole(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', border: '1px solid #e2e0d8', borderRadius: 8, fontFamily: 'inherit', background: '#fff' }}>
              <option value="hod">HOD</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>Department</label>
            <select
              required
              value={newDept}
              onChange={e => setNewDept(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #e2e0d8',
                borderRadius: 8,
                fontFamily: 'inherit',
                background: '#fff'
              }}
            >
              <option value="">Select Department</option>

              {departments.map(d => (
                <option key={d.department_code} value={d.department_code}>
                  {d.department_code} — {d.department_name}
                </option>
              ))}
            </select>
          </div>

          {addMsg && (
            <div style={{ marginBottom: 16, fontSize: 13, padding: '8px 12px', borderRadius: 6, background: addMsg.type === 'error' ? '#fef2f2' : '#f0fdf4', color: addMsg.type === 'error' ? '#ef4444' : '#16a34a' }}>
              {addMsg.text}
            </div>
          )}

          <button type="submit" disabled={adding}
            style={{ width: '100%', padding: '10px', background: '#2d5be3', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: adding ? 'not-allowed' : 'pointer' }}>
            {adding ? 'Adding...' : 'Create User'}
          </button>
        </form>

        {/* Users List */}
        <div style={{ background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,0,0,0.02)' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#faf9f6', borderBottom: '1px solid #e2e0d8' }}>
                <th style={{ padding: '12px 20px', fontWeight: 600, color: '#5a5a54' }}>ID</th>
                <th style={{ padding: '12px 20px', fontWeight: 600, color: '#5a5a54' }}>Username</th>
                <th style={{ padding: '12px 20px', fontWeight: 600, color: '#5a5a54' }}>Dept</th>
                <th style={{ padding: '12px 20px', fontWeight: 600, color: '#5a5a54' }}>Role</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="3" style={{ padding: 20, textAlign: 'center', color: '#9a9a90' }}>Loading users...</td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan="3" style={{ padding: 20, textAlign: 'center', color: '#9a9a90' }}>No users found.</td></tr>
              ) : users.map(u => (
                <tr key={u.user_id} style={{ borderBottom: '1px solid #f0efe9' }}>
                  <td style={{ padding: '12px 20px', color: '#5a5a54' }}>{u.user_id}</td>
                  <td style={{ padding: '12px 20px', fontWeight: 500 }}>{u.username}</td>
                  <td style={{ padding: '12px 20px', fontWeight: 700, color: '#1a1a18' }}>{u.department_code || '—'}</td>
                  <td style={{ padding: '12px 20px' }}>
                    <span style={{
                      padding: '4px 8px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                      background: u.role === 'central-admin' ? '#fef2f2' : u.role === 'admin' ? '#eff6ff' : '#f0fdf4',
                      color: u.role === 'central-admin' ? '#ef4444' : u.role === 'admin' ? '#3b82f6' : '#16a34a'
                    }}>
                      {u.role.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
