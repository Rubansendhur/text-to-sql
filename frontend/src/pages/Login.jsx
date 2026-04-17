import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      })

      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || 'Failed to login')
      }

      login(data)
      navigate('/dashboard')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const inputStyle = {
    width: '100%', padding: '12px 16px', borderRadius: 8, border: '1px solid #e2e0d8',
    fontSize: 14, fontFamily: 'DM Sans, sans-serif', outline: 'none',
    boxSizing: 'border-box', marginBottom: 20
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#f8f7f4', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#fff', padding: '40px', borderRadius: 20, border: '1px solid #e2e0d8', width: '100%', maxWidth: 400, boxShadow: '0 10px 40px -10px rgba(0,0,0,0.05)' }}>
        
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 44, height: 44, borderRadius: 12, background: '#2d5be3', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 700, letterSpacing: 0.5, margin: '0 auto 16px' }}>CIT</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: -0.5, color: '#1a1a18', margin: 0 }}>CIT Academic Portal</h1>
          <p style={{ fontSize: 13, color: '#5a5a54', marginTop: 4 }}>Coimbatore Institute of Technology</p>
        </div>

        {error && <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '12px 16px', borderRadius: 12, marginBottom: 20, fontSize: 13, textAlign: 'center' }}>{error}</div>}

        <form onSubmit={handleLogin}>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#1a1a18', marginBottom: 6 }}>Email Address</label>
          <input 
            type="email" 
            style={inputStyle} 
            placeholder="admin@cit.edu.in" 
            value={username} 
            onChange={e => setUsername(e.target.value)} 
            required 
          />

          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: '#1a1a18', marginBottom: 6 }}>Password</label>
          <input 
            type="password" 
            style={inputStyle} 
            placeholder="••••••••" 
            value={password} 
            onChange={e => setPassword(e.target.value)} 
            required 
          />

          <button 
            type="submit" 
            disabled={loading}
            style={{
              width: '100%', padding: '12px 0', background: '#2d5be3', color: '#fff', 
              border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer', 
              fontFamily: 'DM Sans, sans-serif', transition: 'all 0.2s', marginTop: 8,
              opacity: loading ? 0.7 : 1
            }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
        <div style={{ textAlign: 'center', marginTop: 32, paddingTop: 20, borderTop: '1px solid #e2e0d8', fontSize: 11, color: '#9a9a90', lineHeight: 1.5 }}>
          Restricted Academic Information System <br />
          &copy; {new Date().getFullYear()} Coimbatore Institute of Technology. All rights reserved.<br />
          <span style={{ fontWeight: 'bold' }}>Developed by Department of Decision and Computing Sciences</span> <br />
          <span style={{ fontFamily: 'DM Mono, monospace', marginTop: 4, display: 'inline-block' }}>v0.1 · DCS</span>
        </div>
      </div>
    </div>
  )
}
