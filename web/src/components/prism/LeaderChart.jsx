/* PRISM web — интерактивные графики лидерборда (SVG, рисуются на клиенте).
   Рейтинг Q · Радар SMOP · Оси SMOP + общий scatter A↔B. Наведение/переход на модель.
   Кнопки «Скачать» экспортируют ТЕКУЩИЙ вид в SVG/PNG (сериализация того же <svg> + canvas).

   Тема полотна следует теме сайта (data-theme) и обновляется при переключении.
   Цвета в <svg> — конкретные hex (из палитры темы), не CSS-var: иначе не сериализуются в экспорт. */
import React from 'react';
import { vendorGlyph } from './VendorLogo.jsx';

const AXIS = { S: '#7c7ef8', M: '#22d3ee', O: '#34d399', P: '#fbbf24' };
const PALETTE = ['#22d3ee', '#34d399', '#fbbf24', '#f472b6', '#7c7ef8', '#fb923c', '#4ade80', '#e879f9', '#38bdf8', '#a78bfa'];
const CAT_AXES = { A: ['S', 'M', 'O'], B: ['S', 'M', 'O', 'P'] };
const AXIS_NAME = { S: 'синтаксис', M: 'смысл', O: 'оптимальность', P: 'платформа' };
const FONT = 'ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif';
const qColor = (q) => (q == null ? '#9aa3b2' : q >= 7 ? '#34d399' : q >= 4 ? '#fbbf24' : '#f87171');

// палитры полотна по теме сайта (hex — чтобы сериализовалось в экспорт)
const THEME = {
  light: { bg: '#ffffff', ink: '#1a2230', sub: '#5a6577', grid: '#e2e6ee', muted: '#8a94a6', rowHover: '#eef2f9',
    brand: '#0aa5c4', brandInk: '#ffffff', ok: '#099b6e', warn: '#c9820f', danger: '#dc4d4d', head: '#f2f5fa', zebra: '#f8fafc', tint: '#e8f6fa' },
  dark: { bg: '#0d1a2d', ink: '#eef2f8', sub: '#9aa7bd', grid: '#26374e', muted: '#5f6f88', rowHover: '#182a41',
    brand: '#22d3ee', brandInk: '#04222a', ok: '#34d399', warn: '#fbbf24', danger: '#f87171', head: '#122135', zebra: '#101e33', tint: '#12293a' },
};
const solvedHex = (C, s) => (s == null ? C.muted : s >= 0.7 ? C.ok : s >= 0.4 ? C.warn : C.danger);
function useTheme() {
  const read = () => (typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme')) || 'dark';
  const [t, setT] = React.useState(read);
  React.useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setT(read()));
    obs.observe(el, { attributes: true, attributeFilter: ['data-theme'] });
    return () => obs.disconnect();
  }, []);
  return t === 'light' ? 'light' : 'dark';
}

