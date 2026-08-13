/* PRISM web — интерактивные графики лидерборда (SVG, рисуются на клиенте).
   Рейтинг Q · Радар SMOP · Оси SMOP + общий scatter A↔B. Наведение/переход на модель.
   Кнопки «Скачать» экспортируют ТЕКУЩИЙ вид в SVG/PNG (сериализация того же <svg> + canvas).

   Тема полотна следует теме сайта (data-theme) и обновляется при переключении.
   Цвета в <svg> — конкретные hex (из палитры темы), не CSS-var: иначе не сериализуются в экспорт. */
import React from 'react';
import { vendorGlyph } from './VendorLogo.jsx';
import { useIsMobile } from '../../lib/useMediaQuery.js';
import { buildInsights } from '../../lib/insights.js';
import { verdictDetail } from './NarrativeCard.jsx';

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
function RankingSvg({ svgRef, cat, shown, meta, C, hover, setHover, navigate, mobile }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const rows = shown; // уже отсортировано лучшая→худшая; лучший сверху
  if (mobile) {
    // мобила: узкий холст, имя и балл СТРОКОЙ над баром — левого поля под подписи нет
    const W = 440, L = 16, R = W - 16, top = 40, rh = 42, H = top + rows.length * rh + 34;
    const x = (q) => L + (q / 10) * (R - L);
    return (
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
        <text x={12} y={22} fontSize="13" fontWeight="700" fill={C.ink}>Рейтинг PRISM — категория {cat} · Q</text>
        {[0, 2, 4, 6, 8, 10].map((t) => (
          <g key={t}>
            <line x1={x(t)} y1={top - 4} x2={x(t)} y2={H - 26} stroke={C.grid} strokeDasharray="2 4" />
            <text x={x(t)} y={H - 12} textAnchor="middle" fontSize="9" fill={C.muted}>{t}</text>
          </g>
        ))}
        {rows.map((m, i) => {
          const y = top + i * rh; const q = m[qKey]; const rank = i + 1;
          return (
            <g key={m.id} style={{ cursor: 'pointer' }} onClick={() => navigate && navigate('model', m.id)}>
              <text x={L} y={y + 12} fontSize="11.5" fill={C.ink} fontWeight={rank === 1 ? 700 : 400}>{`${rank}. ${m.name}`}</text>
              <text x={R} y={y + 12} textAnchor="end" fontSize="11" fontWeight="600" fill={C.sub}>{q.toFixed(2)}</text>
              <rect x={L} y={y + 18} width={Math.max(2, x(q) - L)} height={13} rx={3} fill={qColor(q)} opacity={0.9} />
            </g>
          );
        })}
        <text x={W - 10} y={H - 3} textAnchor="end" fontSize="8" fill={C.muted}>{STAMP(meta)}</text>
      </svg>
    );
  }
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
function RadarSvg({ svgRef, cat, shown, meta, C, hover, setHover, navigate, mobile }) {
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const axes = CAT_AXES[cat];
  if (mobile) {
    // мобила: радар сверху по центру, легенда КОЛОНКОЙ ПОД ним (справа не помещается)
    const W = 440, cx = 220, cy = 226, R = 140;
    const legTop = cy + R + 42;
    const H = legTop + shown.length * 20 + 16;
    const ang = (i) => -Math.PI / 2 + (i / axes.length) * 2 * Math.PI;
    const pt = (i, v) => [cx + Math.cos(ang(i)) * R * (v / 10), cy + Math.sin(ang(i)) * R * (v / 10)];
    return (
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
        <text x={12} y={22} fontSize="13" fontWeight="700" fill={C.ink}>Профиль SMOP — категория {cat} ({shown.length})</text>
        {[2, 4, 6, 8, 10].map((r) => (
          <polygon key={r} points={axes.map((_, i) => pt(i, r).join(',')).join(' ')} fill="none" stroke={C.grid} strokeDasharray="2 3" />
        ))}
        {axes.map((a, i) => {
          const [ex, ey] = pt(i, 11.2);
          return (<g key={a}><line x1={cx} y1={cy} x2={pt(i, 10)[0]} y2={pt(i, 10)[1]} stroke={C.grid} /><text x={ex} y={ey + 4} textAnchor="middle" fontSize="12" fontWeight="700" fill={AXIS[a]}>{a}</text></g>);
        })}
        {shown.map((m, idx) => {
          const col = PALETTE[idx % PALETTE.length];
          const pts = axes.map((a, i) => pt(i, (m[cat] && m[cat][a]) || 0).join(',')).join(' ');
          return <polygon key={m.id} points={pts} fill={col} fillOpacity={0.05} stroke={col} strokeWidth={1.4}
            style={{ cursor: 'pointer' }} onClick={() => navigate && navigate('model', m.id)} />;
        })}
        {shown.map((m, idx) => {
          const col = PALETTE[idx % PALETTE.length]; const y = legTop + idx * 20;
          return (
            <g key={m.id} style={{ cursor: 'pointer' }} onClick={() => navigate && navigate('model', m.id)}>
              <circle cx={22} cy={y - 3} r={4.5} fill={col} />
              <text x={34} y={y} fontSize="11" fill={C.ink}>{m.name}</text>
              <text x={W - 18} y={y} textAnchor="end" fontSize="10.5" fontWeight="600" fill={C.sub}>{m[qKey].toFixed(2)}</text>
            </g>
          );
        })}
        <text x={W - 10} y={H - 3} textAnchor="end" fontSize="8" fill={C.muted}>{STAMP(meta)}</text>
      </svg>
    );
  }
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
function BarsSvg({ svgRef, cat, shown, meta, C, hover, setHover, navigate, mobile }) {
  const axes = CAT_AXES[cat];
  if (mobile) {
    // мобила: имя над группой баров; легенда осей с переносом строк
    const W = 440, L = 16, R = W - 46;
    const x = (v) => L + (v / 10) * (R - L);
    const chips = []; let lx = L, ly = 42;
    for (const a of axes) {
      const label = `${a} · ${AXIS_NAME[a]}`;
      const w = 12 + 6 + label.length * 5.6 + 14;
      if (lx + w > W - 12) { lx = L; ly += 16; }
      chips.push({ a, label, x: lx, y: ly });
      lx += w;
    }
    const T = ly + 20;
    const bh = 10, rowH = 18 + axes.length * (bh + 1) + 8;
    const H = T + shown.length * rowH + 28;
    return (
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
        <text x={12} y={22} fontSize="13" fontWeight="700" fill={C.ink}>Профиль по осям SMOP — кат. {cat} ({shown.length})</text>
        {chips.map((ch) => (
          <g key={ch.a}><rect x={ch.x} y={ch.y - 9} width={11} height={11} fill={AXIS[ch.a]} rx={2} /><text x={ch.x + 16} y={ch.y} fontSize="10" fill={C.sub}>{ch.label}</text></g>
        ))}
        {[0, 2, 4, 6, 8, 10].map((t) => (
          <g key={t}><line x1={x(t)} y1={T - 4} x2={x(t)} y2={H - 22} stroke={C.grid} strokeDasharray="2 4" /><text x={x(t)} y={H - 9} textAnchor="middle" fontSize="9" fill={C.muted}>{t}</text></g>
        ))}
        {shown.map((m, ri) => {
          const y0 = T + ri * rowH;
          return (
            <g key={m.id} style={{ cursor: 'pointer' }} onClick={() => navigate && navigate('model', m.id)}>
              <text x={L} y={y0 + 12} fontSize="11.5" fill={C.ink} fontWeight={ri === 0 ? 700 : 400}>{`${ri + 1}. ${m.name}`}</text>
              {axes.map((a, ai) => {
                const v = (m[cat] && m[cat][a]) || 0; const by = y0 + 18 + ai * (bh + 1);
                return (<g key={a}><rect x={L} y={by} width={Math.max(1, x(v) - L)} height={bh} fill={AXIS[a]} opacity={0.9} /><text x={x(v) + 4} y={by + bh - 2} fontSize="8.5" fill={C.sub}>{v.toFixed(1)}</text></g>);
              })}
            </g>
          );
        })}
        <text x={W - 10} y={H - 3} textAnchor="end" fontSize="8" fill={C.muted}>{STAMP(meta)}</text>
      </svg>
    );
  }
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
  const rankX = 36, logoX = 56, logoSz = 30, nameX = 96, aX = 300, bX = 470, qX = 712, barOff = 52, barW = 104;
  // «решено %» — контекстная колонка; цвет по уровню, как на витрине
  const cell = (x, s, cy) => {
    if (s == null) return <text x={x} y={cy + 5} fontSize="12" fill={C.muted}>—</text>;
    const pct = Math.round(s * 100); const col = solvedHex(C, s);
    return (
      <g>
        <text x={x} y={cy + 7}><tspan fontSize="19" fontWeight="700" fill={col}>{pct}</tspan><tspan fontSize="11" fontWeight="600" fill={col} dx="1">%</tspan></text>
        <rect x={x + barOff} y={cy - 4} width={barW} height={7} rx={3.5} fill={C.grid} />
        <rect x={x + barOff} y={cy - 4} width={Math.max(2, barW * s)} height={7} rx={3.5} fill={col} />
      </g>
    );
  };
  // балл Q — главная (сортирующая) цифра
  const qCell = (x, q, cy) => {
    if (q == null) return <text x={x} y={cy + 5} fontSize="12" fill={C.muted}>—</text>;
    return <text x={x} y={cy + 7}><tspan fontSize="23" fontWeight="700" fill={C.ink}>{q.toFixed(2)}</tspan><tspan fontSize="11" fill={C.muted} dx="3">/10</tspan></text>;
  };
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={24} y={30} fontSize="18" fontWeight="700" fill={C.ink}>Рейтинг PRISM — по среднему баллу Q (метрика SMOP)</text>
      <text x={24} y={53} fontSize="12.5" fill={C.sub}>
        <tspan fontWeight="700" fill={C.ink}>Категория A — алгоритмические:</tspan>
        <tspan dx="6"> чистый код без базы. Движок — OneScript + BSL LS.</tspan>
      </text>
      <text x={24} y={72} fontSize="12.5" fill={C.sub}>
        <tspan fontWeight="700" fill={C.ink}>Категория B — платформенные:</tspan>
        <tspan dx="6"> запросы, регистры, метаданные. Движок — реальная 1С в Docker.</tspan>
      </text>
      <text x={24} y={91} fontSize="11" fill={C.muted}>Q — итоговый балл SMOP по 4 осям (0–10) · «решено» — доля задач со всеми пройденными тестами · {rows.length} моделей</text>
      <rect x={0} y={headTop} width={W} height={headH} fill={C.head} />
      <text x={rankX} y={headTop + 18} textAnchor="middle" fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>#</text>
      <text x={logoX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>МОДЕЛЬ</text>
      <text x={aX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>РЕШЕНО · A</text>
      <text x={bX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>РЕШЕНО · B</text>
      <text x={qX} y={headTop + 18} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>БАЛЛ Q</text>
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
            {qCell(qX, m.qOverall, cy)}
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
              // O с малым покрытием (замер меньше чем на половине задач) — приглушаем и подписываем
              const low = a === 'O' && m[cat].oN != null && m[cat].funnel?.n && m[cat].oN < m[cat].funnel.n / 2;
              return (
                <g key={a}>
                  <rect x={cx - cw / 2} y={cy - 13} width={cw} height={26} rx={6} fill={AXIS[a]} fillOpacity={low ? 0.06 : 0.12 + (v / 10) * 0.5} />
                  <text x={cx} y={cy + (low ? 0 : 4)} textAnchor="middle" fontSize="12.5" fontWeight="600" fill={low ? C.muted : (v >= 4 ? C.ink : C.sub)}>{v.toFixed(1)}</text>
                  {low && <text x={cx} y={cy + 11} textAnchor="middle" fontSize="8" fill={C.muted}>{m[cat].oN}/{m[cat].funnel.n}</text>}
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

/* ── рейтинг «Экономики» для выгрузки картинкой (качество ↔ цена/скорость/токены) ──
   rows приходят готовыми из Economy.jsx — тот же порядок и те же доли полос, что на экране:
   сначала парето-оптимум (по Q), затем остальные. */
const ECON_TITLE = { cost: 'цена одной генерации', time: 'среднее время на задачу', tokens: 'токенов на генерацию' };
const ECON_NOTE = {
  cost: 'цена = прайс-лист провайдера × реально сгенерированные токены (средняя по всем задачам)',
  time: 'время ответа модели на одну задачу, секунды (замер прогона, зависит от нагрузки провайдера)',
  tokens: 'вход + выход, среднее на один ответ; от тарифа не зависит — мало токенов ≠ дёшево',
};
const ECON_BETTER = { cost: 'дешевле', time: 'быстрее', tokens: 'экономнее' };
const ECON_COL = { cost: 'ЦЕНА / ГЕНЕРАЦИЯ', time: 'ВРЕМЯ / ЗАДАЧА', tokens: 'ТОКЕНОВ / ГЕНЕРАЦИЯ' };

export function EconomyTableSvg({ svgRef, rows, metric, fmt, meta, C }) {
  const W = 900, headTop = 96, headH = 26, bodyTop = 130, rowH = 44, bandH = 28;
  const firstRest = rows.findIndex((r) => !r.optimum);
  const band = firstRest > 0 ? firstRest : -1; // полосу-разделитель рисуем, только если оптимум не один сплошной блок
  const H = bodyTop + rows.length * rowH + (band >= 0 ? bandH : 0) + 40;
  const rankX = 34, logoX = 52, logoSz = 28, nameX = 90;
  const qX = 300, xX = 520, barW = 150, chipX = 800;
  const qMax = Math.max(...rows.map((r) => r.q), 1);
  const maxX = Math.max(...rows.map((r) => r.x), 1);
  let shift = 0; // сдвиг строк после полосы-разделителя
  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <text x={24} y={30} fontSize="17" fontWeight="700" fill={C.ink}>Экономика PRISM — качество ↔ {ECON_TITLE[metric]}</text>
      <text x={24} y={51} fontSize="12" fill={C.sub}>{ECON_NOTE[metric]}</text>
      <text x={24} y={69} fontSize="11" fill={C.muted}>«оптимум» — нет модели одновременно {ECON_BETTER[metric]} И сильнее · Q — итоговый балл SMOP по 4 осям (0–10) · {rows.length} моделей</text>
      <rect x={0} y={headTop} width={W} height={headH} fill={C.head} />
      <text x={logoX} y={headTop + 17} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>МОДЕЛЬ</text>
      <text x={qX} y={headTop + 17} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>КАЧЕСТВО</text>
      <text x={xX} y={headTop + 17} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>{ECON_COL[metric]}</text>
      <text x={W - 24} y={headTop + 17} textAnchor="end" fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.muted}>ВЫГОДА</text>
      {rows.map((m, i) => {
        if (i === band) shift = bandH;
        const y0 = bodyTop + i * rowH + shift; const cy = y0 + rowH / 2;
        const qw = Math.max(2, barW * (m.q / qMax)), xw = Math.max(2, barW * (m.x / maxX));
        return (
          <g key={m.id}>
            {i === band && (
              <g>
                <rect x={0} y={y0 - bandH} width={W} height={bandH} fill={C.head} />
                <text x={24} y={y0 - bandH / 2 + 4} fontSize="10.5" fontWeight="600" letterSpacing="0.04em" fill={C.muted}>ОСТАЛЬНЫЕ — ЕСТЬ ВАРИАНТ {ECON_BETTER[metric].toUpperCase()} И СИЛЬНЕЕ</text>
              </g>
            )}
            <rect x={0} y={y0} width={W} height={rowH} fill={m.optimum ? C.tint : (i % 2 ? C.zebra : 'transparent')} />
            {m.optimum && <rect x={0} y={y0} width={3} height={rowH} fill={C.ok} />}
            <rect x={rankX - 12} y={cy - 12} width={24} height={24} rx={6} fill={i === 0 ? C.brand : C.head} />
            <text x={rankX} y={cy + 4} textAnchor="middle" fontSize="11" fontWeight="700" fill={i === 0 ? C.brandInk : C.sub}>{i + 1}</text>
            <LogoGlyph x={logoX} cy={cy} size={logoSz} m={m} C={C} />
            <text x={nameX} y={cy - 1} fontSize="13" fontWeight={i === 0 ? 700 : 600} fill={C.ink}>{m.name}</text>
            <text x={nameX} y={cy + 12} fontSize="10" fill={C.muted}>{m.dominator ? `уступает ${clip(m.dominator, 26)}` : (m.family || m.vendor || '')}</text>
            <text x={qX} y={cy - 5} fontSize="12.5" fontWeight="700" fill={qColor(m.q)}>{m.q.toFixed(2)}</text>
            <rect x={qX} y={cy + 3} width={barW} height={7} rx={3.5} fill={C.grid} />
            <rect x={qX} y={cy + 3} width={qw} height={7} rx={3.5} fill={qColor(m.q)} />
            <text x={xX} y={cy - 5} fontSize="12.5" fontWeight="700" fill={C.ink}>{fmt(m.x)}</text>
            {m.hint && <text x={xX + 62} y={cy - 5} fontSize="10" fill={C.muted}>{m.hint}</text>}
            <rect x={xX} y={cy + 3} width={barW} height={7} rx={3.5} fill={C.grid} />
            <rect x={xX} y={cy + 3} width={xw} height={7} rx={3.5} fill={C.sub} />
            {m.optimum && (
              <g>
                <rect x={chipX} y={cy - 11} width={76} height={22} rx={11} fill={C.ok} fillOpacity={0.16} stroke={C.ok} strokeOpacity={0.5} />
                <text x={chipX + 38} y={cy + 4} textAnchor="middle" fontSize="10.5" fontWeight="700" fill={C.ok}>оптимум</text>
              </g>
            )}
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
        <Btn active={scope === 'all'} onClick={() => setScope('all')}>Все ({ranked.length})</Btn>
        <Btn active={scope === 'top10'} onClick={() => setScope('top10')}>Топ-10</Btn>
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
  const isMobile = useIsMobile();
  const qKey = cat === 'A' ? 'qA' : 'qB';
  const [kind, setKind] = React.useState('radar');
  const [hover, setHover] = React.useState(null);
  const [scope, setScope] = React.useState('all');
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
        {/* выгрузка картинки — только на десктопе (как в TableExport) */}
        {!isMobile && (
          <div style={{ display: 'flex', gap: 8 }}>
            <Btn onClick={() => ref.current && exportSvg(ref.current, name)}>↓ SVG</Btn>
            <Btn primary onClick={() => ref.current && exportPng(ref.current, name, C.bg)}>↓ PNG</Btn>
          </div>
        )}
      </div>
      <ModelScope ranked={ranked} scope={scope} setScope={setScope} custom={custom} setCustom={setCustom} />
      {shown.length === 0
        ? <p style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-400)', padding: '30px 0', textAlign: 'center' }}>выбери хотя бы одну модель</p>
        : <Chart svgRef={ref} cat={cat} shown={shown} meta={meta} C={C} hover={hover} setHover={setHover} navigate={navigate} mobile={isMobile} />}
    </div>
  );
}

/* Панель выгрузки таблицы картинкой. Тумблер охвата живёт у родителя (он же фильтрует
   видимую таблицу), сюда приходит готовый render(ref, C) с нужным SVG — он рисуется скрыто. */
export function TableExport({ scope, setScope, count, name, render }) {
  const theme = useTheme();
  const C = THEME[theme];
  const isMobile = useIsMobile();
  const ref = React.useRef(null);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
      <Btn active={scope === 'all'} onClick={() => setScope('all')}>Все ({count})</Btn>
      <Btn active={scope === 'top10'} onClick={() => setScope('top10')}>Топ-10</Btn>
      {/* выгрузка картинки — только на десктопе (на телефоне SVG/PNG не скачивают) */}
      {!isMobile && (
        <>
          <span style={{ flex: 1 }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>скачать:</span>
          <Btn onClick={() => ref.current && exportSvg(ref.current, name)}>↓ SVG</Btn>
          <Btn primary onClick={() => ref.current && exportPng(ref.current, name, C.bg)}>↓ PNG</Btn>
          <div style={{ position: 'absolute', left: -99999, top: 0, width: 900, pointerEvents: 'none' }} aria-hidden="true">
            {render(ref, C)}
          </div>
        </>
      )}
    </div>
  );
}

/* ── инфографика карточки модели: расширенная сводка одной картинкой (SVG → SVG/PNG) ── */
const fmtTokCard = (n) => (n == null ? '—' : n < 1000 ? `${n}` : `${(n / 1000).toFixed(1)}к`);
const fmtReleasedCard = (r) => {
  if (!r) return null;
  const p = String(r).split('-');
  if (p.length >= 3) return `${p[2]}.${p[1]}.${p[0]}`;
  if (p.length === 2) return `${p[1]}.${p[0]}`;
  return r;
};
const clip = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : s);

function ModelCardSvg({ svgRef, model, ins, meta, C }) {
  const W = 820, pad = 32, cw = W - pad * 2;
  const axA = ['S', 'M', 'O'], axB = ['S', 'M', 'O', 'P'];
  const vd = verdictDetail(model, ins);
  const pluses = (vd.pluses || []).slice(0, 4);

  // мета-строка модели: релиз · класс весов · тариф
  const metaBits = [];
  const rel = fmtReleasedCard(model.released);
  if (rel) metaBits.push(`релиз ${rel}`);
  if (model.weights) metaBits.push(model.weights === 'open' ? 'открытые веса' : 'закрытые веса');
  const pIn = model.econ?.priceIn, pOut = model.econ?.priceOut;
  if (pIn != null && pOut != null) metaBits.push(`тариф $${pIn}/$${pOut} за 1M`);
  const metaLine = metaBits.join('  ·  ');

  // вертикальный курсор для гибкого верхнего блока (мета, вердикт, сильные стороны)
  let y = 132; // после шапки
  const leadY = y; y += 32;
  const plusHeadY = pluses.length ? y : null; if (pluses.length) y += 24;
  const plusYs = pluses.map((_, i) => plusHeadY + 24 + i * 24);
  if (pluses.length) y = plusYs[plusYs.length - 1] + 22;

  const boxTop = y + 6;
  const boxHeadH = 58, rowH = 27, maxAx = 4;
  const boxH = boxHeadH + 14 + maxAx * rowH + 10;
  const bw = (cw - 16) / 2;
  const econTop = boxTop + boxH + 40;
  // сравнение: сильнее / слабее / дешевле-дороже
  const cmp = [];
  if (ins.beats?.length) cmp.push(['СИЛЬНЕЕ', C.ok, ins.beats.slice(0, 5).join(', ')]);
  if (ins.losesTo?.length) cmp.push(['СЛАБЕЕ', C.muted, ins.losesTo.slice(0, 5).join(', ')]);
  if (ins.cheaperThan?.length) cmp.push(['ДЕШЕВЛЕ', C.ok, ins.cheaperThan.slice(0, 4).map((x) => `${x.mult} ${x.name}`).join(', ')]);
  else if (ins.pricierThan?.length) cmp.push(['ДОРОЖЕ', C.warn, ins.pricierThan.slice(0, 4).map((x) => `${x.mult} ${x.name}`).join(', ')]);
  const econBottom = econTop + 44;
  const cmpTop = econBottom + 34;                      // воздух между экономикой и «сильнее/дороже»
  const cmpBottom = cmp.length ? cmpTop + (cmp.length - 1) * 24 + 8 : econBottom;

  // где ломается — воронка исходов по категориям (те, где есть прогон)
  const OUTCOME = [['решено', C.ok], ['неверный ответ', '#d8b13e'], ['ошибка выполнения', '#dd7a3b'], ['не компилируется', C.danger]];
  const funCats = [];
  if (model.A?.funnel?.n) funCats.push(['A', model.A.funnel]);
  if (model.B?.funnel?.n) funCats.push(['B', model.B.funnel]);
  const hasFun = funCats.length > 0;
  const funHeadY = cmpBottom + 40;
  const funLegendY = funHeadY + 22;
  const funRowsTop = funLegendY + 26;
  const funRowH = 28;
  const funBottom = hasFun ? funRowsTop + funCats.length * funRowH - 4 : cmpBottom;

  // профиль навыков — балл по видам задач (тегам) из meta.profileCols
  const pc = meta.profileCols || { A: [], B: [] };
  const colsA = pc.A || [], colsB = pc.B || [];
  const tagLabels = meta.tagLabels || {};
  const profN = Math.max(colsA.length, colsB.length);
  const hasProf = profN > 0 && (model.A?.profile || model.B?.profile);
  const profHeadY = (hasFun ? funBottom : cmpBottom) + 40;
  const profBoxTop = profHeadY + 16;
  const profBoxH = 46 + profN * 22 + 12;
  const profBottom = hasProf ? profBoxTop + profBoxH : (hasFun ? funBottom : cmpBottom);

  const H = profBottom + 36;

  const axisRow = (bx, by, w, a, v) => {
    // labelW шире самого длинного имени оси («оптимальность»), чтобы подпись не налезала на полосу
    const col = AXIS[a], labelW = 128, valW = 30, barX = bx + labelW, barW = w - labelW - valW - 6;
    return (
      <g key={a}>
        <rect x={bx} y={by - 9} width={18} height={18} rx={4} fill={col} fillOpacity={0.16} />
        <text x={bx + 9} y={by + 4} textAnchor="middle" fontSize="10.5" fontWeight="700" fill={col}>{a}</text>
        <text x={bx + 25} y={by + 4} fontSize="11.5" fill={C.sub}>{AXIS_NAME[a]}</text>
        {v == null
          ? <text x={bx + w} y={by + 4} textAnchor="end" fontSize="10.5" fill={C.muted}>не изм.</text>
          : (<>
            <rect x={barX} y={by - 3} width={barW} height={6} rx={3} fill={C.grid} />
            <rect x={barX} y={by - 3} width={Math.max(2, barW * (v / 10))} height={6} rx={3} fill={col} />
            <text x={bx + w} y={by + 4} textAnchor="end" fontSize="11.5" fontWeight="600" fill={C.ink}>{v.toFixed(1)}</text>
          </>)}
      </g>
    );
  };
  const catBox = (bx, title, sub, q, solved, axes, scores) => (
    <g>
      <rect x={bx} y={boxTop} width={bw} height={boxH} rx={12} fill={C.head} stroke={C.grid} />
      <text x={bx + 16} y={boxTop + 25} fontSize="13.5" fontWeight="700" fill={C.ink}>{title}</text>
      <text x={bx + 16} y={boxTop + 42} fontSize="11" fill={C.muted}>{sub}</text>
      <text x={bx + bw - 16} y={boxTop + 30} textAnchor="end"><tspan fontSize="26" fontWeight="700" fill={C.ink}>{q != null ? q.toFixed(2) : '—'}</tspan><tspan fontSize="11" fill={C.muted} dx="2">/10</tspan></text>
      <text x={bx + bw - 16} y={boxTop + 47} textAnchor="end" fontSize="11" fontWeight="600" fill={solvedHex(C, solved)}>решено {solved != null ? Math.round(solved * 100) : '—'}%</text>
      {axes.map((a, i) => axisRow(bx + 16, boxTop + boxHeadH + 12 + i * rowH, bw - 32, a, scores?.[a]))}
    </g>
  );
  const econ = [
    ['цена ответа', ins.genCostFmt || '—'],
    ['скорость', ins.avgTime != null ? `${ins.avgTime} с` : '—'],
    ['токенов', fmtTokCard(model.econ?.tokPerGen)],
    ['общая оценка', ins.qOverall != null ? `${ins.qOverall.toFixed(1)} / 10` : '—'],
  ];
  const ew = cw / econ.length;
  const rankTxt = ins.rankOverall <= 3 ? `ТОП-${ins.rankOverall}` : `#${ins.rankOverall}`;

  // строка воронки: метка категории + сегментированная полоса исходов + % решено
  const funRow = (label, f, by) => {
    const lw = 26, cntW = 76, barX = pad + lw, barW = cw - lw - cntW - 8;
    const pct = Math.round((f.buckets['решено'] || 0) / f.n * 100);
    let x = barX;
    return (
      <g key={label}>
        <text x={pad} y={by + 3} fontSize="11.5" fontWeight="700" fill={C.sub}>{label}</text>
        <rect x={barX} y={by - 6} width={barW} height={12} rx={3} fill={C.grid} />
        {OUTCOME.map(([k, c]) => { const w = (f.buckets[k] || 0) / f.n * barW; const s = w > 0 ? <rect key={k} x={x} y={by - 6} width={w} height={12} fill={c} /> : null; x += w; return s; })}
        <text x={pad + cw} y={by + 3} textAnchor="end" fontSize="11" fontWeight="600" fill={C.ink}>{pct}% решено</text>
      </g>
    );
  };
  // колонка профиля навыков: тег + мини-полоса балла
  const skillBox = (bx, title, cols, profile, col) => (
    <g>
      <rect x={bx} y={profBoxTop} width={bw} height={profBoxH} rx={12} fill={C.head} stroke={C.grid} />
      <text x={bx + 16} y={profBoxTop + 25} fontSize="12.5" fontWeight="700" fill={C.ink}>{title}</text>
      {cols.map((c, i) => {
        const v = profile?.[c]?.value, label = tagLabels[c] || c;
        const ry = profBoxTop + 48 + i * 22, lw = 120, vw = 26, barX = bx + 16 + lw, barW = bw - 32 - lw - vw - 6;
        return (
          <g key={c}>
            <text x={bx + 16} y={ry + 3} fontSize="10.5" fill={C.sub}>{clip(label, 17)}</text>
            {v == null
              ? <text x={bx + bw - 16} y={ry + 3} textAnchor="end" fontSize="10" fill={C.muted}>—</text>
              : (<>
                <rect x={barX} y={ry - 2} width={barW} height={5} rx={2.5} fill={C.grid} />
                <rect x={barX} y={ry - 2} width={Math.max(2, barW * (v / 10))} height={5} rx={2.5} fill={col} />
                <text x={bx + bw - 16} y={ry + 3} textAnchor="end" fontSize="10.5" fontWeight="600" fill={C.ink}>{v.toFixed(1)}</text>
              </>)}
          </g>
        );
      })}
    </g>
  );

  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ ...svgStyle, background: C.bg }} fontFamily={FONT}>
      <rect x={0} y={0} width={W} height={4} fill={C.brand} />
      <text x={pad} y={32} fontSize="10.5" fontWeight="700" letterSpacing="0.08em" fill={C.muted}>PRISM · РАЗБОР ОЦЕНКИ · L1</text>
      <text x={W - pad} y={32} textAnchor="end" fontSize="12" fontWeight="700" fill={C.brand}>prism</text>
      <LogoGlyph x={pad} cy={70} size={44} m={model} C={C} />
      <text x={pad + 58} y={64} fontSize="22" fontWeight="700" fill={C.ink}>{model.name}</text>
      <text x={pad + 58} y={83} fontSize="12" fill={C.muted}>{model.family || model.vendor || ''}</text>
      {metaLine && <text x={pad + 58} y={101} fontSize="11" fill={C.sub}>{metaLine}</text>}
      <text x={W - pad} y={66} textAnchor="end"><tspan fontSize="32" fontWeight="700" fill={C.ink}>{ins.qOverall != null ? ins.qOverall.toFixed(2) : '—'}</tspan><tspan fontSize="12" fill={C.muted} dx="2">/10</tspan></text>
      <text x={W - pad} y={86} textAnchor="end" fontSize="11" fontWeight="600" fill={C.brand}>{rankTxt} из {ins.total} · по Q</text>

      <text x={pad} y={leadY} fontSize="14" fill={C.sub}>{vd.lead}</text>

      {pluses.length > 0 && (
        <>
          <text x={pad} y={plusHeadY} fontSize="10" fontWeight="700" letterSpacing="0.06em" fill={C.ok}>СИЛЬНЫЕ СТОРОНЫ</text>
          {pluses.map((p, i) => (
            <text key={p.ax} x={pad} y={plusYs[i]} fontSize="12.5">
              <tspan fill={AXIS[p.ax]} fontWeight="700">+ {p.ax}</tspan>
              <tspan fill={C.ink} fontWeight="700" dx="6">{p.name}</tspan>
              <tspan fill={C.sub} dx="4">— {clip(p.text, 82)}</tspan>
            </text>
          ))}
        </>
      )}

      {catBox(pad, 'Категория A · алгоритмика', 'чистый код без базы', model.qA, model.A?.solved, axA, model.A)}
      {catBox(pad + bw + 16, 'Категория B · платформа', 'запросы, регистры, метаданные 1С', model.qB, model.B?.solved, axB, model.B)}

      <line x1={pad} y1={econTop - 16} x2={W - pad} y2={econTop - 16} stroke={C.grid} />
      {econ.map(([label, val], i) => (
        <g key={label}>
          <text x={pad + ew * i + ew / 2} y={econTop + 6} textAnchor="middle" fontSize="10" fontWeight="700" letterSpacing="0.05em" fill={C.muted}>{label.toUpperCase()}</text>
          <text x={pad + ew * i + ew / 2} y={econTop + 30} textAnchor="middle" fontSize="17" fontWeight="700" fill={C.ink}>{val}</text>
        </g>
      ))}

      {cmp.length > 0 && <line x1={pad} y1={cmpTop - 16} x2={W - pad} y2={cmpTop - 16} stroke={C.grid} />}
      {cmp.map(([label, col, val], i) => (
        <text key={label} x={pad} y={cmpTop + i * 22} fontSize="12">
          <tspan fill={col} fontWeight="700" letterSpacing="0.04em">{label}</tspan>
          <tspan fill={C.sub} dx="8">{clip(val, 96)}</tspan>
        </text>
      ))}

      {hasFun && (<>
        <line x1={pad} y1={funHeadY - 14} x2={W - pad} y2={funHeadY - 14} stroke={C.grid} />
        <text x={pad} y={funHeadY} fontSize="11" fontWeight="700" letterSpacing="0.05em" fill={C.ink}>ГДЕ ЛОМАЕТСЯ</text>
        {OUTCOME.map(([k, c], i) => (
          <g key={k}>
            <rect x={pad + i * (cw / 4)} y={funLegendY - 8} width={9} height={9} rx={2.5} fill={c} />
            <text x={pad + i * (cw / 4) + 14} y={funLegendY} fontSize="10.5" fill={C.sub}>{k}</text>
          </g>
        ))}
        {funCats.map(([label, f], i) => funRow(label, f, funRowsTop + i * funRowH))}
      </>)}

      {hasProf && (<>
        <line x1={pad} y1={profHeadY - 14} x2={W - pad} y2={profHeadY - 14} stroke={C.grid} />
        <text x={pad} y={profHeadY} fontSize="11" fontWeight="700" letterSpacing="0.05em" fill={C.ink}>ПРОФИЛЬ НАВЫКОВ<tspan fontWeight="400" fill={C.muted} dx="8">балл по видам задач</tspan></text>
        {skillBox(pad, 'Категория A · алгоритмика', colsA, model.A?.profile, AXIS.M)}
        {skillBox(pad + bw + 16, 'Категория B · платформа', colsB, model.B?.profile, AXIS.P)}
      </>)}

      <text x={W - pad} y={H - 12} textAnchor="end" fontSize="9" fill={C.muted}>{STAMP(meta)}</text>
    </svg>
  );
}

// Кнопки выгрузки инфографики модели (десктоп, как у таблиц лидерборда). SVG рисуется скрыто.
export function ModelCardExport({ model, models = [], meta = {}, tagLabels = {} }) {
  const theme = useTheme();
  const C = THEME[theme];
  const isMobile = useIsMobile();
  const ref = React.useRef(null);
  if (isMobile || !model) return null; // картинку скачивают с десктопа
  const ins = buildInsights(model, models, tagLabels);
  const name = `prism_model_${model.id}`;
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>скачать:</span>
      <Btn onClick={() => ref.current && exportSvg(ref.current, name)}>↓ SVG</Btn>
      <Btn onClick={() => ref.current && exportPng(ref.current, name, C.bg)}>↓ PNG</Btn>
      <div style={{ position: 'absolute', left: -99999, top: 0, width: 820, pointerEvents: 'none' }} aria-hidden="true">
        <ModelCardSvg svgRef={ref} model={model} ins={ins} meta={meta} C={C} />
      </div>
    </div>
  );
}
