import { useState } from 'react'
import { ResultTable } from './ResultTable.jsx'
import { ResultTimetable } from './ResultTimetable.jsx'

// ── Markdown renderer ──────────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return ''
  let s = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  s = s.replace(/```[\s\S]*?```/g, match => {
    const code = match.replace(/^```[^\n]*\n?/, '').replace(/\n?```$/, '')
    return `<pre style="margin:8px 0;padding:8px 12px;background:#1e293b;color:#94a3b8;border-radius:7px;font-size:11px;overflow-x:auto;white-space:pre-wrap">${code}</pre>`
  })
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/\*([^*\n]+?)\*/g, '<em>$1</em>')
  s = s.replace(/`([^`]+)`/g, '<code style="background:#f3f4f6;padding:1px 5px;border-radius:4px;font-size:12px">$1</code>')
  s = s.replace(/((?:^|\n)- .+)+/g, match => {
    const items = match.trim().split('\n').map(line => {
      const content = line.replace(/^-\s*/, '')
      return `<li style="margin:2px 0">${content}</li>`
    }).join('')
    return `<ul style="margin:6px 0 6px 18px;padding:0">${items}</ul>`
  })
  s = s.replace(/\n\n/g, '</p><p style="margin:6px 0">')
  s = s.replace(/\n/g, '<br>')
  return s
}

// Detect if the summary starts with a followup acknowledgement prefix
function extractFollowupPrefix(text) {
  if (!text) return { prefix: null, body: text }
  // Matches: "Sure! Here's X's timetable:\n\n..." or "Got it — here are the results:\n\n..."
  const m = text.match(/^(Sure[^!]*!.*?:|Got it[^—]*—.*?:)\n\n([\s\S]*)$/s)
  if (m) return { prefix: m[1], body: m[2] }
  return { prefix: null, body: text }
}

// ── Typing indicator ───────────────────────────────────────────────────────────
function ThinkingDots() {
  return (
    <div style={{
      display: 'flex', gap: 5, alignItems: 'center',
      padding: '13px 18px', background: '#f9fafb',
      borderRadius: '4px 18px 18px 18px', border: '1px solid #e5e7eb',
    }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: '50%', background: '#6b7280',
          animation: `pulse-dot 1.4s ease-in-out ${i * 0.22}s infinite`,
        }} />
      ))}
      <span style={{ fontSize: 11, color: '#9ca3af', marginLeft: 4 }}>thinking…</span>
      <style>{`
        @keyframes pulse-dot {
          0%,80%,100% { transform: scale(0.7); opacity: 0.5; }
          40%          { transform: scale(1.1); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

// ── Bot avatar ─────────────────────────────────────────────────────────────────
function BotAvatar() {
  return (
    <div style={{
      width: 32, height: 32, borderRadius: 10, flexShrink: 0,
      background: 'linear-gradient(135deg,#2d5be3,#7c3aed)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 13, color: '#fff', fontWeight: 700,
    }}>✦</div>
  )
}

// ── Followup context badge ─────────────────────────────────────────────────────
function FollowupBadge({ text }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      background: '#eff6ff', border: '1px solid #bfdbfe',
      borderRadius: 20, padding: '3px 10px',
      fontSize: 11, color: '#2563eb', fontWeight: 600,
      marginBottom: 8,
    }}>
      <span style={{ fontSize: 13 }}>↩</span>
      <span>{text}</span>
    </div>
  )
}

