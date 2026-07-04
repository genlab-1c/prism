/* PRISM web — интерактивные графики лидерборда (SVG, рисуются на клиенте).
   Радар SMOP и ранжир по Q̄ с наведением и переходом на модель. Кнопка «скачать»
   экспортирует ТЕКУЩИЙ вид в SVG или PNG (сериализация того же <svg>, растр через canvas).

   Важно для экспорта: внутри <svg> только конкретные цвета (hex) и системный шрифт —
   CSS-переменные при сериализации не разрешаются, поэтому здесь не используем var(). */
import React from 'react';

const C = {
  bg: '#ffffff', ink: '#1a2230', sub: '#5a6577', grid: '#e2e6ee', muted: '#8a94a6',
};
const AXIS = { S: '#7c7ef8', M: '#22d3ee', O: '#34d399', P: '#fbbf24' };
const PALETTE = ['#22d3ee', '#34d399', '#fbbf24', '#f472b6', '#7c7ef8', '#fb923c', '#4ade80', '#e879f9'];
const CAT_AXES = { A: ['S', 'M', 'O'], B: ['S', 'M', 'O', 'P'] };
const FONT = 'ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif';
const qColor = (q) => (q == null ? '#c2c9d6' : q >= 7 ? '#34d399' : q >= 4 ? '#fbbf24' : '#f87171');

// ── экспорт текущего svg ─────────────────────────────────────────────────────
function _dl(href, name) {
  const a = document.createElement('a');
  a.href = href; a.download = name; document.body.appendChild(a); a.click(); a.remove();
}
function exportSvg(svg, name) {
  const s = new XMLSerializer().serializeToString(svg);
  const blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n' + s], { type: 'image/svg+xml' });
  const url = URL.createObjectURL(blob); _dl(url, `${name}.svg`); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportPng(svg, name, scale = 2) {
  const vb = svg.viewBox.baseVal;
  const w = (vb && vb.width) || svg.clientWidth || 900;
  const h = (vb && vb.height) || svg.clientHeight || 500;
  const s = new XMLSerializer().serializeToString(svg);
  const url = URL.createObjectURL(new Blob([s], { type: 'image/svg+xml;charset=utf-8' }));
  const img = new Image();
  img.onload = () => {
    const cv = document.createElement('canvas'); cv.width = w * scale; cv.height = h * scale;
    const ctx = cv.getContext('2d'); ctx.fillStyle = C.bg; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, 0, 0, cv.width, cv.height);
    cv.toBlob((b) => { const u = URL.createObjectURL(b); _dl(u, `${name}.png`); setTimeout(() => URL.revokeObjectURL(u), 1000); });
    URL.revokeObjectURL(url);
  };
  img.src = url;
}

const STAMP = (meta) => `PRISM · genlab-1c/prism${meta?.version ? ` · v${meta.version}` : ''} · L1${meta?.lastRun ? ` · ${meta.lastRun}` : ''}`;

/* ── ранжир по Q̄ (горизонтальные бары) ── */
function RankingSvg({ svgRef, cat, models, meta, hover, setHover, navigate }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const rows = models.filter((m) => m[qKey] != null).sort((a, b) => b[qKey] - a[qKey]);
  const L = 210, R = 860, top = 44, rh = 30, W = 900, H = top + rows.length * rh + 34;
  const x = (q) => L + (q / 10) * (R - L);
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block', background: C.bg, borderRadius: 8 }} fontFamily={FONT}>
      <text x={20} y={26} fontSize="16" fontWeight="700" fill={C.ink}>Лидерборд PRISM — категория {cat} · Q̄</text>
      {[0, 2, 4, 6, 8, 10].map((t) => (
        <g key={t}>
          <line x1={x(t)} y1={top - 6} x2={x(t)} y2={H - 28} stroke={C.grid} strokeDasharray="2 4" />
          <text x={x(t)} y={H - 12} textAnchor="middle" fontSize="10" fill={C.muted}>{t}</text>
        </g>
      ))}
      {rows.map((m, i) => {
        const y = top + i * rh; const q = m[qKey]; const on = hover === m.id;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <rect x={0} y={y} width={W} height={rh} fill={on ? '#f2f5fa' : 'transparent'} />
            <text x={L - 10} y={y + rh / 2 + 4} textAnchor="end" fontSize="12" fill={C.ink} fontWeight={i === 0 ? 700 : 400}>{`${i + 1}. ${m.name}`}</text>
            <rect x={L} y={y + 6} width={Math.max(1, x(q) - L)} height={rh - 12} rx={3} fill={qColor(q)} opacity={on ? 1 : 0.9} />
            <text x={x(q) + 6} y={y + rh / 2 + 4} fontSize="11" fontWeight="600" fill={C.ink}>{q.toFixed(2)}</text>
          </g>
        );
      })}
      <text x={W - 12} y={H - 4} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

