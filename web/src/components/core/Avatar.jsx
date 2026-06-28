import React from 'react';

/**
 * Model avatar — a rounded square badge with the model's initials over a
 * deterministic axis-tinted background. Keeps the leaderboard legible
 * without bundling vendor logos.
 */
export function Avatar({ name = '?', size = 36, style = {}, ...rest }) {
  const initials = name
    .replace(/[^A-Za-zА-Яа-я0-9 ]/g, ' ')
    .trim().split(/\s+/).slice(0, 2)
    .map(w => w[0]).join('').toUpperCase() || '?';

  const tints = [
    ['var(--axis-s)', 'var(--axis-s-soft)'],
    ['var(--axis-m)', 'var(--axis-m-soft)'],
    ['var(--axis-o)', 'var(--axis-o-soft)'],
    ['var(--axis-p)', 'var(--axis-p-soft)'],
  ];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  const [fg, bg] = tints[h % tints.length];

  return (
    <span style={{
      width: size, height: size, flex: 'none',
      display: 'inline-grid', placeItems: 'center',
      borderRadius: 'var(--radius-md)',
      background: bg, color: fg,
      border: '1px solid var(--line)',
      fontFamily: 'var(--font-mono)', fontWeight: 600,
      fontSize: Math.round(size * 0.36),
      letterSpacing: '0.01em',
      ...style,
    }} {...rest}>{initials}</span>
  );
}
