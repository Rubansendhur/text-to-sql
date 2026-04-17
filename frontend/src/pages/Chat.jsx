import { useEffect, useRef, useState } from 'react'
import { API_BASE, authHeaders } from '../lib/api.js'
import { MessageBubble } from '../components/chat/MessageBubble.jsx'
import { useAuth } from '../contexts/AuthContext.jsx'

const STARTERS = [
  'How many active students are there?',
  'Which students have more than 2 arrears?',
  'List all faculty members and their designations.',
  'How many students are hostellers vs day scholars?',
  'Show me 8th semester students from the 2022 batch.',
]

const RESPONSIBLE_USAGE = [
  {
    label: 'Use for academic support',
    example: 'Show the timetable for Tuesday 3rd hour.',
  },
  {
    label: 'Prefer aggregation over personal data',
    example: 'How many students are hostellers in 8th semester?',
  },
  {
    label: 'Avoid secrets or private data',
    example: 'Do not ask for passwords, OTPs, or API keys.',
  },
  {
    label: 'Keep requests narrow and authorized',
    example: 'Show your own department data only; AIML logins will not return DCS details.',
  },
]

const CHAT_REQUEST_TIMEOUT_MS = 140000  // 140s to give backend time to finish

let _uid = 0
const uid = () => String(++_uid)

function withFallbackApiBase(base) {
  if (base.includes('localhost')) {
    return [base, base.replace('localhost', '127.0.0.1')]
  }
  return [base]
}

async function postChatWithRetry(user, payload) {
  const candidates = withFallbackApiBase(API_BASE)
  let lastError = null

  for (const base of candidates) {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), CHAT_REQUEST_TIMEOUT_MS)

      const resp = await fetch(`${base}/api/chat`, {
        method: 'POST',
        headers: authHeaders(user, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      clearTimeout(timeout)

      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        throw new Error(data?.detail || data?.error || `Chat request failed (${resp.status})`)
      }
      return data
    } catch (err) {
      lastError = err
    }
  }

  throw lastError || new Error('Failed to reach backend chat API')
}

