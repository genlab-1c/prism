/* Fixed PRISM-1 snapshot: cumulative counts by model release month.
   Both lines use the overall score across the full bank. */
import React from 'react';
import edition from '../../data/prism1.json';
import '../../styles/chronicle.css';

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const FULL_MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
const LINES = [
  { key: 'high', label: '9 баллов и выше', short: '9+', className: 'chr-cyan' },
  { key: 'veryHigh', label: '9,5 балла и выше', short: '9,5+', className: 'chr-purple' },
];
const toTime = (s) => Date.parse(/^\d{4}-\d{2}$/.test(s) ? `${s}-15T00:00:00Z` : s);

export function Chronicle({ models = [] }) {
  const [selected, setSelected] = React.useState(null);
  const [width, setWidth] = React.useState(720);
  const plot = React.useRef(null);
  React.useEffect(() => {
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(Math.max(220, Math.round(entry.contentRect.width)));
    });
    observer.observe(plot.current);
    return () => observer.disconnect();
  }, []);

  const rows = React.useMemo(() => {
    const end = Date.parse(`${edition.fixedAt}T23:59:59Z`);
    const year = new Date(end).getUTCFullYear();
    const dated = models.filter(m => m.released && Number.isFinite(m.qOverall))
      .map(m => ({ time: toTime(m.released), score: m.qOverall }));
    return Array.from({ length: new Date(end).getUTCMonth() + 1 }, (_, month) => {
      const cutoff = Math.min(end, Date.UTC(year, month + 1, 1) - 1);
      const upto = dated.filter(m => m.time <= cutoff);
      return { month, year, total: upto.length,
        high: upto.filter(m => m.score >= 9).length,
        veryHigh: upto.filter(m => m.score >= 9.5).length };
    });
  }, [models]);
  const last = rows[rows.length - 1];
  const current = rows[selected ?? rows.length - 1];
  const compact = width < 500;
  const left = compact ? 22 : 26, right = width - (compact ? 26 : 58), top = 16, bottom = 196, height = 226;
  const max = Math.max(5, Math.ceil(last.high / 5) * 5);
  const x = (i) => left + i / Math.max(1, rows.length - 1) * (right - left);
  const y = (n) => bottom - n / max * (bottom - top);
  const path = (key) => rows.map((row, i) => `${i ? 'L' : 'M'}${x(i)},${y(row[key])}`).join(' ');
  const year = last.year;

  return (
    <section className="chr-card" aria-labelledby="chr-title">
      <div className="chr-top">
        <h3 id="chr-title">Всё больше моделей у верхней границы шкалы</h3>
        <span className="chr-period">{year} · все {edition.tasks} задач</span>
      </div>
      <p className="chr-description">Сколько моделей из PRISM-1 набрали высокую общую оценку к каждому месяцу их выхода.</p>
      <div className="chr-legend">
        {LINES.map(line => <span key={line.key} className={line.className}><i />{line.label}</span>)}
      </div>
      <div className="chr-plot" ref={plot}>
        <svg viewBox={`0 0 ${width} ${height}`} role="group" aria-label={`Модели с общей оценкой 9 и 9,5 балла и выше по месяцам ${year} года`}>
          <title>{`К октябрю: ${last.high} моделей с оценкой 9+, из них ${last.veryHigh} с оценкой 9,5+`}</title>
          {Array.from({ length: max / 5 + 1 }, (_, i) => i * 5).map(value => <g key={value}>
            <line className="chr-grid" x1={left} x2={right} y1={y(value)} y2={y(value)} />
            <text className="chr-tick" x={left - 9} y={y(value) + 4} textAnchor="end">{value}</text>
          </g>)}
          <path className="chr-area" d={`${path('high')} L${right},${bottom} L${left},${bottom} Z`} />
          <line className="chr-guide" x1={x(selected ?? rows.length - 1)} x2={x(selected ?? rows.length - 1)} y1={top} y2={bottom} />
          {LINES.map(line => <g key={line.key} className={line.className}>
            <path className="chr-line" d={path(line.key)} />
            {rows.map((row, i) => <circle key={i} className="chr-point" cx={x(i)} cy={y(row[line.key])} r={i === (selected ?? rows.length - 1) ? 5 : 3.5} />)}
            <text className="chr-end" x={right + (compact ? 7 : 9)} y={y(last[line.key]) + 4}>{last[line.key]}{!compact && <tspan className="chr-end-label"> {line.short}</tspan>}</text>
          </g>)}
          {rows.map((row, i) => <g key={row.month}>
            {(width >= 500 || i % 2 === 0 || i === rows.length - 1) &&
              <text className={`chr-tick${i === (selected ?? rows.length - 1) ? ' chr-tick--active' : ''}`} x={x(i)} y={bottom + 22} textAnchor="middle">{MONTHS[row.month]}</text>}
            <rect className="chr-hit" x={i === 0 ? left - 10 : (x(i - 1) + x(i)) / 2} y={top}
              width={(right - left) / Math.max(1, rows.length - 1) * (i === 0 || i === rows.length - 1 ? .5 : 1) + (i === 0 ? 10 : 0)} height={bottom - top}
              tabIndex="0" role="button" aria-pressed={selected === i}
              aria-label={`${FULL_MONTHS[row.month]}: ${row.high} моделей с оценкой 9 и выше, ${row.veryHigh} с оценкой 9,5 и выше, всего ${row.total}`}
              onMouseEnter={() => setSelected(i)} onFocus={() => setSelected(i)} onClick={() => setSelected(i)}
              onKeyDown={e => {
                if (['Enter', ' ', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                  e.preventDefault();
                  const next = Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowLeft' ? -1 : e.key === 'ArrowRight' ? 1 : 0)));
                  setSelected(next);
                  if (next !== i) plot.current.querySelectorAll('.chr-hit')[next].focus();
                }
              }} />
          </g>)}
        </svg>
      </div>
      <div className="chr-selection" aria-live="polite">
        <strong>{FULL_MONTHS[current.month]}</strong>
        <span className="chr-cyan"><b>{current.high}</b> с оценкой 9+</span>
        <span className="chr-purple"><b>{current.veryHigh}</b> с оценкой 9,5+</span>
        <span>из {current.total} моделей</span>
      </div>
      <p className="chr-note">
        Даты выхода моделей, не даты прогонов. Накопительный счёт только среди протестированных моделей;
        линии показывают рост числа высоких оценок, а не изменение оценки одной модели.
        {' '}Срез на {edition.fixedAt.split('-').reverse().join('.')}.
      </p>
    </section>
  );
}
