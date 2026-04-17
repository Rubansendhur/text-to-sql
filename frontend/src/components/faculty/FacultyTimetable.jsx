import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../../lib/api.js'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
const HOURS = [1, 2, 3, 4, 5, 6, 7]
const ACTIVITIES = ['Library', 'Physical Education', 'TWM/CCM', 'Placement/CGC', 'Association', 'Mentor Hour']
const SEM_LABEL = { 1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII' }

function slotBg(slot) {
  if (!slot || slot.type === 'free') return '#fff'
  if (slot.type === 'activity') return '#f0fdf4'
  return '#eff6ff'
}

function SlotCell({ slot, isDragging }) {
  const op = isDragging ? 0.4 : 1
  if (!slot || slot.type === 'free') {
    return (
      <div style={{ minHeight: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: op }}>
        <span style={{ fontSize: 11, color: '#ccc', fontFamily: 'DM Mono, monospace' }}>+</span>
      </div>
    )
  }
  if (slot.type === 'activity') {
    return (
      <div style={{ minHeight: 64, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, padding: 4, opacity: op }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#16a34a', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{slot.activity}</span>
      </div>
    )
  }
  return (
    <div style={{ minHeight: 64, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', justifyContent: 'flex-start', gap: 2, padding: '6px 8px', opacity: op }}>
      <span style={{ fontSize: 12, fontWeight: 800, color: '#1d4ed8', fontFamily: 'DM Mono, monospace' }}>{slot.subjectCode}</span>
      <span style={{ fontSize: 10, color: '#6b7280', lineHeight: 1.3 }}>{slot.subjectName}</span>
      {slot.semBatch && (
        <span style={{ fontSize: 9, fontWeight: 600, background: '#e0e7ff', color: '#4338ca', padding: '1px 5px', borderRadius: 4 }}>
          Sem {SEM_LABEL[slot.semBatch] ?? slot.semBatch}
        </span>
      )}
    </div>
  )
}

export function FacultyTimetable({ faculty, isAdmin = false }) {
  const [tt, setTt] = useState({})
  const [subjects, setSubjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [toast, setToast] = useState(null)
  const [modal, setModal] = useState(null)
  const [mType, setMType] = useState('subject')
  const [mSem, setMSem] = useState('')
  const [mSubId, setMSubId] = useState('')
  const [mAct, setMAct] = useState('')
  const [dragKey, setDragKey] = useState(null)
  const [dropTgt, setDropTgt] = useState(null)
  const toastTimer = useRef(null)

  function showToast(msg, type = 'info') {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, type })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }

  useEffect(() => {
    const token = localStorage.getItem('access_token')

    setLoading(true)
    setTt({})
    setDirty(false)

    Promise.all([
      fetch(`${API_BASE}/api/faculty/${faculty.faculty_id}/timetable`, {
        headers: { Authorization: `Bearer ${token}` }
      }).then(r => r.json()),

      fetch(`${API_BASE}/api/subjects/all`, {
        headers: { Authorization: `Bearer ${token}` }
      }).then(r => r.json()),
    ])
      .then(([ttData, subData]) => {
        const built = {}

          ; (ttData.timetable || []).forEach(row => {
            const key = `${row.day_of_week}_${row.hour_number}`

            if (row.subject_code) {
              built[key] = {
                type: 'subject',
                subjectId: row.subject_id,
                subjectCode: row.subject_code,
                subjectName: row.subject_name,
                subjectType: row.subject_type,
                semBatch: row.sem_batch
              }
            } else if (row.activity) {
              built[key] = {
                type: 'activity',
                activity: row.activity,
                semBatch: row.sem_batch
              }
            }
          })

        setTt(built)
        setSubjects(subData.subjects || [])
      })
      .catch(e => showToast(e.message, 'err'))
      .finally(() => setLoading(false))

  }, [faculty.faculty_id])

  function openModal(day, hour) {
    if (!isAdmin) return
    const slot = tt[`${day}_${hour}`]
    setMType(slot?.type === 'activity' ? 'activity' : 'subject')
    setMSem(slot?.semBatch ? String(slot.semBatch) : '')
    setMSubId(slot?.subjectId ? String(slot.subjectId) : '')
    setMAct(slot?.activity || '')
    setModal({ day, hour })
  }

  function commitModal() {
    if (!modal) return
    const key = `${modal.day}_${modal.hour}`
    const next = { ...tt }
    if (mType === 'activity' && mAct) {
      next[key] = { type: 'activity', activity: mAct }
    } else if (mType === 'subject' && mSubId) {
      const sub = subjects.find(s => String(s.subject_id) === mSubId)
      if (sub) next[key] = { type: 'subject', subjectId: sub.subject_id, subjectCode: sub.subject_code, subjectName: sub.subject_name, subjectType: sub.subject_type, semBatch: sub.semester_number }
    }
    setTt(next); setDirty(true); setModal(null)
  }

  function clearModal() {
    if (!modal) return
    const next = { ...tt }
    delete next[`${modal.day}_${modal.hour}`]
    setTt(next); setDirty(true); setModal(null)
  }

  // Drag handlers
  function handleDragStart(e, key) {
    setDragKey(key)
    e.dataTransfer.effectAllowed = 'copyMove'
    const el = e.currentTarget
    setTimeout(() => { if (el) el.style.opacity = '0.4' }, 0)
  }
  function handleDragEnd(e) {
    if (e.currentTarget) e.currentTarget.style.opacity = ''
    setDragKey(null); setDropTgt(null)
  }
  function handleDragOver(e, key) {
    e.preventDefault()
    e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move'
    setDropTgt(key)
  }
  function handleDrop(e, targetKey) {
    e.preventDefault()
    if (!dragKey || dragKey === targetKey) { setDragKey(null); setDropTgt(null); return }
    const isCopy = e.ctrlKey
    const next = { ...tt }
    const src = next[dragKey]; const tgt = next[targetKey]
    if (isCopy) { if (src) next[targetKey] = { ...src }; showToast('Copied', 'info') }
    else {
      if (tgt) next[dragKey] = tgt; else delete next[dragKey]
      if (src) next[targetKey] = src; showToast('Moved', 'info')
    }
    setTt(next); setDirty(true); setDragKey(null); setDropTgt(null)
  }

  async function save() {
    setSaving(true)
    const token = localStorage.getItem('access_token')
    const slots = Object.entries(tt).map(([key, slot]) => {
      const [day, h] = key.split('_')
      return { day_of_week: day, hour_number: Number(h), subject_code: slot?.type === 'subject' ? slot.subjectCode ?? null : null, activity: slot?.type === 'activity' ? slot.activity ?? null : null, sem_batch: slot?.semBatch ?? null }
    })
    try {
      const r = await fetch(`${API_BASE}/api/faculty/${faculty.faculty_id}/timetable`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(slots) })
      if (!r.ok) throw new Error()
      setDirty(false); showToast('Saved!', 'ok')
    } catch { showToast('Save failed', 'err') }
    setSaving(false)
  }

  const modalSubs = mSem ? subjects.filter(s => String(s.semester_number) === mSem) : subjects

  if (loading) return (
    <div style={{ height: 400, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8' }}>
      <span style={{ color: '#9a9a90', fontSize: 13 }}>Loading timetable…</span>
    </div>
  )

  return (
    <div style={{ background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', overflow: 'hidden', position: 'relative' }}>
      {/* Toast */}
      {toast && (
        <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 200, background: toast.type === 'ok' ? '#dcfce7' : toast.type === 'err' ? '#fee2e2' : '#e0f2fe', color: toast.type === 'ok' ? '#166534' : toast.type === 'err' ? '#991b1b' : '#0369a1', padding: '8px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ padding: '18px 24px', borderBottom: '1px solid #e2e0d8', background: '#fafaf8', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{faculty.title} {faculty.full_name}</h2>
          <p style={{ fontSize: 12, color: '#9a9a90', margin: '3px 0 0' }}>{faculty.designation}{faculty.email && ` · ${faculty.email}`}</p>
        </div>
        {isAdmin && dirty && (
          <button onClick={save} disabled={saving} style={{ padding: '7px 18px', background: '#2d5be3', color: '#fff', border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>
            {saving ? 'Saving…' : '💾 Save'}
          </button>
        )}
      </div>

      {isAdmin && (
        <div style={{ padding: '8px 24px', background: '#f0f9ff', borderBottom: '1px solid #bae6fd', fontSize: 11, color: '#0369a1' }}>
          Click cell to assign · Drag to move · <kbd style={{ background: '#e0f2fe', padding: '1px 4px', borderRadius: 3 }}>Ctrl</kbd>+drag to copy
        </div>
      )}

      {/* Grid */}
      <div style={{ overflowX: 'auto', padding: 16 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 700 }}>
          <thead>
            <tr>
              <th style={thStyle}>Day</th>
              {HOURS.map(h => <th key={h} style={thStyle}>Period {h}</th>)}
            </tr>
          </thead>
          <tbody>
            {DAYS.map(day => (
              <tr key={day}>
                <td style={{ ...thStyle, fontWeight: 700, color: '#374151', textAlign: 'center', width: 60 }}>{day}</td>
                {HOURS.map(h => {
                  const key = `${day}_${h}`
                  const slot = tt[key]
                  const filled = slot && slot.type !== 'free'
                  return (
                    <td key={h}
                      draggable={isAdmin && !!filled}
                      onDragStart={isAdmin && filled ? e => handleDragStart(e, key) : undefined}
                      onDragEnd={isAdmin && filled ? handleDragEnd : undefined}
                      onDragOver={isAdmin ? e => handleDragOver(e, key) : undefined}
                      onDragLeave={isAdmin ? () => setDropTgt(null) : undefined}
                      onDrop={isAdmin ? e => handleDrop(e, key) : undefined}
                      onClick={() => openModal(day, h)}
                      style={{ border: dropTgt === key ? '2px dashed #2d5be3' : '1px solid #e2e0d8', background: dropTgt === key ? '#dbeafe' : slotBg(slot), cursor: isAdmin ? (filled ? 'grab' : 'pointer') : 'default', verticalAlign: 'top', padding: 4, transition: 'background 0.12s' }}
                    >
                      <SlotCell slot={slot} isDragging={dragKey === key} />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {modal && isAdmin && (
        <div onClick={e => { if (e.target === e.currentTarget) setModal(null) }}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
        >
          <div style={{ background: '#fff', borderRadius: 16, padding: 28, minWidth: 360, maxWidth: 440, width: '100%', boxShadow: '0 16px 48px rgba(0,0,0,0.18)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>Assign — {modal.day}, Period {modal.hour}</h3>
              <button onClick={() => setModal(null)} style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: '#9a9a90' }}>✕</button>
            </div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              {['subject', 'activity'].map(t => (
                <button key={t} onClick={() => setMType(t)} style={{ flex: 1, padding: '8px 0', borderRadius: 8, border: `1.5px solid ${mType === t ? '#2d5be3' : '#e2e0d8'}`, background: mType === t ? '#eef2fc' : '#fff', color: mType === t ? '#2d5be3' : '#5a5a54', fontWeight: 600, fontSize: 13, cursor: 'pointer', textTransform: 'capitalize', fontFamily: 'DM Sans, sans-serif' }}>
                  {t}
                </button>
              ))}
            </div>
            {mType === 'subject' ? (
              <>
                <ModalLabel>Semester</ModalLabel>
                <select value={mSem} onChange={e => { setMSem(e.target.value); setMSubId('') }} style={mSel}>
                  <option value="">All Semesters</option>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map(s => <option key={s} value={s}>Semester {SEM_LABEL[s]}</option>)}
                </select>
                <ModalLabel>Subject</ModalLabel>
                <select value={mSubId} onChange={e => setMSubId(e.target.value)} style={mSel}>
                  <option value="">— Select Subject —</option>
                  {['Theory', 'Practical', 'Elective', 'Elective Practical'].map(type => {
                    const group = modalSubs.filter(s => s.subject_type === type)
                    return group.length ? (
                      <optgroup key={type} label={type}>
                        {group.map(s => <option key={s.subject_id} value={s.subject_id}>{s.subject_code} – {s.subject_name}</option>)}
                      </optgroup>
                    ) : null
                  })}
                </select>
              </>
            ) : (
              <>
                <ModalLabel>Activity</ModalLabel>
                <select value={mAct} onChange={e => setMAct(e.target.value)} style={mSel}>
                  <option value="">— Select Activity —</option>
                  {ACTIVITIES.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 20 }}>
              <button onClick={commitModal} style={{ flex: 1, padding: '9px 0', background: '#2d5be3', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>Assign</button>
              <button onClick={clearModal} style={{ padding: '9px 14px', background: '#fff', color: '#dc2626', border: '1px solid #fca5a5', borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>Clear</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ModalLabel({ children }) {
  return <div style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', color: '#5a5a54', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 5 }}>{children}</div>
}

const thStyle = { padding: '8px 14px', background: '#f8f7f4', fontSize: 11, color: '#6b7280', border: '1px solid #e2e0d8', fontWeight: 600, textAlign: 'center' }
const mSel = { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #e2e0d8', fontSize: 13, marginBottom: 14, outline: 'none', fontFamily: 'DM Sans, sans-serif' }

