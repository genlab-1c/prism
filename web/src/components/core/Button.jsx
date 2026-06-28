import React from 'react';

/**
 * PRISM Button — primary action is brand cyan. Calm mechanical press
 * (translateY, no scale). Variants: primary | secondary | ghost | danger.
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  iconLeft = null,
  iconRight = null,
  full = false,
  style = {},
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);

  const sizes = {
    sm: { padding: '6px 12px', fontSize: '13px', height: 32, gap: 6 },
    md: { padding: '9px 16px', fontSize: '14px', height: 40, gap: 8 },
    lg: { padding: '13px 22px', fontSize: '15px', height: 48, gap: 10 },
  };
  const s = sizes[size] || sizes.md;

  const palettes = {
    primary: {
      bg: 'var(--brand)', bgHover: 'var(--brand-strong)',
      color: 'var(--brand-ink)', border: 'transparent', fw: 600,
    },
    secondary: {
      bg: 'var(--surface-raised)', bgHover: 'var(--navy-600)',
      color: 'var(--ink-100)', border: 'var(--border-strong)', fw: 500,
    },
    ghost: {
      bg: 'transparent', bgHover: 'var(--hover-overlay)',
      color: 'var(--ink-200)', border: 'transparent', fw: 500,
    },
    danger: {
      bg: 'var(--danger-soft)', bgHover: 'rgba(248,113,113,0.22)',
      color: 'var(--danger)', border: 'var(--danger-soft)', fw: 600,
    },
  };
  const p = palettes[variant] || palettes.primary;

  return (
    <button
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setActive(false); }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        gap: s.gap, width: full ? '100%' : 'auto',
        height: s.height, padding: s.padding,
        fontFamily: 'var(--font-sans)', fontSize: s.fontSize, fontWeight: p.fw,
        lineHeight: 1, letterSpacing: '0.005em',
        color: disabled ? 'var(--ink-400)' : p.color,
        background: disabled ? 'var(--surface)' : (hover ? p.bgHover : p.bg),
        border: `1px solid ${disabled ? 'var(--line)' : p.border}`,
        borderRadius: 'var(--radius-md)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transform: active && !disabled ? 'translateY(1px)' : 'translateY(0)',
        transition: 'background var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease)',
        whiteSpace: 'nowrap', userSelect: 'none',
        opacity: disabled ? 0.6 : 1,
        ...style,
      }}
      {...rest}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