// ── экспорт текущего svg ─────────────────────────────────────────────────────
function _dl(href, name) {
  const a = document.createElement('a');
  a.href = href; a.download = name; document.body.appendChild(a); a.click(); a.remove();
}
function exportSvg(svg, name) {
  const s = new XMLSerializer().serializeToString(svg);
  const url = URL.createObjectURL(new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n' + s], { type: 'image/svg+xml' }));
  _dl(url, `${name}.svg`); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportPng(svg, name, bg, scale = 2) {
  const vb = svg.viewBox.baseVal;
  const w = (vb && vb.width) || 900, h = (vb && vb.height) || 500;
  const s = new XMLSerializer().serializeToString(svg);
  const url = URL.createObjectURL(new Blob([s], { type: 'image/svg+xml;charset=utf-8' }));
  const img = new Image();
  img.onload = () => {
    const cv = document.createElement('canvas'); cv.width = w * scale; cv.height = h * scale;
    const ctx = cv.getContext('2d'); ctx.fillStyle = bg; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, 0, 0, cv.width, cv.height);
    cv.toBlob((b) => { const u = URL.createObjectURL(b); _dl(u, `${name}.png`); setTimeout(() => URL.revokeObjectURL(u), 1000); });
    URL.revokeObjectURL(url);
  };
  img.src = url;
}

const STAMP = (meta) => `PRISM · genlab-1c/prism${meta?.version ? ` · v${meta.version}` : ''} · L1${meta?.lastRun ? ` · ${meta.lastRun}` : ''}`;
const svgStyle = { width: '100%', height: 'auto', display: 'block', borderRadius: 8 };

/* ── рейтинг по Q (горизонтальные бары) ── */
function RankingSvg({ svgRef, cat, shown, meta, C, hover, setHover, navigate }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const rows = shown; // уже отсортировано лучшая→худшая; лучший сверху
  const L = 210, R = 858, top = 44, rh = 30, W = 900, H = top + rows.length * rh + 50;
  const x = (q) => L + (q / 10) * (R - L);
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={20} y={26} fontSize="16" fontWeight="700" fill={C.ink}>Рейтинг PRISM — категория {cat} · Q</text>
      {[0, 2, 4, 6, 8, 10].map((t) => (
        <g key={t}>
          <line x1={x(t)} y1={top - 6} x2={x(t)} y2={H - 40} stroke={C.grid} strokeDasharray="2 4" />
          <text x={x(t)} y={H - 26} textAnchor="middle" fontSize="10" fill={C.muted}>{t}</text>
        </g>
      ))}
      {rows.map((m, i) => {
        const y = top + i * rh; const q = m[qKey]; const on = hover === m.id; const rank = i + 1;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <rect x={0} y={y} width={W} height={rh} fill={on ? C.rowHover : 'transparent'} />
            <text x={L - 10} y={y + rh / 2 + 4} textAnchor="end" fontSize="12" fill={C.ink} fontWeight={rank === 1 ? 700 : 400}>{`${rank}. ${m.name}`}</text>
            <rect x={L} y={y + 6} width={Math.max(1, x(q) - L)} height={rh - 12} rx={3} fill={qColor(q)} opacity={on ? 1 : 0.9} />
            <text x={x(q) + 6} y={y + rh / 2 + 4} fontSize="11" fontWeight="600" fill={C.ink}>{q.toFixed(2)}</text>
          </g>
        );
      })}
      <text x={W - 12} y={H - 8} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

/* ── радар SMOP ── */
function RadarSvg({ svgRef, cat, shown, meta, C, hover, setHover, navigate }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const axes = CAT_AXES[cat];
  const cx = 300, cy = 300, R = 210, W = 900, H = Math.max(560, 92 + shown.length * 24);
  const ang = (i) => -Math.PI / 2 + (i / axes.length) * 2 * Math.PI;
  const pt = (i, v) => [cx + Math.cos(ang(i)) * R * (v / 10), cy + Math.sin(ang(i)) * R * (v / 10)];
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={20} y={28} fontSize="16" fontWeight="700" fill={C.ink}>Профиль SMOP — категория {cat} ({shown.length} моделей)</text>
      {[2, 4, 6, 8, 10].map((r) => (
        <polygon key={r} points={axes.map((_, i) => pt(i, r).join(',')).join(' ')} fill="none" stroke={C.grid} strokeDasharray="2 3" />
      ))}
      {axes.map((a, i) => {
        const [ex, ey] = pt(i, 10.9);
        return (<g key={a}><line x1={cx} y1={cy} x2={pt(i, 10)[0]} y2={pt(i, 10)[1]} stroke={C.grid} /><text x={ex} y={ey + 4} textAnchor="middle" fontSize="14" fontWeight="700" fill={AXIS[a]}>{a}</text></g>);
      })}
      {shown.map((m, idx) => {
        const col = PALETTE[idx % PALETTE.length]; const on = hover === m.id; const dim = hover && !on;
        const pts = axes.map((a, i) => pt(i, (m[cat] && m[cat][a]) || 0).join(',')).join(' ');
        return <polygon key={m.id} points={pts} fill={col} fillOpacity={on ? 0.18 : 0.05} stroke={col} strokeWidth={on ? 2.6 : 1.5} opacity={dim ? 0.2 : 1}
          style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)} />;
      })}
      {shown.map((m, idx) => {
        const col = PALETTE[idx % PALETTE.length]; const y = 70 + idx * 24; const on = hover === m.id;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <rect x={600} y={y - 12} width={290} height={20} fill={on ? C.rowHover : 'transparent'} rx={4} />
            <circle cx={614} cy={y - 2} r={5} fill={col} />
            <text x={628} y={y + 2} fontSize="12" fill={C.ink} fontWeight={on ? 700 : 400}>{m.name}</text>
            <text x={885} y={y + 2} textAnchor="end" fontSize="11.5" fontWeight="600" fill={C.sub}>{m[qKey].toFixed(2)}</text>
          </g>
        );
      })}
      <text x={W - 12} y={H - 6} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

