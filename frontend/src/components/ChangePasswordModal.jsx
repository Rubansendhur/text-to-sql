import { useState } from 'react'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function ChangePasswordModal({ onClose }) {
  const { user } = useAuth()
  const token = user?.token
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (newPassword !== confirmPassword) {
      setStatus({ type: 'error', text: 'New passwords do not match' })
      return
    }
    
    setSaving(true)
    setStatus(null)
    
    try {
      const res = await fetch(`${API_BASE}/api/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
      })
      
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to update password')
      
      setStatus({ type: 'success', text: 'Password successfully updated' })
      setTimeout(onClose, 2000)
    } catch (err) {
      setStatus({ type: 'error', text: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(2px)' }}>
      <div style={{ background: '#fff', borderRadius: 16, width: 400, overflow: 'hidden', boxShadow: '0 20px 40px rgba(0,0,0,0.1)' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #e2e0d8', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: 16, fontWeight: 600 }}>Change Password</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#9a9a90' }}>&times;</button>
        </div>
        
        <form onSubmit={handleSubmit} style={{ padding: 24 }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>Current Password</label>
            <input required type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #e2e0d8', borderRadius: 8, fontFamily: 'inherit' }} />
          </div>
          
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>New Password</label>
            <input required type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #e2e0d8', borderRadius: 8, fontFamily: 'inherit' }} />
          </div>
          
          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: '#5a5a54', marginBottom: 6 }}>Confirm New Password</label>
            <input required type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #e2e0d8', borderRadius: 8, fontFamily: 'inherit' }} />
          </div>

          {status && (
            <div style={{ marginBottom: 20, fontSize: 13, padding: '10px 12px', borderRadius: 8, background: status.type === 'error' ? '#fef2f2' : '#f0fdf4', color: status.type === 'error' ? '#ef4444' : '#16a34a' }}>
              {status.text}
            </div>
          )}

          <div style={{ display: 'flex', gap: 12 }}>
            <button type="button" onClick={onClose}
              style={{ flex: 1, padding: '10px', background: '#f0efe9', color: '#5a5a54', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer' }}>Cancel</button>
            <button type="submit" disabled={saving}
              style={{ flex: 1, padding: '10px', background: '#2d5be3', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer' }}>
              {saving ? 'Updating...' : 'Update'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
