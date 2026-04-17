import { useState, useEffect, useCallback } from 'react'
import { API_BASE, authHeaders } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

const DAYS        = ['Mon','Tue','Wed','Thu','Fri']
const HOURS       = [1,2,3,4,5,6,7]
const TIME_LABELS = { 1:'09:00–09:55',2:'09:55–10:50',3:'11:05–12:00',4:'12:00–12:55',5:'14:00–14:55',6:'14:55–15:50',7:'15:50–16:45' }
const DAY_FULL    = { Mon:'Monday',Tue:'Tuesday',Wed:'Wednesday',Thu:'Thursday',Fri:'Friday' }
const SEM_LABEL   = { 1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII',9:'IX',10:'X' }
const SEMESTERS   = [1,2,3,4,5,6,7,8,9,10]
const ACTIVITIES  = ['Library','Physical Education','TWM/CCM','Placement/CGC','Association','Mentor Hour']

function slotBg(slot) {
  if (!slot || slot.type === 'free') return '#fafaf8'
  if (slot.type === 'activity')      return '#fefce8'
  if (slot.subjectType === 'Practical' || slot.subjectType === 'Elective Practical') return '#f0fdf4'
  return '#eff6ff'
}

function shortName(name) {
  const p = name.split('.')
  return p.length <= 2 ? name : p[0] + '.' + p[p.length - 1]
}

function SlotCell({ slot, isDragging }) {
  const op = isDragging ? 0.4 : 1
  if (!slot || slot.type === 'free') {
    return <div style={{ minHeight: 64, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: op }}><span style={{ fontSize: 11, color: '#ccc9bd', fontFamily: 'DM Mono, monospace' }}>+</span></div>
  }
  if (slot.type === 'activity') {
    return (
      <div style={{ minHeight: 64, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, padding: '6px 4px', textAlign: 'center', opacity: op }}>
        <div style={{ fontSize: 11, fontWeight: 500, color: '#b45309', fontFamily: 'DM Mono, monospace' }}>{slot.activity}</div>
        {slot.facultyName && <div style={{ fontSize: 10, color: '#9a9a90', fontFamily: 'DM Mono, monospace' }}>{shortName(slot.facultyName)}</div>}
      </div>
    )
  }
  return (
    <div style={{ minHeight: 64, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, padding: '6px 4px', textAlign: 'center', opacity: op }}>
      <div style={{ fontSize: 11, fontWeight: 500, color: '#2d5be3', fontFamily: 'DM Mono, monospace' }}>{slot.subjectCode}</div>
      <div style={{ fontSize: 10, color: '#5a5a54', lineHeight: 1.3, maxWidth: 108, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{slot.subjectName}</div>
      {slot.facultyName && <div style={{ fontSize: 10, color: '#9a9a90', fontFamily: 'DM Mono, monospace' }}>{shortName(slot.facultyName)}</div>}
    </div>
  )
}

function Stat({ label, value }) {
  return <div><div style={{ fontSize: 16, fontWeight: 600, fontFamily: 'DM Mono, monospace' }}>{value}</div><div style={{ fontSize: 10, color: '#9a9a90' }}>{label}</div></div>
}

function Legend({ color, label, border }) {
  return <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}><div style={{ width: 12, height: 12, borderRadius: 3, background: color, border: border ? '1px solid #ddd' : 'none', flexShrink: 0 }} /><span style={{ fontSize: 11, color: '#5a5a54' }}>{label}</span></div>
}

const thStyle   = { background: '#f8f7f4', padding: '10px 8px', textAlign: 'center', fontSize: 11, fontWeight: 500, fontFamily: 'DM Mono, monospace', color: '#5a5a54', borderBottom: '1px solid #e2e0d8', borderRight: '1px solid #e2e0d8' }
const selectSt  = { width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid #ccc9bd', fontSize: 13, fontFamily: 'DM Sans, sans-serif', background: '#fff', color: '#1a1a18' }
const btnSt     = { padding: '8px 18px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }

export default function Timetable() {
  const { user } = useAuth()
  const isAdmin  = user?.role === 'admin'

  // ── Core state ─────────────────────────────────────────────────────────────
  const [departments,  setDepartments]  = useState([])
  const [deptId,       setDeptId]       = useState(null)   // selected department_id
  const [section,      setSection]      = useState('A')
  const [availSections,setAvailSections]= useState(['A'])
  const [newSecInput,  setNewSecInput]  = useState('')
  const [faculties,    setFaculties]    = useState([])
  const [subjects,     setSubjects]     = useState([])
  const [sem,          setSem]          = useState(null)
  const [tt,           setTt]           = useState({})
  const [editMode,     setEditMode]     = useState(false)
  const [dirty,        setDirty]        = useState(false)
  const [saving,       setSaving]       = useState(false)
  const [toast,        setToast]        = useState(null)
  const [modal,        setModal]        = useState(null)
  const [mType,        setMType]        = useState('subject')
  const [mFacDeptFilter,setMFacDeptFilter]= useState('')  // '' = All
  const [mFacId,       setMFacId]       = useState('')
  const [mSubId,       setMSubId]       = useState('')
  const [mActivity,    setMActivity]    = useState('')
  const [mActFacId,    setMActFacId]    = useState('')
  const [showEl,       setShowEl]       = useState(false)
  const [elCode,       setElCode]       = useState('')
  const [elName,       setElName]       = useState('')
  const [elSaving,     setElSaving]     = useState(false)
  const [dragKey,      setDragKey]      = useState(null)
  const [dropTarget,   setDropTarget]   = useState(null)

  const showToast = useCallback((msg, type = 'ok') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }, [])

  // ── On mount: resolve own department, load faculties + subjects ─────────────
  useEffect(() => {
    // Always resolve dept from the logged-in user's department_code
    fetch(`${API_BASE}/api/departments/all`, { headers: authHeaders(user) })
      .then(r => r.json())
      .then(d => {
        const depts = d.departments || []
        setDepartments(depts)
        // Auto-select the user's own department (all roles)
        if (user?.department_code) {
          const own = depts.find(d => d.department_code === user.department_code)
          if (own) setDeptId(own.department_id)
        }
      })
      .catch(() => {})

    // Load ALL faculty across all departments for cross-dept assignment
    fetch(`${API_BASE}/api/faculty/all`, { headers: authHeaders(user) })
      .then(r => r.json())
      .then(d => {
        if (d.faculty?.length)
          setFaculties(d.faculty.map(f => ({
            id: f.faculty_id,
            name: `${f.title || ''} ${f.full_name}`.trim(),
            deptCode: f.department_code,
            deptId: f.department_id,
          })))
      }).catch(() => {})

    loadSubjects()
  }, [user])

  function loadSubjects() {
    fetch(`${API_BASE}/api/subjects/all`, { headers: authHeaders(user) })
      .then(r => r.json())
      .then(d => {
        if (d.subjects?.length)
          setSubjects(d.subjects.map(s => ({ id: s.subject_id, code: s.subject_code, name: s.subject_name, sem: s.semester_number, type: s.subject_type || 'Theory', deptId: s.department_id })))
      }).catch(() => {})
  }

  // ── Load sections for selected dept + sem ─────────────────────────────────
  async function loadSections(resolvedDeptId, resolvedSem) {
    if (!resolvedDeptId || !resolvedSem) return
    try {
      const d = await fetch(
        `${API_BASE}/api/timetable/sections?department_id=${resolvedDeptId}&sem_batch=${resolvedSem}`,
        { headers: authHeaders(user) }
      ).then(r => r.json())
      const secs = d.sections || ['A']
      setAvailSections(secs)
      // Keep current section if still valid, else reset to first
      setSection(prev => secs.includes(prev) ? prev : secs[0])
    } catch { setAvailSections(['A']) }
  }

  // ── Load timetable grid ────────────────────────────────────────────────────
  async function loadSem(s, overrideDeptId, overrideSection) {
    const useDeptId  = overrideDeptId  ?? deptId
    const useSection = overrideSection ?? section
    if (!useDeptId) { showToast('Select a department first', 'info'); return }
    setSem(s); setEditMode(false); setDirty(false); setTt({})
    await loadSections(useDeptId, s)
    try {
      const url = `${API_BASE}/api/timetable/sem/${s}?department_id=${useDeptId}&section=${useSection}`
      const d   = await fetch(url, { headers: authHeaders(user) }).then(r => r.json())
      const loaded = {}
      for (const row of (d.slots || [])) {
        loaded[`${row.day_of_week}_${row.hour_number}`] = {
          type: row.activity ? 'activity' : 'subject',
          facultyId: row.faculty_id, facultyName: row.faculty_name,
          subjectId: row.subject_id, subjectCode: row.subject_code,
          subjectName: row.subject_name, subjectType: row.subject_type,
          activity: row.activity, semBatch: row.sem_batch,
        }
      }
      setTt(loaded)
    } catch { /* empty */ }
  }

  // Re-load when section changes (if sem already selected)
  async function changeSection(newSection) {
    setSection(newSection)
    if (sem && deptId) await loadSem(sem, deptId, newSection)
  }

  // ── Slot modal ─────────────────────────────────────────────────────────────
  function openSlot(day, hour) {
    if (!sem) return
    const key  = `${day}_${hour}`
    const slot = tt[key]
    if (slot && slot.type !== 'free' && !editMode) { showToast('Turn on Edit Mode to change a filled slot', 'info'); return }
    setModal({ day, hour })
    if (slot?.type === 'activity') { setMType('activity'); setMActivity(slot.activity || ''); setMActFacId(String(slot.facultyId || '')); setMFacId(''); setMSubId('') }
    else if (slot?.type === 'subject') { setMType('subject'); setMFacId(String(slot.facultyId || '')); setMSubId(String(slot.subjectId || '')); setMActivity(''); setMActFacId('') }
    else { setMType('subject'); setMFacId(''); setMSubId(''); setMActivity(''); setMActFacId('') }
  }

  function applySlot() {
    if (!modal || !sem) return
    const key  = `${modal.day}_${modal.hour}`
    const next = { ...tt }
    if (mType === 'free') { delete next[key] }
    else if (mType === 'activity') {
      if (!mActivity) { showToast('Select an activity', 'err'); return }
      const fac = faculties.find(f => f.id === Number(mActFacId))
      next[key] = { type: 'activity', activity: mActivity, facultyId: fac?.id, facultyName: fac?.name, semBatch: sem }
    } else {
      if (!mFacId)  { showToast('Select a faculty member', 'err'); return }
      if (!mSubId)  { showToast('Select a subject', 'err'); return }
      const fac = faculties.find(f => f.id === Number(mFacId))
      const sub = subjects.find(s => s.id === Number(mSubId))
      next[key] = { type: 'subject', semBatch: sem, facultyId: fac?.id, facultyName: fac?.name, subjectId: sub?.id, subjectCode: sub?.code, subjectName: sub?.name, subjectType: sub?.type }
    }
    setTt(next); setDirty(true); setModal(null)
  }

  function clearSlot() {
    if (!modal) return
    const next = { ...tt }; delete next[`${modal.day}_${modal.hour}`]
    setTt(next); setDirty(true); setModal(null)
  }

  // ── Drag & drop ────────────────────────────────────────────────────────────
  function handleDragStart(e, key) {
    setDragKey(key); e.dataTransfer.effectAllowed = 'copyMove'
    const el = e.currentTarget
    setTimeout(() => { if (el) el.style.opacity = '0.4' }, 0)
  }
  function handleDragEnd(e) { if (e.currentTarget) e.currentTarget.style.opacity = ''; setDragKey(null); setDropTarget(null) }
  function handleDragOver(e, key) { e.preventDefault(); e.dataTransfer.dropEffect = e.ctrlKey ? 'copy' : 'move'; setDropTarget(key) }
  function handleDrop(e, targetKey) {
    e.preventDefault()
    if (!dragKey || dragKey === targetKey) { setDragKey(null); setDropTarget(null); return }
    const next = { ...tt }; const src = next[dragKey]; const tgt = next[targetKey]
    if (e.ctrlKey) { if (src) next[targetKey] = { ...src }; showToast('Slot copied', 'info') }
    else { if (tgt) next[dragKey] = tgt; else delete next[dragKey]; if (src) next[targetKey] = src; showToast('Slot moved', 'info') }
    setTt(next); setDirty(true); setDragKey(null); setDropTarget(null)
  }

  // ── Elective creation ──────────────────────────────────────────────────────
  async function createElective() {
    if (!sem || !elCode.trim() || !elName.trim()) { showToast('Provide both code and name', 'err'); return }
    setElSaving(true)
    try {
      const r = await fetch(`${API_BASE}/api/subjects`, {
        method: 'POST',
        headers: authHeaders(user, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({ subject_code: elCode.trim(), subject_name: elName.trim(), semester_number: sem, subject_type: 'Elective' })
      })
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed') }
      showToast('Elective created!', 'ok'); setShowEl(false); setElCode(''); setElName(''); loadSubjects()
    } catch (e) { showToast(e.message, 'err') }
    setElSaving(false)
  }

  // ── Save ───────────────────────────────────────────────────────────────────
  async function save() {
    if (!sem || !deptId) return; setSaving(true)
    const slots = Object.entries(tt).map(([key, slot]) => {
      const [day, h] = key.split('_')
      return { day_of_week: day, hour_number: Number(h), faculty_id: slot?.facultyId ?? null, subject_id: slot?.subjectId ?? null, activity: slot?.activity ?? null, sem_batch: sem }
    })
    try {
      const r = await fetch(`${API_BASE}/api/timetable/save`, {
        method: 'POST',
        headers: authHeaders(user, { 'Content-Type': 'application/json' }),
        body: JSON.stringify({ sem_batch: sem, department_id: deptId, section, slots })
      })
      if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Save failed') }
      setDirty(false); showToast(`Semester ${SEM_LABEL[sem]} · Section ${section} saved (${slots.length} slots)`, 'ok')
      // Refresh available sections in case a new one was created
      await loadSections(deptId, sem)
    } catch (e) { showToast(e.message, 'err') }
    setSaving(false)
  }

  async function clearAll() {
    if (!sem) return
    const count = Object.keys(tt).length
    if (!confirm(`Clear all ${count} slots for Semester ${SEM_LABEL[sem]} · Section ${section}?`)) return
    setTt({}); setDirty(true); showToast(`Semester ${SEM_LABEL[sem]} / Section ${section} cleared`, 'info')
  }

  // ── Computed ───────────────────────────────────────────────────────────────
  const filteredSubjects  = sem ? subjects.filter(s => s.sem === sem || s.type === 'Elective' || s.type === 'Elective Practical') : subjects
  const theorySubjects    = filteredSubjects.filter(s => s.type === 'Theory')
  const practicalSubjects = filteredSubjects.filter(s => s.type === 'Practical' || s.type === 'Elective Practical')
  const electiveSubjects  = filteredSubjects.filter(s => s.type === 'Elective')
  const otherSubjects     = filteredSubjects.filter(s => !['Theory','Practical','Elective','Elective Practical'].includes(s.type))
  const filledCount = Object.values(tt).filter(s => s?.type !== 'free').length
  const facSet      = new Set(Object.values(tt).map(s => s?.facultyId).filter(Boolean))
  const selectedDept = departments.find(d => d.department_id === deptId)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>

      {/* Top bar */}
      <div style={{ background: '#fff', borderBottom: '1px solid #e2e0d8', padding: '0 28px', height: 54, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Timetable Entry</span>
          {selectedDept && <span style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', padding: '2px 10px', borderRadius: 20, background: '#f0fdf4', color: '#16a34a' }}>{selectedDept.department_code}</span>}
          {sem && <span style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', padding: '2px 10px', borderRadius: 20, background: '#eef2fc', color: '#2d5be3' }}>Sem {SEM_LABEL[sem]}</span>}
          {sem && <span style={{ fontSize: 11, fontFamily: 'DM Mono, monospace', padding: '2px 10px', borderRadius: 20, background: '#fdf4ff', color: '#7c3aed' }}>Sec {section}</span>}
          {dirty && <span style={{ fontSize: 11, color: '#b45309', fontFamily: 'DM Mono, monospace' }}>● unsaved</span>}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {sem && isAdmin && <button onClick={() => setEditMode(v => !v)} style={{ padding: '6px 14px', borderRadius: 8, border: `1.5px solid ${editMode ? '#fcd34d' : '#e2e0d8'}`, background: editMode ? '#fef3c7' : '#fff', color: editMode ? '#b45309' : '#5a5a54', fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>✏ Edit Mode: {editMode ? 'ON' : 'OFF'}</button>}
          {sem && isAdmin && <button onClick={clearAll} style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid #e2e0d8', background: '#fff', color: '#5a5a54', fontSize: 12, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>Clear</button>}
          {isAdmin && <button onClick={save} disabled={!sem || !deptId || saving} style={{ padding: '6px 18px', borderRadius: 8, border: 'none', background: (!sem || !deptId || saving) ? '#9ab0f5' : '#2d5be3', color: '#fff', fontSize: 12, fontWeight: 500, cursor: (!sem || !deptId || saving) ? 'not-allowed' : 'pointer', fontFamily: 'DM Sans, sans-serif' }}>
            {saving ? 'Saving…' : 'Save'}
          </button>}
        </div>
      </div>

      {editMode && <div style={{ background: '#fffbeb', borderBottom: '1px solid #fde68a', padding: '7px 28px', fontSize: 12, color: '#b45309', fontWeight: 500, flexShrink: 0 }}>✏️ Edit mode is ON — click any slot to change it</div>}

      {sem && isAdmin && <div style={{ background: '#f0f9ff', borderBottom: '1px solid #bae6fd', padding: '6px 28px', fontSize: 11, color: '#0369a1', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 16 }}>
        <span>🖱️ <strong>Drag</strong> a filled slot to <strong>move</strong> it</span>
        <span style={{ color: '#cbd5e1' }}>·</span>
        <span><kbd style={{ background: '#e0f2fe', color: '#0369a1', padding: '1px 5px', borderRadius: 4, fontSize: 10, fontWeight: 700 }}>Ctrl</kbd> + drag to <strong>copy</strong></span>
        <span style={{ color: '#cbd5e1' }}>·</span>
        <span>Click any slot to edit</span>
      </div>}

      {/* Selectors + stats */}
      <div style={{ padding: '12px 28px', borderBottom: '1px solid #e2e0d8', background: '#fafaf8', flexShrink: 0, display: 'flex', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap' }}>

        {/* Semester selector */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <label style={{ fontSize: 10, fontFamily: 'DM Mono, monospace', color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Semester Batch</label>
          <select
            value={sem ?? ''}
            onChange={e => e.target.value && loadSem(Number(e.target.value))}
            disabled={!deptId}
            style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid #ccc9bd', background: !deptId ? '#f0f0f0' : '#fff', fontSize: 13, cursor: deptId ? 'pointer' : 'not-allowed', fontFamily: 'DM Sans, sans-serif' }}
          >
            <option value="">— Select —</option>
            <optgroup label="Semesters I–VIII">{SEMESTERS.filter(s => s <= 8).map(s => <option key={s} value={s}>Semester {SEM_LABEL[s]}</option>)}</optgroup>
            <optgroup label="Optional (IX–X)">{[9,10].map(s => <option key={s} value={s}>Semester {SEM_LABEL[s]}</option>)}</optgroup>
          </select>
        </div>

        {/* Section selector */}
        {sem && deptId && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <label style={{ fontSize: 10, fontFamily: 'DM Mono, monospace', color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Section</label>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {availSections.map(sec => (
                <button
                  key={sec}
                  onClick={() => changeSection(sec)}
                  style={{ padding: '6px 14px', borderRadius: 8, border: `1.5px solid ${section === sec ? '#7c3aed' : '#e2e0d8'}`, background: section === sec ? '#fdf4ff' : '#fff', color: section === sec ? '#7c3aed' : '#5a5a54', fontSize: 13, fontWeight: section === sec ? 600 : 400, cursor: 'pointer', fontFamily: 'DM Mono, monospace' }}
                >{sec}</button>
              ))}
              {/* Add new section (admin only) */}
              {isAdmin && (
                <div style={{ display: 'flex', gap: 4 }}>
                  <input
                    value={newSecInput}
                    onChange={e => setNewSecInput(e.target.value.toUpperCase().slice(0,3))}
                    placeholder="+ Sec"
                    style={{ width: 54, padding: '6px 8px', borderRadius: 8, border: '1px dashed #ccc9bd', fontSize: 12, fontFamily: 'DM Mono, monospace', textAlign: 'center' }}
                  />
                  {newSecInput && !availSections.includes(newSecInput) && (
                    <button
                      onClick={() => {
                        const s = newSecInput.trim()
                        if (!s) return
                        setAvailSections(prev => [...prev, s])
                        setSection(s)
                        setTt({})
                        setNewSecInput('')
                      }}
                      style={{ padding: '6px 10px', borderRadius: 8, border: 'none', background: '#7c3aed', color: '#fff', fontSize: 12, cursor: 'pointer' }}
                    >Add</button>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Stats */}
        {sem && <>
          <Stat label="Slots filled"     value={`${filledCount} / 35`} />
          <Stat label="Faculty assigned" value={String(facSet.size)} />
          <div style={{ display: 'flex', gap: 14, marginLeft: 'auto' }}>
            <Legend color="#dbeafe" label="Theory" />
            <Legend color="#dcfce7" label="Practical" />
            <Legend color="#fef9c3" label="Activity" />
            <Legend color="#f5f5f1" label="Free" border />
          </div>
        </>}
      </div>

      {/* Grid */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px 28px 32px' }}>
        {!deptId ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12, color: '#9a9a90' }}>
            <div style={{ fontSize: 40 }}>🏫</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>Select a department to begin</div>
            <div style={{ fontSize: 12 }}>Then choose semester and section</div>
          </div>
        ) : !sem ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12, color: '#9a9a90' }}>
            <div style={{ fontSize: 40 }}>📅</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>Select a semester to begin</div>
            <div style={{ fontSize: 12 }}>Choose from the dropdown above</div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%', minWidth: 820, background: '#fff', border: '1px solid #e2e0d8', borderRadius: 14, overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,0,0,0.05)' }}>
              <thead>
                <tr>
                  <th style={{ ...thStyle, width: 70, textAlign: 'left', paddingLeft: 16, color: '#9a9a90' }}>Day</th>
                  {HOURS.map(h => <th key={h} style={{ ...thStyle, minWidth: 115 }}><span style={{ display: 'block', fontSize: 14, fontWeight: 600, color: '#1a1a18', fontFamily: 'DM Mono, monospace' }}>{h}</span><span style={{ display: 'block', fontSize: 10, color: '#9a9a90', marginTop: 1 }}>{TIME_LABELS[h]}</span></th>)}
                </tr>
              </thead>
              <tbody>
                {DAYS.map((day, di) => (
                  <tr key={day}>
                    <td style={{ background: '#f8f7f4', borderRight: '1px solid #e2e0d8', borderBottom: di < DAYS.length - 1 ? '1px solid #e2e0d8' : 'none', paddingLeft: 16, fontSize: 12, fontWeight: 600, color: '#5a5a54', fontFamily: 'DM Mono, monospace', letterSpacing: '0.03em', verticalAlign: 'middle' }}>{day}</td>
                    {HOURS.map((h, hi) => {
                      const key    = `${day}_${h}`
                      const slot   = tt[key]
                      const filled = slot && slot.type !== 'free'
                      return (
                        <td key={h}
                          draggable={!!filled && isAdmin}
                          onDragStart={(filled && isAdmin) ? e => handleDragStart(e, key) : undefined}
                          onDragEnd={(filled && isAdmin) ? handleDragEnd : undefined}
                          onDragOver={isAdmin ? e => handleDragOver(e, key) : undefined}
                          onDragLeave={isAdmin ? () => setDropTarget(null) : undefined}
                          onDrop={isAdmin ? e => handleDrop(e, key) : undefined}
                          onClick={() => { if (isAdmin) openSlot(day, h) }}
                          className={(!filled || editMode) ? 'slot-editable' : ''}
                          style={{ border: 'none', borderRight: hi < HOURS.length - 1 ? '1px solid #e2e0d8' : 'none', borderBottom: di < DAYS.length - 1 ? '1px solid #e2e0d8' : 'none', background: dropTarget === key ? '#dbeafe' : slotBg(slot), cursor: (filled && isAdmin) ? 'grab' : (isAdmin ? 'pointer' : 'default'), verticalAlign: 'top', padding: 4, transition: 'background 0.15s', outline: dropTarget === key ? '2px dashed #2d5be3' : 'none', outlineOffset: '-2px' }}>
                          <SlotCell slot={slot} isDragging={dragKey === key} />
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Slot Modal */}
      {modal && (
        <div onClick={e => { if (e.target === e.currentTarget) setModal(null) }} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(2px)' }}>
          <div style={{ background: '#fff', borderRadius: 18, padding: 28, width: 420, maxWidth: '95vw', boxShadow: '0 20px 60px rgba(0,0,0,0.18)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600 }}>{DAY_FULL[modal.day]}, Hour {modal.hour}</div>
                <div style={{ fontSize: 11, color: '#9a9a90', fontFamily: 'DM Mono, monospace', marginTop: 2 }}>{TIME_LABELS[modal.hour]}</div>
              </div>
              <button onClick={() => setModal(null)} style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: '#9a9a90' }}>✕</button>
            </div>

            {/* Type toggle */}
            <div style={{ display: 'flex', gap: 6, marginBottom: 18 }}>
              {['subject','activity','free'].map(t => (
                <button key={t} onClick={() => setMType(t)} style={{ flex: 1, padding: '8px 4px', borderRadius: 10, border: `1.5px solid ${mType === t ? '#2d5be3' : '#e2e0d8'}`, background: mType === t ? '#eef2fc' : '#fff', color: mType === t ? '#2d5be3' : '#5a5a54', fontSize: 12, fontWeight: 500, cursor: 'pointer', fontFamily: 'DM Sans, sans-serif' }}>
                  {t === 'subject' ? '📚 Subject' : t === 'activity' ? '🎯 Activity' : '◻ Free'}
                </button>
              ))}
            </div>

            {mType === 'subject' && (
              <>
                <MLabel>Faculty Department</MLabel>
                <select
                  value={mFacDeptFilter}
                  onChange={e => { setMFacDeptFilter(e.target.value); setMFacId('') }}
                  style={{ ...selectSt, marginBottom: 10 }}
                >
                  <option value="">All Departments</option>
                  {departments.map(d => (
                    <option key={d.department_id} value={d.department_code}>
                      {d.department_code} — {d.department_name}
                    </option>
                  ))}
                </select>
                <MLabel>Faculty</MLabel>
                <select value={mFacId} onChange={e => setMFacId(e.target.value)} style={{ ...selectSt, marginBottom: 14 }}>
                  <option value="">— Select Faculty —</option>
                  {(mFacDeptFilter
                    ? faculties.filter(f => f.deptCode === mFacDeptFilter)
                    : faculties
                  ).map(f => <option key={f.id} value={f.id}>[{f.deptCode}] {f.name}</option>)}
                </select>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                  <MLabel>Subject</MLabel>
                  <button onClick={() => setShowEl(v => !v)} style={{ background: 'none', border: 'none', color: '#2d5be3', fontSize: 11, cursor: 'pointer', fontWeight: 600 }}>
                    {showEl ? 'Cancel' : '+ Add New Elective'}
                  </button>
                </div>

                {showEl ? (
                  <div style={{ background: '#f8f7f4', padding: 12, borderRadius: 8, border: '1px solid #e2e0d8', marginBottom: 14 }}>
                    <input type="text" placeholder="Code (e.g. 22ELX01)" value={elCode} onChange={e => setElCode(e.target.value.toUpperCase())} style={{ ...selectSt, marginBottom: 8 }} />
                    <input type="text" placeholder="Subject Name" value={elName} onChange={e => setElName(e.target.value)} style={{ ...selectSt, marginBottom: 8 }} />
                    <button onClick={createElective} disabled={elSaving || !elCode || !elName} style={{ ...btnSt, background: '#2d5be3', color: '#fff', border: 'none', width: '100%', padding: '7px 12px', fontSize: 12 }}>
                      {elSaving ? 'Saving…' : 'Save Elective to Database'}
                    </button>
                  </div>
                ) : (
                  <select value={mSubId} onChange={e => setMSubId(e.target.value)} style={{ ...selectSt, marginBottom: 14 }}>
                    <option value="">— Select Subject for Sem {sem} —</option>
                    {theorySubjects.length > 0    && <optgroup label="Theory">{theorySubjects.map(s => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}</optgroup>}
                    {practicalSubjects.length > 0 && <optgroup label="Practical">{practicalSubjects.map(s => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}</optgroup>}
                    {electiveSubjects.length > 0  && <optgroup label="Electives">{electiveSubjects.map(s => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}</optgroup>}
                    {otherSubjects.length > 0     && <optgroup label="Other">{otherSubjects.map(s => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}</optgroup>}
                  </select>
                )}
              </>
            )}

            {mType === 'activity' && (
              <>
                <MLabel>Activity</MLabel>
                <select value={mActivity} onChange={e => setMActivity(e.target.value)} style={{ ...selectSt, marginBottom: 14 }}>
                  <option value="">— Select Activity —</option>
                  {ACTIVITIES.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
                <MLabel>Faculty (optional)</MLabel>
                <select value={mActFacId} onChange={e => setMActFacId(e.target.value)} style={{ ...selectSt, marginBottom: 14 }}>
                  <option value="">— None / Multiple —</option>
                  {faculties.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </>
            )}

            {mType === 'free' && <p style={{ fontSize: 13, color: '#5a5a54', marginBottom: 8 }}>This slot will be marked as free.</p>}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 22, paddingTop: 16, borderTop: '1px solid #e2e0d8' }}>
              <button onClick={clearSlot} style={{ ...btnSt, background: '#fef2f2', color: '#dc2626', border: '1px solid #fca5a5' }}>Clear Slot</button>
              <button onClick={() => setModal(null)} style={{ ...btnSt, background: '#fff', color: '#5a5a54', border: '1px solid #e2e0d8' }}>Cancel</button>
              <button onClick={applySlot} style={{ ...btnSt, background: '#2d5be3', color: '#fff', border: 'none' }}>Apply</button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', bottom: 24, right: 24, padding: '11px 20px', borderRadius: 10, fontSize: 13, fontWeight: 500, zIndex: 9999, background: toast.type === 'ok' ? '#eaf6ef' : toast.type === 'err' ? '#fef2f2' : '#eef2fc', color: toast.type === 'ok' ? '#16a34a' : toast.type === 'err' ? '#dc2626' : '#2d5be3', border: `1px solid ${toast.type === 'ok' ? '#86efac' : toast.type === 'err' ? '#fca5a5' : '#c5d3f8'}`, boxShadow: '0 4px 16px rgba(0,0,0,0.1)' }}>
          {toast.msg}
        </div>
      )}
    </div>
  )
}

function MLabel({ children }) {
  return <div style={{ fontSize: 10, fontFamily: 'DM Mono, monospace', color: '#5a5a54', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 5 }}>{children}</div>
}