/* ── оси SMOP: сгруппированные бары ── */
function BarsSvg({ svgRef, cat, shown, meta, C, hover, setHover, navigate }) {
  const axes = CAT_AXES[cat];
  const L = 210, R = 830, T = 70, rowH = 48, W = 900, H = T + shown.length * rowH + 46;
  const x = (v) => L + (v / 10) * (R - L);
  const bh = (rowH - 16) / axes.length;
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={20} y={28} fontSize="16" fontWeight="700" fill={C.ink}>Профиль по осям SMOP — категория {cat} ({shown.length} моделей)</text>
      {(() => { let lx = L; return axes.map((a) => { const label = `${a} · ${AXIS_NAME[a]}`; const x0 = lx; lx += 30 + label.length * 6.4 + 16; return (<g key={a}><rect x={x0} y={44} width={12} height={12} fill={AXIS[a]} rx={2} /><text x={x0 + 18} y={54} fontSize="11" fill={C.sub}>{label}</text></g>); }); })()}
      {[0, 2, 4, 6, 8, 10].map((t) => (<g key={t}><line x1={x(t)} y1={T - 6} x2={x(t)} y2={H - 40} stroke={C.grid} strokeDasharray="2 4" /><text x={x(t)} y={H - 26} textAnchor="middle" fontSize="10" fill={C.muted}>{t}</text></g>))}
      {shown.map((m, ri) => {
        const y0 = T + ri * rowH; const on = hover === m.id;
        return (
          <g key={m.id} style={{ cursor: 'pointer' }} onMouseEnter={() => setHover(m.id)} onMouseLeave={() => setHover(null)} onClick={() => navigate && navigate('model', m.id)}>
            <rect x={0} y={y0} width={W} height={rowH} fill={on ? C.rowHover : 'transparent'} />
            <text x={L - 10} y={y0 + rowH / 2 + 4} textAnchor="end" fontSize="12" fill={C.ink} fontWeight={ri === 0 ? 700 : 400}>{`${ri + 1}. ${m.name}`}</text>
            {axes.map((a, ai) => {
              const v = (m[cat] && m[cat][a]) || 0; const by = y0 + 8 + ai * bh;
              return (<g key={a}><rect x={L} y={by} width={Math.max(1, x(v) - L)} height={bh - 2} fill={AXIS[a]} opacity={on ? 1 : 0.9} /><text x={x(v) + 5} y={by + bh / 2 + 2} fontSize="9" fill={C.sub}>{v.toFixed(1)}</text></g>);
            })}
          </g>
        );
      })}
      <text x={W - 12} y={H - 8} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

/* Знак вендора внутри выгружаемого <svg>: бейдж + inline-путь бренда (или монограмма
   для неизвестного вендора). Пути 24×24 из VendorLogo — масштабируем в бейдж size×size. */
function LogoGlyph({ x, cy, size, m, C }) {
  const gl = vendorGlyph(m.vendor);
  const s2 = size / 2;
  if (!gl) {
    const ch = (m.family || m.name || '?').trim()[0]?.toUpperCase() || '?';
    return (
      <g>
        <rect x={x} y={cy - s2} width={size} height={size} rx={7} fill={C.head} stroke={C.grid} />
        <text x={x + s2} y={cy + 4} textAnchor="middle" fontSize={size * 0.5} fontWeight="700" fill={C.sub}>{ch}</text>
      </g>
    );
  }
  const col = gl.color.startsWith('#') ? gl.color : C.ink; // 'var(--ink-100)' (xAI) → ink темы
  const gs = size * 0.62, off = (size - gs) / 2, k = gs / 24;
  return (
    <g>
      <rect x={x} y={cy - s2} width={size} height={size} rx={7} fill={col} fillOpacity={0.14} stroke={C.grid} />
      <g transform={`translate(${x + off}, ${cy - s2 + off}) scale(${k})`}
        fill={gl.stroke ? 'none' : col} stroke={gl.stroke ? col : undefined}
        strokeWidth={gl.stroke ? 2.3 : undefined} strokeLinecap="round" strokeLinejoin="round">
        {gl.paths.map((d, i) => <path key={i} d={d} />)}
      </g>
    </g>
  );
}

/* ── таблица сводки для выгрузки картинкой (доля полностью решённых A/B) ── */
export function SummaryTableSvg({ svgRef, rows, meta, C }) {
  const W = 900, headTop = 104, headH = 27, bodyTop = 140, rowH = 46;
  const H = bodyTop + rows.length * rowH + 40;
  const rankX = 36, logoX = 56, logoSz = 30, nameX = 96, aX = 452, bX = 672, barOff = 62, barW = 128;
  const cell = (x, s, cy) => {
    if (s == null) return <text x={x} y={cy + 5} fontSize="12" fill={C.muted}>не измерялось</text>;
    const pct = Math.round(s * 100); const col = solvedHex(C, s);
    return (
      <g>
        <text x={x} y={cy + 7}><tspan fontSize="21" fontWeight="700" fill={col}>{pct}</tspan><tspan fontSize="12" fontWeight="600" fill={col} dx="1">%</tspan></text>
        <rect x={x + barOff} y={cy - 4} width={barW} height={7} rx={3.5} fill={C.grid} />
        <rect x={x + barOff} y={cy - 4} width={Math.max(2, barW * s)} height={7} rx={3.5} fill={col} />
      </g>
    );
  };
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={24} y={30} fontSize="18" fontWeight="700" fill={C.ink}>Рейтинг PRISM — доля полностью решённых задач</text>
      <text x={24} y={53} fontSize="12.5" fill={C.sub}>
        <tspan fontWeight="700" fill={C.ink}>Категория A — алгоритмические:</tspan>
        <tspan dx="6"> чистый код без базы. Движок — OneScript + BSL LS.</tspan>
      </text>
      <text x={24} y={72} fontSize="12.5" fill={C.sub}>
        <tspan fontWeight="700" fill={C.ink}>Категория B — платформенные:</tspan>
        <tspan dx="6"> запросы, регистры, метаданные. Движок — реальная 1С в Docker.</tspan>
      </text>
      <text x={24} y={91} fontSize="11" fill={C.muted}>«решено» — код прошёл все скрытые проверки · {rows.length} моделей</text>
      <rect x={0} y={headTop} width={W} height={headH} fill={C.head} />
      <text x={rankX} y={headTop + 18} textAnchor="middle" fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>#</text>
      <text x={logoX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>МОДЕЛЬ</text>
      <text x={aX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>АЛГОРИТМИЧЕСКИЕ · A</text>
      <text x={bX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>ПЛАТФОРМЕННЫЕ · B</text>
      {rows.map((m, i) => {
        const y0 = bodyTop + i * rowH; const cy = y0 + rowH / 2; const top = i === 0;
        return (
          <g key={m.id}>
            <rect x={0} y={y0} width={W} height={rowH} fill={top ? C.tint : (i % 2 ? C.zebra : 'transparent')} />
            <rect x={rankX - 13} y={cy - 13} width={26} height={26} rx={7} fill={top ? C.brand : C.head} />
            <text x={rankX} y={cy + 4} textAnchor="middle" fontSize="12" fontWeight="700" fill={top ? C.brandInk : C.sub}>{i + 1}</text>
            <LogoGlyph x={logoX} cy={cy} size={logoSz} m={m} C={C} />
            <text x={nameX} y={cy - 2} fontSize="14" fontWeight={top ? 700 : 600} fill={C.ink}>{m.name}</text>
            <text x={nameX} y={cy + 13} fontSize="10.5" fill={C.muted}>{m.family || m.vendor || ''}</text>
            {cell(aX, m.A?.solved, cy)}
            {cell(bX, m.B?.solved, cy)}
          </g>
        );
      })}
      <text x={W - 16} y={H - 14} textAnchor="end" fontSize="9.5" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

/* ── таблица баллов SMOP категории для выгрузки картинкой ── */
export function ScoresTableSvg({ svgRef, cat, rows, meta, C }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const axes = CAT_AXES[cat];
  const W = 900, headTop = 84, headH = 25, bodyTop = 116, rowH = 44;
  const H = bodyTop + rows.length * rowH + 40;
  const rankX = 34, logoX = 52, logoSz = 28, nameX = 90, axStart = 306, axEnd = 772, qX = 838;
  const colW = (axEnd - axStart) / axes.length;
  const engine = cat === 'A'
    ? 'категория A · алгоритмические — чистый код без базы. Движок — OneScript + BSL LS'
    : 'категория B · платформенные — запросы, регистры, метаданные. Движок — реальная 1С в Docker';
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={24} y={30} fontSize="17" fontWeight="700" fill={C.ink}>Рейтинг PRISM — категория {cat} · баллы SMOP</text>
      <text x={24} y={51} fontSize="12" fill={C.sub}>{engine}</text>
      <text x={24} y={69} fontSize="11" fill={C.muted}>{axes.map((a) => `${a} — ${AXIS_NAME[a]}`).join(' · ')} · Q — средний балл по осям · {rows.length} моделей</text>
      <rect x={0} y={headTop} width={W} height={headH} fill={C.head} />
      <text x={logoX} y={headTop + 17} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>МОДЕЛЬ</text>
      {axes.map((a, i) => <text key={a} x={axStart + i * colW + colW / 2} y={headTop + 17} textAnchor="middle" fontSize="11.5" fontWeight="700" fill={AXIS[a]}>{a}</text>)}
      <text x={qX} y={headTop + 17} textAnchor="middle" fontSize="11.5" fontWeight="700" fill={C.ink}>Q</text>
      {rows.map((m, i) => {
        const y0 = bodyTop + i * rowH; const cy = y0 + rowH / 2; const top = i === 0; const q = m[qKey];
        return (
          <g key={m.id}>
            <rect x={0} y={y0} width={W} height={rowH} fill={top ? C.tint : (i % 2 ? C.zebra : 'transparent')} />
            <rect x={rankX - 12} y={cy - 12} width={24} height={24} rx={6} fill={top ? C.brand : C.head} />
            <text x={rankX} y={cy + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill={top ? C.brandInk : C.sub}>{i + 1}</text>
            <LogoGlyph x={logoX} cy={cy} size={logoSz} m={m} C={C} />
            <text x={nameX} y={cy - 1} fontSize="13" fontWeight={top ? 700 : 600} fill={C.ink}>{m.name}</text>
            <text x={nameX} y={cy + 12} fontSize="10" fill={C.muted}>{m.family || m.vendor || ''}</text>
            {axes.map((a, ai) => {
              const v = m[cat] && m[cat][a]; const cx = axStart + ai * colW + colW / 2; const cw = Math.min(colW - 10, 70);
              if (v == null) return <text key={a} x={cx} y={cy + 4} textAnchor="middle" fontSize="12" fill={C.muted}>—</text>;
              return (
                <g key={a}>
                  <rect x={cx - cw / 2} y={cy - 13} width={cw} height={26} rx={6} fill={AXIS[a]} fillOpacity={0.12 + (v / 10) * 0.5} />
                  <text x={cx} y={cy + 4} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={v >= 4 ? C.ink : C.sub}>{v.toFixed(1)}</text>
                </g>
              );
            })}
            <text x={qX} y={cy + 5} textAnchor="middle" fontSize="18" fontWeight="700" fill={C.ink}>{q.toFixed(2)}</text>
          </g>
        );
      })}
      <text x={W - 16} y={H - 14} textAnchor="end" fontSize="9.5" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

function Btn({ children, onClick, active, primary }) {
  const [h, setH] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{ cursor: 'pointer', borderRadius: 'var(--radius-sm)', padding: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap',
        border: `1px solid ${active ? 'var(--brand)' : 'var(--line)'}`,
        background: primary ? (h ? 'var(--brand-strong)' : 'var(--brand)') : active ? 'var(--surface-raised)' : (h ? 'var(--surface-raised)' : 'var(--surface-sunken)'),
        color: primary ? 'var(--brand-ink)' : active ? 'var(--ink-100)' : 'var(--ink-300)' }}>{children}</button>
  );
}

// выбор охвата моделей: Топ-10 · Все · Выбрать
function ModelScope({ ranked, scope, setScope, custom, setCustom }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>модели:</span>
        <Btn active={scope === 'top10'} onClick={() => setScope('top10')}>Топ-10</Btn>
        <Btn active={scope === 'all'} onClick={() => setScope('all')}>Все ({ranked.length})</Btn>
        <Btn active={scope === 'custom'} onClick={() => { if (!custom.size) setCustom(new Set(ranked.slice(0, 10).map((m) => m.id))); setScope('custom'); }}>Выбрать{scope === 'custom' ? ` (${custom.size})` : ''}</Btn>
      </div>
      {scope === 'custom' && (
        <div style={{ marginTop: 8, maxHeight: 168, overflowY: 'auto', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', padding: '8px 10px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '4px 12px' }}>
          {ranked.map((m) => (
            <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, color: 'var(--ink-200)', cursor: 'pointer' }}>
              <input type="checkbox" checked={custom.has(m.id)} onChange={(e) => { const n = new Set(custom); if (e.target.checked) n.add(m.id); else n.delete(m.id); setCustom(n); }} />
              {m.name}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function LeaderChart({ cat, models = [], meta = {}, navigate }) {
  const theme = useTheme();
  const C = THEME[theme];
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const [kind, setKind] = React.useState('radar');
  const [hover, setHover] = React.useState(null);
  const [scope, setScope] = React.useState('top10');
  const [custom, setCustom] = React.useState(new Set());
  const ref = React.useRef(null);
  const name = `prism_${kind}_${cat}`;

  const ranked = React.useMemo(() => models.filter((m) => m[qKey] != null).sort((a, b) => b[qKey] - a[qKey]), [models, qKey]);
  const shown = scope === 'all' ? ranked : scope === 'top10' ? ranked.slice(0, 10) : ranked.filter((m) => custom.has(m.id));

  const tab = (k, label) => (
    <button onClick={() => setKind(k)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px 8px', marginRight: 18, borderBottom: `2px solid ${kind === k ? 'var(--brand)' : 'transparent'}`, fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: kind === k ? 600 : 500, color: kind === k ? 'var(--ink-100)' : 'var(--ink-400)' }}>{label}</button>
  );
  const Chart = kind === 'radar' ? RadarSvg : kind === 'ranking' ? RankingSvg : BarsSvg;
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--radius-lg)', padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
        <div>{tab('radar', 'Радар SMOP')}{tab('ranking', 'Рейтинг Q')}{tab('bars', 'Оси SMOP')}</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn onClick={() => ref.current && exportSvg(ref.current, name)}>↓ SVG</Btn>
          <Btn primary onClick={() => ref.current && exportPng(ref.current, name, C.bg)}>↓ PNG</Btn>
        </div>
      </div>
      <ModelScope ranked={ranked} scope={scope} setScope={setScope} custom={custom} setCustom={setCustom} />
      {shown.length === 0
        ? <p style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-400)', padding: '30px 0', textAlign: 'center' }}>выбери хотя бы одну модель</p>
        : <Chart svgRef={ref} cat={cat} shown={shown} meta={meta} C={C} hover={hover} setHover={setHover} navigate={navigate} />}
    </div>
  );
}

/* Панель выгрузки таблицы картинкой. Тумблер охвата живёт у родителя (он же фильтрует
   видимую таблицу), сюда приходит готовый render(ref, C) с нужным SVG — он рисуется скрыто. */
export function TableExport({ scope, setScope, count, name, render }) {
  const theme = useTheme();
  const C = THEME[theme];
  const ref = React.useRef(null);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
      <Btn active={scope === 'top10'} onClick={() => setScope('top10')}>Топ-10</Btn>
      <Btn active={scope === 'all'} onClick={() => setScope('all')}>Все ({count})</Btn>
      <span style={{ flex: 1 }} />
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>скачать:</span>
      <Btn onClick={() => ref.current && exportSvg(ref.current, name)}>↓ SVG</Btn>
      <Btn primary onClick={() => ref.current && exportPng(ref.current, name, C.bg)}>↓ PNG</Btn>
      <div style={{ position: 'absolute', left: -99999, top: 0, width: 900, pointerEvents: 'none' }} aria-hidden="true">
        {render(ref, C)}
      </div>
    </div>
  );
}