/* ── радар SMOP (топ-N) ── */
function RadarSvg({ svgRef, cat, models, meta, top = 8, hover, setHover, navigate }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const axes = CAT_AXES[cat];
  const rows = models.filter((m) => m[qKey] != null).sort((a, b) => b[qKey] - a[qKey]).slice(0, top);
  const W = 900, H = 560, cx = 300, cy = 300, R = 210;
  const ang = (i) => -Math.PI / 2 + (i / axes.length) * 2 * Math.PI;
  const pt = (i, v) => [cx + Math.cos(ang(i)) * R * (v / 10), cy + Math.sin(ang(i)) * R * (v / 10)];
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block', background: C.bg, borderRadius: 8 }} fontFamily={FONT}>
      <text x={20} y={28} fontSize="16" fontWeight="700" fill={C.ink}>Профиль SMOP — категория {cat} (топ-{rows.length})</text>
      {[2, 4, 6, 8, 10].map((r) => (
        <polygon key={r} points={axes.map((_, i) => pt(i, r).join(',')).join(' ')} fill="none" stroke={C.grid} strokeDasharray="2 3" />
      ))}
      {axes.map((a, i) => {
        const [ex, ey] = pt(i, 10.9);
        return (
          <g key={a}>
            <line x1={cx} y1={cy} x2={pt(i, 10)[0]} y2={pt(i, 10)[1]} stroke={C.grid} />
            <text x={ex} y={ey + 4} textAnchor="middle" fontSize="14" fontWeight="700" fill={AXIS[a]}>{a}</text>
          </g>
        );
      })}
      {rows.map((m, idx) => {
        const col = PALETTE[idx % PALETTE.length]; const on = hover === m.id; const dim = hover && !on;
        const pts = axes.map((a, i) => pt(i, (m[cat] && m[cat][a]) || 0).join(',')).join(' ');
        return (
          <polygon key={m.id} points={pts} fill={col} fillOpacity={on ? 0.18 : 0.06} stroke={col} strokeWidth={on ? 2.6 : 1.6} opacity={dim ? 0.25 : 1}
            style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)} />
        );
      })}
      {rows.map((m, idx) => {
        const col = PALETTE[idx % PALETTE.length]; const y = 70 + idx * 26; const on = hover === m.id;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <rect x={600} y={y - 12} width={290} height={22} fill={on ? '#f2f5fa' : 'transparent'} rx={4} />
            <circle cx={614} cy={y - 1} r={5} fill={col} />
            <text x={628} y={y + 3} fontSize="12.5" fill={C.ink} fontWeight={on ? 700 : 400}>{m.name}</text>
            <text x={885} y={y + 3} textAnchor="end" fontSize="12" fontWeight="600" fill={C.sub}>{m[qKey].toFixed(2)}</text>
          </g>
        );
      })}
      <text x={W - 12} y={H - 6} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