// ── Row count pill ─────────────────────────────────────────────────────────────
function RowPill({ count }) {
  if (!count) return null
  return (
    <span style={{
      background: '#f0fdf4', border: '1px solid #bbf7d0',
      borderRadius: 20, padding: '1px 8px',
      fontSize: 10, color: '#15803d', fontWeight: 600,
    }}>{count} row{count !== 1 ? 's' : ''}</span>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────
export function MessageBubble({ msg, onFeedback }) {
  const [showSql, setShowSql] = useState(false)

  // User bubble
  if (msg.role === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
        <div style={{
          background: '#2d5be3', color: '#fff',
          borderRadius: '18px 18px 4px 18px',
          padding: '10px 16px', maxWidth: '72%',
          fontSize: 14, lineHeight: 1.55, wordBreak: 'break-word',
          boxShadow: '0 1px 4px rgba(45,91,227,0.18)',
        }}>
          {msg.text}
        </div>
      </div>
    )
  }

  // AI bubble
  const isClarify = msg.display_type === 'clarify' || msg.awaiting_clarification
  const bubbleBg  = isClarify ? '#eff6ff' : '#f9fafb'
  const bubbleBorder = isClarify ? '1px solid #93c5fd' : '1px solid #e5e7eb'

  if (msg.loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 14 }}>
        <div style={{ display: 'flex', gap: 10, maxWidth: '88%' }}>
          <BotAvatar />
          <ThinkingDots />
        </div>
      </div>
    )
  }

  // Pull out followup prefix from summary text
  const { prefix: followupPrefix, body: summaryBody } = extractFollowupPrefix(msg.text || '')

  // Extract day filter from question for timetable highlight
  const DAY_MAP = { monday:'Mon', mon:'Mon', tuesday:'Tue', tue:'Tue', tues:'Tue',
    wednesday:'Wed', wed:'Wed', thursday:'Thu', thu:'Thu', friday:'Fri', fri:'Fri', saturday:'Sat', sat:'Sat' }
  const highlightDay = (() => {
    const q = (msg.question || msg.text || '').toLowerCase()
    for (const [k, v] of Object.entries(DAY_MAP)) {
      if (new RegExp(`\\b${k}\\b`).test(q)) return v
    }
    return null
  })()

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
      <div style={{ display: 'flex', gap: 10, maxWidth: '90%' }}>
        <BotAvatar />
        <div style={{ flex: 1 }}>
          <div style={{
            background: bubbleBg,
            borderRadius: '4px 18px 18px 18px',
            border: bubbleBorder,
            padding: '12px 16px',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}>

            {/* Error state */}
            {msg.error ? (
              <div style={{ color: '#dc2626', fontSize: 13, lineHeight: 1.5, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                <span>⚠️</span>
                <span dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.error) }} />
              </div>
            ) : (
              <>
                {/* Clarification badge */}
                {isClarify && (
                  <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: '#3b82f6', letterSpacing: '0.05em', marginBottom: 6 }}>
                    💬 Needs clarification
                  </div>
                )}

                {/* Followup context badge — shown when response starts with "Sure! / Got it —" */}
                {followupPrefix && (
                  <FollowupBadge text={followupPrefix.replace(/:$/, '')} />
                )}

                {/* Main summary text */}
                <div
                  style={{ fontSize: 14, color: '#111827', lineHeight: 1.65, wordBreak: 'break-word' }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(summaryBody || msg.text || '') }}
                />

                {/* Data display */}
                {msg.display_type === 'timetable' && msg.rows?.length > 0 ? (
                  <ResultTimetable rows={msg.rows} highlightDay={highlightDay} />
                ) : msg.rows?.length > 0 ? (
                  <ResultTable columns={msg.columns} rows={msg.rows} />
                ) : null}

                {/* SQL toggle */}
                {msg.sql && (
                  <div style={{ marginTop: 10 }}>
                    <button
                      onClick={() => setShowSql(v => !v)}
                      style={{
                        fontSize: 11, color: '#9ca3af', background: 'none',
                        border: 'none', cursor: 'pointer', padding: 0,
                        textDecoration: 'underline', textUnderlineOffset: 2,
                      }}
                    >{showSql ? 'Hide SQL' : 'Show SQL'}</button>
                    {showSql && (
                      <pre style={{
                        marginTop: 6, padding: '8px 12px',
                        background: '#1e293b', color: '#94a3b8',
                        borderRadius: 8, fontSize: 11,
                        overflowX: 'auto', whiteSpace: 'pre-wrap',
                      }}>{msg.sql}</pre>
                    )}
                  </div>
                )}

                {/* Meta row */}
                <div style={{
                  marginTop: 8, fontSize: 10, color: '#9ca3af',
                  display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center',
                }}>
                  {msg.model && <span style={{ background: '#f3f4f6', borderRadius: 4, padding: '1px 6px' }}>{msg.model}</span>}
                  {msg.ms != null && <span>{Math.round(msg.ms)}ms</span>}
                  <RowPill count={msg.rows?.length} />
                </div>

                {/* Feedback row */}
                {msg.role === 'ai' && msg.message_id && !msg.error && (
                  <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 11, color: '#9ca3af' }}>Was this helpful?</span>
                    <button
                      type="button"
                      disabled={msg.feedback_pending}
                      onClick={() => onFeedback?.(msg.message_id, 1)}
                      title="Thumbs up"
                      style={{
                        border: '1px solid #d1d5db',
                        background: msg.feedback_score === 1 ? '#dcfce7' : '#fff',
                        color: msg.feedback_score === 1 ? '#166534' : '#4b5563',
                        borderRadius: 8,
                        padding: '2px 8px',
                        cursor: msg.feedback_pending ? 'not-allowed' : 'pointer',
                        fontSize: 14,
                        opacity: msg.feedback_pending ? 0.65 : 1,
                      }}
                    >
                      👍
                    </button>
                    <button
                      type="button"
                      disabled={msg.feedback_pending}
                      onClick={() => onFeedback?.(msg.message_id, -1)}
                      title="Thumbs down"
                      style={{
                        border: '1px solid #d1d5db',
                        background: msg.feedback_score === -1 ? '#fee2e2' : '#fff',
                        color: msg.feedback_score === -1 ? '#991b1b' : '#4b5563',
                        borderRadius: 8,
                        padding: '2px 8px',
                        cursor: msg.feedback_pending ? 'not-allowed' : 'pointer',
                        fontSize: 14,
                        opacity: msg.feedback_pending ? 0.65 : 1,
                      }}
                    >
                      👎
                    </button>
                    {msg.feedback_pending && (
                      <span style={{ fontSize: 11, color: '#9ca3af' }}>saving…</span>
                    )}
                    {msg.feedback_error && (
                      <span style={{ fontSize: 11, color: '#dc2626' }}>{msg.feedback_error}</span>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}