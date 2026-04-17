export function ResultTimetable({ rows, highlightDay }) {
  if (!rows || rows.length === 0) return null;

  // Build day list from data — only show days that have data OR standard Mon–Fri
  const dataDays = [...new Set(rows.map(r => r.day_of_week).filter(Boolean))];
  const allDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
  if (dataDays.includes('Sat')) allDays.push('Sat');

  const maxHour = Math.max(...rows.map(r => parseInt(r.hour_number) || 0), 0);
  if (maxHour === 0) return null;
  const hours = Array.from({ length: maxHour }, (_, i) => i + 1);

  const timetable = {};
  allDays.forEach(d => { timetable[d] = {}; hours.forEach(h => { timetable[d][h] = []; }); });
  rows.forEach(r => {
    const day = r.day_of_week; const hr = parseInt(r.hour_number);
    if (!timetable[day]) timetable[day] = {};
    if (!timetable[day][hr]) timetable[day][hr] = [];
    timetable[day][hr].push(r);
  });

  // Determine which day to highlight: prop > first day with data
  const activeDay = highlightDay || (dataDays.length === 1 ? dataDays[0] : null);

  return (
    <div style={{ overflowX: 'auto', marginTop: 12, borderRadius: 12, border: '1px solid #e5e7eb', background: '#fff' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, textAlign: 'center' }}>
        <thead>
          <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e5e7eb' }}>
            <th style={{ padding: '10px', width: 56, borderRight: '1px solid #e5e7eb', color: '#64748b', fontWeight: 700 }}>Day</th>
            {hours.map(h => (
              <th key={h} style={{ padding: '10px', color: '#64748b', fontWeight: 600, borderRight: h !== maxHour ? '1px solid #e5e7eb' : 'none', minWidth: 90 }}>
                Hour {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {allDays.map((day, idx) => {
            const isHighlighted = day === activeDay;
            const hasData = hours.some(h => (timetable[day][h] || []).length > 0);
            return (
              <tr key={day} style={{
                borderBottom: idx !== allDays.length - 1 ? '1px solid #f1f5f9' : 'none',
                background: isHighlighted ? '#fefce8' : 'transparent',
                opacity: !hasData && !isHighlighted ? 0.5 : 1,
              }}>
                <td style={{
                  padding: '8px', fontWeight: 700,
                  color: isHighlighted ? '#a16207' : '#334155',
                  borderRight: '1px solid #e5e7eb',
                  background: isHighlighted ? '#fef9c3' : '#f8fafc',
                  fontSize: isHighlighted ? 13 : 12,
                }}>
                  {day}
                  {isHighlighted && <div style={{ fontSize: 8, color: '#ca8a04', fontWeight: 400 }}>◀</div>}
                </td>
                {hours.map(h => {
                  const cells = timetable[day][h] || [];
                  return (
                    <td key={h} style={{ padding: '5px', borderRight: h !== maxHour ? '1px solid #f1f5f9' : 'none', verticalAlign: 'top' }}>
                      {cells.length === 0 ? (
                        <span style={{ color: '#e2e8f0', fontSize: 11 }}>—</span>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                          {cells.map((cell, cidx) => {
                            const subj = cell.subject_name || cell.subject || cell.subject_code || cell.activity || '—';
                            const type = cell.subject_type || 'Theory';
                            const batch = cell.sem_batch;
                            let bg = '#eff6ff', border = '#bfdbfe', color = '#1d4ed8';
                            if (type.includes('Practical')) { bg = '#f0fdf4'; border = '#bbf7d0'; color = '#15803d'; }
                            else if (type.includes('Elective')) { bg = '#fffbeb'; border = '#fde68a'; color = '#b45309'; }
                            return (
                              <div key={cidx} style={{
                                background: bg, border: `1px solid ${border}`,
                                borderRadius: 6, padding: '4px 6px', fontSize: 10, textAlign: 'left',
                              }}>
                                <div style={{ fontWeight: 700, color, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 110 }} title={subj}>
                                  {subj}
                                </div>
                                {(cell.start_time || batch) && (
                                  <div style={{ fontSize: 9, color: '#64748b', marginTop: 1 }}>
                                    {cell.start_time && cell.end_time
                                      ? `${cell.start_time}–${cell.end_time}`
                                      : batch ? `Sem ${batch}` : ''}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}