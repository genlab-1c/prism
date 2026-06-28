import React from 'react';

/**
 * Leaderboard rank indicator. #1 wears the prism gradient; #2–3 get a
 * brighter ring; the rest are quiet mono numerals. Rank is data, so the
 * styling escalates only at the very top — no medal emoji.
 */
export function RankBadge({ rank = 1, size = 34, style = {}, ...rest }) {
  const isTop = rank === 1;
  const isPodium = rank <= 3;
  return (
    <span style={{ position: 'relative', width: size, height: size, flex: 'none', display: 'inline-grid', placeItems: 'center', ...style }} {...rest}>
      {isTop && (
        <span style={{
          position: 'absolute', inset: 0, borderRadius: 'var(--radius-md)',
          background: 'var(--prism)', opacity: 0.18,
        }} />
      )}
      <span style={{
        position: 'absolute', inset: 0, borderRadius: 'var(--radius-md)',
        padding: 1.5,
        background: isTop ? 'var(--prism)' : (isPodium ? 'var(--border-strong)' : 'var(--line)'),
        WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
        WebkitMaskComposite: 'xor', maskComposite: 'exclude',
      }} />
      <span style={{
        fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
        fontWeight: 700, fontSize: Math.round(size * 0.42),
        color: isTop ? 'var(--ink-100)' : (isPodium ? 'var(--ink-200)' : 'var(--ink-400)'),
      }}>{rank}</span>
    </span>
  );
}