/* ── оси SMOP: сгруппированные бары по осям для топ-N моделей ── */
const AXIS_NAME = { S: 'синтаксис', M: 'смысл', O: 'оптимальность', P: 'платформа' };
function BarsSvg({ svgRef, cat, models, meta, top = 8, hover, setHover, navigate }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const axes = CAT_AXES[cat];
  const rows = models.filter((m) => m[qKey] != null).sort((a, b) => b[qKey] - a[qKey]).slice(0, top);
  const L = 210, Rr = 830, T = 70, rowH = 48, W = 900, H = T + rows.length * rowH + 30;
  const x = (v) => L + (v / 10) * (Rr - L);
  const bh = (rowH - 16) / axes.length;
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block', background: C.bg, borderRadius: 8 }} fontFamily={FONT}>
      <text x={20} y={28} fontSize="16" fontWeight="700" fill={C.ink}>Профиль по осям SMOP — категория {cat} (топ-{rows.length})</text>
      {/* легенда осей */}
      {axes.map((a, i) => (
        <g key={a}>
          <rect x={L + i * 90} y={44} width={12} height={12} fill={AXIS[a]} rx={2} />
          <text x={L + i * 90 + 18} y={54} fontSize="11" fill={C.sub}>{a} · {AXIS_NAME[a]}</text>
        </g>
      ))}
      {[0, 2, 4, 6, 8, 10].map((t) => (
        <g key={t}>
          <line x1={x(t)} y1={T - 6} x2={x(t)} y2={H - 28} stroke={C.grid} strokeDasharray="2 4" />
          <text x={x(t)} y={H - 12} textAnchor="middle" fontSize="10" fill={C.muted}>{t}</text>
        </g>
      ))}
      {rows.map((m, ri) => {
        const y0 = T + ri * rowH; const on = hover === m.id;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <rect x={0} y={y0} width={W} height={rowH} fill={on ? '#f2f5fa' : 'transparent'} />
            <text x={L - 10} y={y0 + rowH / 2 + 4} textAnchor="end" fontSize="12" fill={C.ink} fontWeight={ri === 0 ? 700 : 400}>{`${ri + 1}. ${m.name}`}</text>
            {axes.map((a, ai) => {
              const v = (m[cat] && m[cat][a]) || 0; const by = y0 + 8 + ai * bh;
              return (
                <g key={a}>
                  <rect x={L} y={by} width={Math.max(1, x(v) - L)} height={bh - 2} fill={AXIS[a]} opacity={on ? 1 : 0.9} />
                  <text x={x(v) + 5} y={by + bh / 2 + 2} fontSize="9" fill={C.sub}>{v.toFixed(1)}</text>
                </g>
              );
            })}
          </g>
        );
      })}
      <text x={W - 12} y={H - 4} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

function Btn({ children, onClick, primary }) {
  const [h, setH] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{ cursor: 'pointer', borderRadius: 'var(--radius-sm)', padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600,
        border: '1px solid var(--line)', background: primary ? (h ? 'var(--brand-strong)' : 'var(--brand)') : (h ? 'var(--surface-raised)' : 'var(--surface-sunken)'),
        color: primary ? 'var(--brand-ink)' : 'var(--ink-200)' }}>{children}</button>
  );
}

