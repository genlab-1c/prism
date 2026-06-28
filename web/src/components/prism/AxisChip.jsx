import React from 'react';

const AXES = {
  S: { color: 'var(--axis-s)', soft: 'var(--axis-s-soft)', line: 'var(--axis-s-line)', label: 'Синтаксис' },
  M: { color: 'var(--axis-m)', soft: 'var(--axis-m-soft)', line: 'var(--axis-m-line)', label: 'Смысл' },
  O: { color: 'var(--axis-o)', soft: 'var(--axis-o-soft)', line: 'var(--axis-o-line)', label: 'Оптимальность' },
  P: { color: 'var(--axis-p)', soft: 'var(--axis-p-soft)', line: 'var(--axis-p-line)', label: 'Платформа' },
};

/**
 * One of the four SMOP axes as a chip. The axis letter (mono) is the icon.
 * `showLabel` adds the Russian name; `solid` fills the letter disc.
 */
export function AxisChip({ axis = 'S', showLabel = true, size = 'md', style = {}, ...rest }) {
  const a = AXES[axis] || AXES.S;
  const dims = size === 'sm'
    ? { disc: 20, font: 12, pad: '4px 12px 4px 5px', gap: 7 }
    : { disc: 26, font: 15, pad: '6px 16px 6px 6px', gap: 9 };

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: dims.gap,
      padding: showLabel ? dims.pad : '4px',
      borderRadius: 'var(--radius-pill)',
      background: a.soft, border: `1px solid ${a.line}`,
      color: a.color, fontFamily: 'var(--font-mono)', fontWeight: 600,
      fontSize: size === 'sm' ? '12px' : '13px', whiteSpace: 'nowrap',
      ...style,
    }} {...rest}>
      <span style={{
        width: dims.disc, height: dims.disc, flex: 'none',
        borderRadius: '50%', background: a.color, color: 'var(--brand-ink)',
        display: 'grid', placeItems: 'center', fontSize: dims.font, fontWeight: 700,
      }}>{axis}</span>
      {showLabel && a.label}
    </span>
  );
}

export { AXES };
