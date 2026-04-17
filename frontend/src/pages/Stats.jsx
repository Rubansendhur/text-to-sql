import { useEffect, useState } from 'react'
import { API_BASE } from '../lib/api.js'
import { useAuth } from '../contexts/AuthContext.jsx'

// ── Tiny inline bar chart (no dependency) ────────────────────────────────────
function BarChart({ data, valueKey, labelKey, color = '#2d5be3', height = 140, formatVal }) {
  if (!data?.length) return <p style={{ color: '#9a9a90', fontSize: 13 }}>No data</p>
  const max = Math.max(...data.map(d => Number(d[valueKey]) || 0)) || 1
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height, paddingBottom: 24, position: 'relative' }}>
      {data.map((d, i) => {
        const val = Number(d[valueKey]) || 0
        const pct = (val / max) * 100
        return (
          <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, height: '100%', justifyContent: 'flex-end' }}>
            {/* Value label */}
            <div style={{ fontSize: 10, fontWeight: 700, color, fontFamily: 'DM Mono, monospace', whiteSpace: 'nowrap' }}>
              {formatVal ? formatVal(val) : val}
            </div>
            {/* Bar */}
            <div style={{
              width: '100%', background: color + '20', borderRadius: '4px 4px 0 0',
              height: `${pct}%`, minHeight: 4,
              display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
              position: 'relative', overflow: 'hidden'
            }}>
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0,
                height: `${Math.max(pct, 8)}%`, minHeight: 4,
                background: color, borderRadius: '4px 4px 0 0',
                transition: 'height 0.4s ease'
              }} />
            </div>
            {/* X label */}
            <div style={{
              position: 'absolute', bottom: 0, fontSize: 9, color: '#9a9a90',
              fontWeight: 600, textAlign: 'center', whiteSpace: 'nowrap',
              overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 40
            }}>
              {d[labelKey]}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Horizontal progress bar ───────────────────────────────────────────────────