export function LeaderChart({ cat, models = [], meta = {}, navigate }) {
  const [kind, setKind] = React.useState('radar');
  const [hover, setHover] = React.useState(null);
  const ref = React.useRef(null);
  const name = `prism_${kind}_${cat}`;
  const tab = (k, label) => (
    <button onClick={() => setKind(k)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px 8px', marginRight: 18, borderBottom: `2px solid ${kind === k ? 'var(--brand)' : 'transparent'}`, fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: kind === k ? 600 : 500, color: kind === k ? 'var(--ink-100)' : 'var(--ink-400)' }}>{label}</button>
  );
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
        <div>{tab('radar', 'Радар SMOP')}{tab('ranking', 'Ранжир Q̄')}{tab('bars', 'Оси SMOP')}</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn onClick={() => ref.current && exportSvg(ref.current, name)}>Скачать SVG</Btn>
          <Btn primary onClick={() => ref.current && exportPng(ref.current, name)}>Скачать PNG</Btn>
        </div>
      </div>
      {kind === 'radar' && <RadarSvg svgRef={ref} cat={cat} models={models} meta={meta} hover={hover} setHover={setHover} navigate={navigate} />}
      {kind === 'ranking' && <RankingSvg svgRef={ref} cat={cat} models={models} meta={meta} hover={hover} setHover={setHover} navigate={navigate} />}
      {kind === 'bars' && <BarsSvg svgRef={ref} cat={cat} models={models} meta={meta} hover={hover} setHover={setHover} navigate={navigate} />}
      <p style={{ margin: '10px 0 0', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>наведи — подсветка, клик — открыть модель · кнопки экспортируют текущий вид</p>
    </div>
  );
}

/* ── общий график: доля решённых A ↔ B (все модели) — для Сводки ── */
function OverallScatterSvg({ svgRef, models, meta, hover, setHover, navigate }) {
  const pts = models.filter((m) => m.A && m.A.solved != null && m.B && m.B.solved != null);
  const top = new Set([...models].filter((m) => m.qOverall != null).sort((a, b) => b.qOverall - a.qOverall).slice(0, 3).map((m) => m.id));
  const W = 900, H = 560, L = 70, Rr = 858, T = 46, Bb = 496;
  const sx = (p) => L + p * (Rr - L);
  const sy = (p) => Bb - p * (Bb - T);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block', background: C.bg, borderRadius: 8 }} fontFamily={FONT}>
      <text x={20} y={28} fontSize="16" fontWeight="700" fill={C.ink}>Общий зачёт: <tspan fill={AXIS.M}>алгоритмика A</tspan> × <tspan fill={AXIS.P}>платформа 1С B</tspan> · доля решённых</text>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={sx(t)} y1={T} x2={sx(t)} y2={Bb} stroke={C.grid} strokeDasharray="2 4" />
          <line x1={L} y1={sy(t)} x2={Rr} y2={sy(t)} stroke={C.grid} strokeDasharray="2 4" />
          <text x={sx(t)} y={Bb + 18} textAnchor="middle" fontSize="10" fill={C.muted}>{t * 100}%</text>
          <text x={L - 10} y={sy(t) + 4} textAnchor="end" fontSize="10" fill={C.muted}>{t * 100}%</text>
        </g>
      ))}
      <text x={(L + Rr) / 2} y={H - 14} textAnchor="middle" fontSize="12" fill={C.sub}>решено в категории A (алгоритмика) →</text>
      <text x={18} y={(T + Bb) / 2} textAnchor="middle" fontSize="12" fill={C.sub} transform={`rotate(-90 18 ${(T + Bb) / 2})`}>решено в категории B (платформа 1С) →</text>
      {pts.map((m) => {
        const cx = sx(m.A.solved), cy = sy(m.B.solved); const on = hover === m.id; const label = top.has(m.id) || on;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <circle cx={cx} cy={cy} r={on ? 7 : 5} fill={qColor(m.qOverall)} stroke={C.bg} strokeWidth="1.5" opacity={on || !hover ? 1 : 0.5} />
            {label && <text x={cx + 9} y={cy + 4} fontSize="11" fontWeight={on ? 700 : 500} fill={C.ink}>{m.name}</text>}
          </g>
        );
      })}
      <text x={W - 12} y={H - 6} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

export function OverallChart({ models = [], meta = {}, navigate }) {
  const [hover, setHover] = React.useState(null);
  const ref = React.useRef(null);
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-300)' }}>кто силён в обоих — правый-верх; специалисты — по краям</span>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn onClick={() => ref.current && exportSvg(ref.current, 'prism_overall')}>Скачать SVG</Btn>
          <Btn primary onClick={() => ref.current && exportPng(ref.current, 'prism_overall')}>Скачать PNG</Btn>
        </div>
      </div>
      <OverallScatterSvg svgRef={ref} models={models} meta={meta} hover={hover} setHover={setHover} navigate={navigate} />
      <p style={{ margin: '10px 0 0', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-400)' }}>цвет точки — общий Q · наведи для подписи, клик — открыть модель</p>
    </div>
  );
}