async function postFeedback(user, payload) {
  const candidates = withFallbackApiBase(API_BASE)
  let lastError = null

  for (const base of candidates) {
    try {
      const resp = await fetch(`${base}/api/chat/feedback`, {
        method: 'POST',
        headers: authHeaders(user, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok || data?.ok === false) {
        throw new Error(data?.message || data?.detail || `Feedback failed (${resp.status})`)
      }
      return data
    } catch (err) {
      lastError = err
    }
  }

  throw lastError || new Error('Failed to save feedback')
}

export default function Chat() {
  const { user } = useAuth();
  const displayDept = user?.department_code || (user?.username ? user.username.split('@')[0].replace(/hod|admin|central/i, '').toUpperCase() || 'Department' : 'Department');
  const userScope = `${user?.username || 'guest'}_${user?.department_code || 'nodept'}`
  const storageKey = `chat_history_${userScope}`
  const sessionStorageKey = `chat_session_${userScope}`

  const welcomeMsg = {
    id: uid(), role: 'ai',
    text: `Hello! I can answer questions about ${displayDept} students, faculty, arrears, and timetables. Try asking something below!`,
  }

  const loadHistory = () => {
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        const parsed = JSON.parse(saved)
        // strip any dangling loading bubbles from a previous crash
        return parsed.filter(m => !m.loading)
      }
    } catch {}
    return [welcomeMsg]
  }

  const loadSession = () => {
    try {
      const saved = localStorage.getItem(sessionStorageKey)
      return saved ? JSON.parse(saved) : null
    } catch {}
    return null
  }

  const [messages, setMessages] = useState(loadHistory)
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const [model,   setModel]   = useState(null)
  const [sessionId, setSessionId] = useState(loadSession)
  const bottomRef = useRef(null)

  useEffect(() => {
    setMessages(loadHistory())
    setSessionId(loadSession())
  }, [storageKey, sessionStorageKey])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Persist messages to localStorage on every change (skip while loading)
  useEffect(() => {
    if (!loading) {
      try { 
        localStorage.setItem(storageKey, JSON.stringify(messages))
        if (sessionId) {
          localStorage.setItem(sessionStorageKey, JSON.stringify(sessionId))
        }
      } catch {}
    }
  }, [messages, loading, sessionId, storageKey, sessionStorageKey])

  useEffect(() => {
    fetch(`${API_BASE}/api/model`, { headers: authHeaders(user) })
      .then(r => r.json())
      .then(d => setModel(d.model))
      .catch(() => {})
  }, [user?.token, user?.username])

  async function send(question) {
    const q = (question ?? input).trim()
    if (!q || loading) return
    setInput('')
    setLoading(true)
    const userMsg   = { id: uid(), role: 'user', text: q }
    const loadingId = uid()
    setMessages(prev => [...prev, userMsg, { id: loadingId, role: 'ai', text: '', loading: true }])
    try {
      const data = await postChatWithRetry(user, {
        question: q,
        role: user?.role || 'hod',
        session_id: sessionId,
      })
      
      // Store session ID from first response
      if (data.session_id && !sessionId) {
        setSessionId(data.session_id)
      }
      
      // Extract rows from data field based on display_type
      let rows = []
      let displayType = data.display_type || 'text'
      
      if ((displayType === 'table' || displayType === 'timetable') && data.data?.rows) {
        rows = data.data.rows
      } else if (data.rows) {
        rows = data.rows
      }
      
      const aiMsg = {
        id: uid(), 
        role: 'ai',
        message_id: data.message_id,
        feedback_score: null,
        session_id: data.session_id,
        display_type: displayType,
        text:    data.summary  || data.error || 'Something went wrong.',
        sql:     data.sql      || undefined,
        rows:    rows,
        columns: data.columns  || [],
        error:   data.error    || undefined,
        ms:      data.execution_ms,
        model:   data.model_used !== 'none' ? data.model_used : undefined,
      }
      setMessages(prev => [...prev.slice(0, -1), aiMsg])
    } catch (e) {
      const msg = e?.name === 'AbortError'
        ? 'Request timed out. Please try again.'
        : (e?.message || 'Network error')
      setMessages(prev => [...prev.slice(0, -1), { id: uid(), role: 'ai', text: '', error: msg }])
    } finally {
      setLoading(false)
    }
  }

  async function submitFeedback(messageId, score) {
    if (!messageId || !score) return

    setMessages(prev => prev.map(m => (
      m.message_id === messageId
        ? { ...m, feedback_pending: true, feedback_error: null }
        : m
    )))

    try {
      await postFeedback(user, { message_id: messageId, feedback_score: score })
      setMessages(prev => prev.map(m => (
        m.message_id === messageId
          ? { ...m, feedback_score: score, feedback_pending: false, feedback_error: null }
          : m
      )))
    } catch (e) {
      setMessages(prev => prev.map(m => (
        m.message_id === messageId
          ? {
              ...m,
              feedback_pending: false,
              feedback_error: e?.message || 'Could not save feedback',
            }
          : m
      )))
    }
  }

  function clearChat() {
    const fresh = [{ id: uid(), role: 'ai', text: `Hello! I can answer questions about ${displayDept} students, faculty, arrears, and timetables. Try asking something below!` }]
    setMessages(fresh)
    setSessionId(null) // Clear session for new conversation
    try { 
      localStorage.setItem(storageKey, JSON.stringify(fresh))
      localStorage.removeItem(sessionStorageKey) // Clear stored session ID
    } catch {}
  }

  return (
    <div style={{ padding: '24px 32px', flex: 1, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, background: '#fff', overflow: 'hidden', border: '1px solid #e2e0d8', borderRadius: 16 }}>
        {/* Header */}
        <div style={{ padding: '16px 24px', borderBottom: '3px solid #e2e0d8', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 38, height: 38, borderRadius: 12, background: 'linear-gradient(135deg,#2d5be3,#7c3aed)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 18 }}>✦</div>
              <div>
                <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Ask AI</h1>
                <p style={{ margin: 0, fontSize: 12, color: '#9a9a90' }}>
                  Ask questions about {displayDept} students, faculty &amp; arrears
                  {model && <span> · <span style={{ color: '#2d5be3' }}>{model}</span></span>}
                </p>
              </div>
            </div>
            {messages.length > 1 && (
              <button onClick={clearChat} title="Clear chat history"
                style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #e2e0d8', background: '#fafaf8', color: '#9a9a90', fontSize: 12, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif', transition: 'all 0.12s' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = '#dc2626'; e.currentTarget.style.color = '#dc2626' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e0d8'; e.currentTarget.style.color = '#9a9a90' }}
              >🗑 Clear chat</button>
            )}
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          <div style={{ marginBottom: 14, padding: '14px 16px', borderRadius: 14, border: '1px solid #dbeafe', background: 'linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%)' }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: '#2563eb', marginBottom: 8 }}>
              Ethical AI &amp; Responsible Usage
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {RESPONSIBLE_USAGE.map(item => (
                <div key={item.label} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12, color: '#1f2937', lineHeight: 1.5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 999, background: '#2563eb', marginTop: 6, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontWeight: 700 }}>{item.label}</div>
                    <div style={{ color: '#4b5563' }}>{item.example}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          {messages.map(msg => (
            <MessageBubble
              key={msg.id}
              msg={msg}
              onFeedback={submitFeedback}
            />
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Starters */}
        {messages.length <= 1 && (
          <div style={{ padding: '0 24px 12px', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {STARTERS.map(s => (
              <button key={s} onClick={() => send(s)} style={{ padding: '7px 14px', borderRadius: 20, border: '2px solid #e2e0d8', background: '#f8f7f4', color: '#5a5a54', fontSize: 12, cursor: 'pointer', transition: 'border-color 0.1s', fontFamily: 'DM Sans, sans-serif' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = '#2d5be3'}
                onMouseLeave={e => e.currentTarget.style.borderColor = '#e2e0d8'}
              >{s}</button>
            ))}
          </div>
        )}

        {/* Input */}
        <div style={{ padding: '12px 24px 20px', borderTop: '3px solid #e2e0d8', flexShrink: 0 }}>
          <form onSubmit={e => { e.preventDefault(); send() }} style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder={`Ask anything about ${displayDept} students, faculty, arrears…`}
              rows={1}
              style={{ flex: 1, padding: '10px 14px', borderRadius: 12, border: '2px solid #e2e0d8', fontSize: 14, resize: 'none', outline: 'none', lineHeight: 1.5, fontFamily: 'DM Sans, sans-serif', transition: 'border-color 0.15s' }}
              onFocus={e => e.target.style.borderColor = '#2d5be3'}
              onBlur={e  => e.target.style.borderColor = '#e2e0d8'}
            />
            <button type="submit" disabled={loading || !input.trim()} style={{ padding: '10px 20px', borderRadius: 12, border: 'none', background: loading || !input.trim() ? '#e2e0d8' : '#2d5be3', color: loading || !input.trim() ? '#9a9a90' : '#fff', fontWeight: 600, fontSize: 14, cursor: loading || !input.trim() ? 'not-allowed' : 'pointer', transition: 'all 0.15s', whiteSpace: 'nowrap', fontFamily: 'DM Sans, sans-serif' }}>
              {loading ? '…' : 'Send ↵'}
            </button>
          </form>
          <div style={{ fontSize: 10, color: '#9a9a90', marginTop: 6, textAlign: 'center' }}>
            Enter to send · Shift+Enter for new line
          </div>
        </div>
      </div>
    </div>
  )
}