function HBar({ label, value, max, color, suffix = '' }) {
  const pct = Math.min((value / (max || 1)) * 100, 100)
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
        <span style={{ color: '#5a5a54', fontWeight: 500 }}>{label}</span>
        <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 700, color }}>{value}{suffix}</span>
      </div>
      <div style={{ height: 7, background: '#f0efe9', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.5s' }} />
      </div>
    </div>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MetricCard({ label, value, icon, color, bg, sub }) {
  return (
    <div style={{ background: bg, borderRadius: 16, padding: '20px 22px', border: '1px solid rgba(0,0,0,0.04)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color, opacity: 0.8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
        <span style={{ fontSize: 20 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 36, fontWeight: 900, color, fontFamily: 'DM Mono, monospace', letterSpacing: -1, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color, opacity: 0.6, marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children, style = {} }) {
  return (
    <div style={{ background: '#fff', borderRadius: 16, border: '1px solid #e2e0d8', padding: '20px 24px', ...style }}>
      {title && <h3 style={{ margin: '0 0 18px', fontSize: 13, fontWeight: 700, color: '#1a1a18', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{title}</h3>}
      {children}
    </div>
  )
}

export default function Stats() {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deptSort, setDeptSort] = useState('dept')  // 'dept' | 'gpa' | 'arrears' | 'students'

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    fetch(`${API_BASE}/api/admin/stats`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => { if (!r.ok) throw new Error('err'); return r.json() })
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError('Failed to load stats'); setLoading(false) })
  }, [])

  if (loading) return (
    <div style={{ padding: '40px 32px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 24 }}>
        {[1,2,3,4,5].map(i => <div key={i} style={{ height: 100, borderRadius: 16, background: '#f0efe9' }} />)}
      </div>
      <div style={{ height: 300, borderRadius: 16, background: '#f0efe9' }} />
    </div>
  )

  if (error) return (
    <div style={{ padding: 40 }}>
      <div style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626', padding: '16px 20px', borderRadius: 12 }}>{error}</div>
    </div>
  )

  const { departments = [], semester_gpa = [], batch_trends = [], top_arrear_subjects = [] } = data

  // Sort departments
  const sortedDepts = [...departments].sort((a, b) => {
    if (deptSort === 'gpa') return (b.avg_gpa || 0) - (a.avg_gpa || 0)
    if (deptSort === 'arrears') return (b.arrear_rate_pct || 0) - (a.arrear_rate_pct || 0)
    if (deptSort === 'students') return (b.students || 0) - (a.students || 0)
    return a.dept.localeCompare(b.dept)
  })

  const maxGpa = Math.max(...departments.map(d => Number(d.avg_gpa) || 0)) || 10
  const maxStudents = Math.max(...departments.map(d => Number(d.students) || 0)) || 1
  const maxArrearRate = Math.max(...departments.map(d => Number(d.arrear_rate_pct) || 0)) || 100

  // Get unique batches for batch trend chart (last 4)
  const batches = [...new Set(batch_trends.map(b => b.batch))].sort((a, b) => b - a).slice(0, 4)
  const batchChartData = batches.map(batch => {
    const rows = batch_trends.filter(b => b.batch === batch)
    const avgCgpa = rows.length ? (rows.reduce((s, r) => s + Number(r.avg_cgpa), 0) / rows.length).toFixed(2) : 0
    return { batch: String(batch), avg_cgpa: avgCgpa }
  }).reverse()

  // Arrear subject chart data
  const arrearChartData = top_arrear_subjects.slice(0, 8).map(s => ({
    subject: s.subject_code,
    count: s.active_arrear_count
  }))

  return (
    <div className="page-container" style={{ maxWidth: 1200 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, letterSpacing: -0.5, marginBottom: 4 }}>Admin Analytics</h1>
        <p style={{ fontSize: 13, color: '#5a5a54' }}>
          Institution-wide performance · {data.total_departments} departments
        </p>
      </div>

      {/* ── Global metrics ─────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 24 }}>
        <MetricCard label="Total Students" value={data.total_students ?? '—'} icon="👨‍🎓" color="#2d5be3" bg="#eef2fc" />
        <MetricCard label="Total Faculty"  value={data.total_faculty ?? '—'}  icon="👨‍🏫" color="#7c3aed" bg="#f5f3ff" />
        <MetricCard label="Departments"    value={data.total_departments ?? '—'} icon="🏛️" color="#0891b2" bg="#ecfeff" />
        <MetricCard label="Avg CGPA"       value={data.avg_gpa ?? '—'}        icon="📊" color="#16a34a" bg="#f0fdf4"
          sub="institution-wide" />
        <MetricCard label="Active Arrears" value={data.total_arrears ?? '—'}  icon="⚠️" color="#dc2626" bg="#fef2f2"
          sub="unique students" />
      </div>

      {/* ── Insight highlights ─────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { icon: '🏆', label: 'Highest Avg GPA', value: data.top_gpa_dept, color: '#16a34a', bg: '#f0fdf4' },
          { icon: '⚠️', label: 'Most Arrears', value: data.max_arrears_dept, color: '#dc2626', bg: '#fef2f2' },
          { icon: '👨‍🏫', label: 'Most Faculty', value: data.highest_faculty_load, color: '#7c3aed', bg: '#f5f3ff' },
          { icon: '🏫', label: 'Largest Dept', value: data.largest_dept, color: '#2d5be3', bg: '#eef2fc' },
        ].map(m => (
          <div key={m.label} style={{ background: m.bg, borderRadius: 14, padding: '14px 18px', border: `1px solid ${m.color}20` }}>
            <div style={{ fontSize: 18, marginBottom: 6 }}>{m.icon}</div>
            <div style={{ fontSize: 11, color: m.color, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{m.label}</div>
            <div style={{ fontSize: 20, fontWeight: 800, color: m.color, fontFamily: 'DM Mono, monospace' }}>{m.value ?? '—'}</div>
          </div>
        ))}
      </div>

      {/* ── Charts row ─────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>

        {/* GPA by department */}
        <Section title="Avg GPA by Department">
          <BarChart
            data={departments.map(d => ({ dept: d.dept, avg_gpa: d.avg_gpa || 0 }))}
            valueKey="avg_gpa" labelKey="dept" color="#2d5be3" height={160}
            formatVal={v => Number(v).toFixed(1)}
          />
        </Section>

        {/* Arrear rate % by dept */}
        <Section title="Arrear Rate % by Department">
          <BarChart
            data={departments.map(d => ({ dept: d.dept, rate: d.arrear_rate_pct || 0 }))}
            valueKey="rate" labelKey="dept" color="#dc2626" height={160}
            formatVal={v => `${Number(v).toFixed(0)}%`}
          />
        </Section>

        {/* Batch-wise avg CGPA trend */}
        <Section title="Batch-wise Avg CGPA (Recent Batches)">
          {batchChartData.length === 0
            ? <p style={{ color: '#9a9a90', fontSize: 13 }}>No batch data available.</p>
            : <BarChart data={batchChartData} valueKey="avg_cgpa" labelKey="batch" color="#7c3aed" height={160} formatVal={v => Number(v).toFixed(2)} />
          }
        </Section>

        {/* Top arrear subjects */}
        <Section title="Top Subjects with Most Arrears">
          {arrearChartData.length === 0
            ? <p style={{ color: '#9a9a90', fontSize: 13 }}>No arrear subject data.</p>
            : <BarChart data={arrearChartData} valueKey="count" labelKey="subject" color="#b45309" height={160} />
          }
        </Section>
      </div>

      {/* ── Department comparison table ─────────────────────────────── */}
      <Section title="Department-wise Performance" style={{ marginBottom: 20 }}>
        {/* Sort controls */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: '#9a9a90', alignSelf: 'center' }}>Sort by:</span>
          {[
            { key: 'dept', label: 'Code' },
            { key: 'students', label: 'Students ↓' },
            { key: 'gpa', label: 'GPA ↓' },
            { key: 'arrears', label: 'Arrear Rate ↓' },
          ].map(s => (
            <button key={s.key} onClick={() => setDeptSort(s.key)} style={{
              padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: deptSort === s.key ? 700 : 400,
              border: `1px solid ${deptSort === s.key ? '#2d5be3' : '#e2e0d8'}`,
              background: deptSort === s.key ? '#eef2fc' : '#fff',
              color: deptSort === s.key ? '#2d5be3' : '#5a5a54',
              cursor: 'pointer', fontFamily: 'DM Sans, sans-serif'
            }}>{s.label}</button>
          ))}
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f8f7f4', borderBottom: '2px solid #e2e0d8' }}>
                {['Dept', 'Name', 'Students', 'Hostellers', 'Faculty', 'Ratio S:F', 'Avg GPA', 'Max GPA', 'Arrear Rate', 'Arrear Count'].map(h => (
                  <th key={h} style={{ padding: '11px 14px', textAlign: 'left', fontSize: 10, fontWeight: 700, color: '#9a9a90', textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedDepts.map((d, i) => {
                const gpaColor = d.avg_gpa >= 8 ? '#16a34a' : d.avg_gpa >= 6 ? '#2d5be3' : d.avg_gpa >= 5 ? '#b45309' : '#dc2626'
                const arrearColor = d.arrear_rate_pct >= 30 ? '#dc2626' : d.arrear_rate_pct >= 15 ? '#b45309' : '#16a34a'
                return (
                  <tr key={d.dept} style={{ borderBottom: '1px solid #f0efe9' }}
                    onMouseEnter={e => e.currentTarget.style.background = '#fafaf8'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}
                  >
                    {/* Dept code */}
                    <td style={{ padding: '13px 14px', fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 12, color: '#2d5be3' }}>{d.dept}</td>
                    {/* Name */}
                    <td style={{ padding: '13px 14px', color: '#1a1a18', fontWeight: 500, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.department_name}</td>
                    {/* Students */}
                    <td style={{ padding: '13px 14px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span style={{ fontWeight: 700, fontFamily: 'DM Mono, monospace' }}>{d.students ?? 0}</span>
                        <div style={{ width: 60, height: 4, background: '#f0efe9', borderRadius: 2 }}>
                          <div style={{ width: `${((d.students || 0) / maxStudents) * 100}%`, height: '100%', background: '#2d5be3', borderRadius: 2 }} />
                        </div>
                      </div>
                    </td>
                    {/* Hostellers */}
                    <td style={{ padding: '13px 14px', color: '#5a5a54' }}>
                      <div style={{ fontSize: 12 }}>{d.hostellers ?? 0}</div>
                      <div style={{ fontSize: 10, color: '#9a9a90' }}>{d.day_scholars ?? 0} day</div>
                    </td>
                    {/* Faculty */}
                    <td style={{ padding: '13px 14px', fontFamily: 'DM Mono, monospace', fontWeight: 700, color: '#7c3aed' }}>{d.faculty ?? 0}</td>
                    {/* S:F ratio */}
                    <td style={{ padding: '13px 14px', fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#5a5a54' }}>
                      {d.students_per_faculty ? `${d.students_per_faculty}:1` : '—'}
                    </td>
                    {/* Avg GPA */}
                    <td style={{ padding: '13px 14px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 800, color: gpaColor }}>
                          {d.avg_gpa ? Number(d.avg_gpa).toFixed(2) : '—'}
                        </span>
                        <div style={{ width: 60, height: 4, background: '#f0efe9', borderRadius: 2 }}>
                          <div style={{ width: `${((d.avg_gpa || 0) / maxGpa) * 100}%`, height: '100%', background: gpaColor, borderRadius: 2 }} />
                        </div>
                      </div>
                    </td>
                    {/* Max GPA */}
                    <td style={{ padding: '13px 14px', fontFamily: 'DM Mono, monospace', fontSize: 12, color: '#16a34a' }}>
                      {d.max_gpa ? Number(d.max_gpa).toFixed(2) : '—'}
                    </td>
                    {/* Arrear rate */}
                    <td style={{ padding: '13px 14px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 800, color: arrearColor }}>
                          {d.arrear_rate_pct ?? 0}%
                        </span>
                        <div style={{ width: 60, height: 4, background: '#f0efe9', borderRadius: 2 }}>
                          <div style={{ width: `${Math.min((d.arrear_rate_pct || 0) / maxArrearRate * 100, 100)}%`, height: '100%', background: arrearColor, borderRadius: 2 }} />
                        </div>
                      </div>
                    </td>
                    {/* Arrear count */}
                    <td style={{ padding: '13px 14px' }}>
                      <span style={{
                        fontFamily: 'DM Mono, monospace', fontWeight: 700, fontSize: 12,
                        background: d.students_with_arrears > 0 ? '#fef2f2' : '#f0fdf4',
                        color: d.students_with_arrears > 0 ? '#dc2626' : '#16a34a',
                        padding: '2px 8px', borderRadius: 5
                      }}>{d.students_with_arrears ?? 0}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ── Top arrear subjects table ───────────────────────────────── */}
      <Section title="Top 10 Subjects with Most Active Arrears">
        {top_arrear_subjects.length === 0 ? (
          <p style={{ color: '#9a9a90', fontSize: 13 }}>No arrear subject data available.</p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
            {top_arrear_subjects.map((s, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                background: '#fff8ed', border: '1px solid #fde68a',
                borderRadius: 10, padding: '11px 14px'
              }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: '#fffbeb', border: '1px solid #fde68a',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 13, color: '#b45309', flexShrink: 0
                }}>{i + 1}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 12, color: '#b45309' }}>{s.subject_code}</span>
                    <span style={{
                      fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 13, color: '#dc2626',
                      background: '#fef2f2', border: '1px solid #fecaca', padding: '1px 7px', borderRadius: 5
                    }}>{s.active_arrear_count}</span>
                  </div>
                  <div style={{ fontSize: 11, color: '#1a1a18', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.subject_name}</div>
                  <div style={{ fontSize: 10, color: '#9a9a90', marginTop: 1 }}>Sem {s.semester_number} · {s.department_code}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  )
}