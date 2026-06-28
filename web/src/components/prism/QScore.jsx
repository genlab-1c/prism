import React from 'react';

/**
 * The Q score — mean across axes, the "one number at a glance". Big mono
 * numeral with an eyebrow. Secondary to the vector by design, so the
 * label always reminds that Q is a summary.
 */
export function QScore({ value = 0, size = 'md', label = 'Q · общий балл', style = {}, ...rest }) {
  const sizes = { sm: 28, md: 44, lg: 64 };
  const fs = sizes[size] || sizes.md;
  const v = value.toFixed(2);
  const [whole, dec] = v.split('.');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, ...style }} {...rest}>
      <span style={{
        fontSize: '10.5px', letterSpacing: '0.08em', textTransform: 'uppercase',
        color: 'var(--ink-400)', fontWeight: 600,
      }}>{label}</span>
      <span style={{
        fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums',
        fontWeight: 700, fontSize: fs, lineHeight: 1, letterSpacing: '-0.02em',
        color: 'var(--ink-100)',
      }}>{whole}<span style={{ color: 'var(--ink-300)' }}>.{dec}</span></span>
    </div>
  );
}
