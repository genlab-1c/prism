import React from 'react';

/**
 * Status / label pill. Tones map to PRISM's honesty marks:
 * ok (✅ рабочее), pending (⏳ ждёт), unproven (🔴 не доказано),
 * warn (⚠️), info, neutral. Dot is the icon — no emoji in chrome.
 */
export function Badge({ children, tone = 'neutral', dot = true, size = 'md', style = {}, ...rest }) {
  const tones = {
    ok:       { fg: 'var(--ok)',     bg: 'var(--ok-soft)',     line: 'rgba(52,211,153,0.35)' },
    pending:  { fg: 'var(--warn)',   bg: 'var(--warn-soft)',   line: 'rgba(251,191,36,0.35)' },
    unproven: { fg: 'var(--danger)', bg: 'var(--danger-soft)', line: 'rgba(248,113,113,0.35)' },
    warn:     { fg: 'var(--warn)',   bg: 'var(--warn-soft)',   line: 'rgba(251,191,36,0.35)' },
    info:     { fg: 'var(--info)',   bg: 'var(--axis-s-soft)', line: 'var(--axis-s-line)' },
    brand:    { fg: 'var(--brand)',  bg: 'var(--axis-m-soft)', line: 'var(--axis-m-line)' },
    neutral:  { fg: 'var(--ink-300)', bg: 'var(--chip-bg)', line: 'var(--line)' },
  };
  const t = tones[tone] || tones.neutral;
  const dims = size === 'sm'
    ? { fontSize: '11px', padding: dot ? '2px 9px 2px 7px' : '2px 9px', d: 5 }
    : { fontSize: '12px', padding: dot ? '4px 11px 4px 8px' : '4px 11px', d: 6 };

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      fontFamily: 'var(--font-sans)', fontSize: dims.fontSize, fontWeight: 600,
      letterSpacing: '0.01em', lineHeight: 1.4,
      color: t.fg, background: t.bg,
      border: `1px solid ${t.line}`, borderRadius: 'var(--radius-pill)',
      padding: dims.padding, whiteSpace: 'nowrap',
      ...style,
    }} {...rest}>
      {dot && <span style={{ width: dims.d, height: dims.d, borderRadius: '50%', background: t.fg, flex: 'none' }} />}
      {children}
    </span>
  );
}
