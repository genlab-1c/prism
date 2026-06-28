import React from 'react';

/** Small static label tag (mono). For task ids, categories, model families. */
export function Tag({ children, color = 'neutral', style = {}, ...rest }) {
  const map = {
    neutral: { fg: 'var(--ink-300)', line: 'var(--line)' },
    s: { fg: 'var(--axis-s)', line: 'var(--axis-s-line)' },
    m: { fg: 'var(--axis-m)', line: 'var(--axis-m-line)' },
    o: { fg: 'var(--axis-o)', line: 'var(--axis-o-line)' },
    p: { fg: 'var(--axis-p)', line: 'var(--axis-p-line)' },
  };
  const c = map[color] || map.neutral;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 500,
      letterSpacing: '0.02em', color: c.fg,
      border: `1px solid ${c.line}`, borderRadius: 'var(--radius-xs)',
      padding: '2px 7px', background: 'var(--chip-bg)',
      ...style,
    }} {...rest}>{children}</span>
  );
}
