/* PRISM web — общая шапка (островок на каждой странице).
   Сама управляет темой (dark-first, как в DS); навигация — настоящими ссылками
   (страницы сайта раздельные), активный пункт приходит пропсом `active`. */
import React from 'react';
import { Icon } from './chrome/Chrome.jsx';

const BASE = import.meta.env.BASE_URL;
const NAV = [
  { key: 'leaderboard', label: 'лидерборд', href: BASE },
  { key: 'methodology', label: 'методология', href: `${BASE}methodology` },
  { key: 'tasks', label: 'задачи', href: `${BASE}tasks` },
  { key: 'docs', label: 'документация', href: `${BASE}docs` },
];

function NavLink({ label, href, active }) {
  const [hover, setHover] = React.useState(false);
  return (
    <a href={href} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        textDecoration: 'none', fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: active ? 600 : 500,
        color: active ? 'var(--ink-100)' : (hover ? 'var(--ink-200)' : 'var(--ink-400)'),
        padding: '21px 2px', position: 'relative', letterSpacing: '0.005em',
        transition: 'color var(--dur-fast) var(--ease)',
      }}>
      {label}
      {active && <span style={{ position: 'absolute', left: -2, right: -2, bottom: -1, height: 2, background: 'var(--brand)' }} />}
    </a>
  );
}

function ThemeToggle({ theme, onToggle }) {
  const [hover, setHover] = React.useState(false);
  const light = theme === 'light';
  return (
    <button onClick={onToggle} title={light ? 'Тёмная тема' : 'Светлая тема'} aria-label="Сменить тему"
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        width: 32, height: 32, display: 'grid', placeItems: 'center', cursor: 'pointer',
        borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-strong)',
        background: hover ? 'var(--surface-raised)' : 'var(--surface)',
        color: 'var(--ink-200)', transition: 'background var(--dur-fast) var(--ease)',
      }}>
      <Icon name={light ? 'moon' : 'sun'} size={16} />
    </button>
  );
}

function StarButton() {
  const [hover, setHover] = React.useState(false);
  return (
    <a href="https://github.com/genlab-1c/prism" target="_blank" rel="noreferrer"
      style={{ display: 'inline-flex', alignItems: 'stretch', borderRadius: 'var(--radius-sm)', overflow: 'hidden', border: '1px solid var(--border-strong)', textDecoration: 'none' }}>
      <span onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 7, padding: '0 11px', height: 30,
          background: hover ? 'var(--navy-600)' : 'var(--surface-raised)', color: 'var(--ink-100)',
          fontFamily: 'var(--font-mono)', fontSize: 12.5, fontWeight: 500, transition: 'background var(--dur-fast) var(--ease)',
        }}>
        <span style={{ color: 'var(--one-c)' }}><Icon name="star" size={14} /></span>Star
      </span>
    </a>
  );
}

export default function SiteHeader({ active = 'leaderboard', version = '' }) {
  const [theme, setTheme] = React.useState(
    () => (typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme')) || 'dark',
  );
  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light';
    setTheme(next);
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('prism-theme', next); } catch (e) {}
  };
  const logo = `${BASE}assets/${theme === 'light' ? 'locklight' : 'lockdark'}.png`;

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20,
      background: 'var(--surface-translucent)', backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid var(--line)',
    }}>
      <div style={{ maxWidth: 'var(--container)', margin: '0 auto', padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <a href={BASE} style={{ display: 'flex', alignItems: 'center' }}>
            <img src={logo} alt="PRISM" style={{ height: 26, width: 'auto', display: 'block' }} />
          </a>
          <span style={{ color: 'var(--line)', fontSize: 18 }}>/</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--ink-400)' }}>
            <span style={{ color: 'var(--ink-300)' }}>genlab-1c</span><span> / </span><span style={{ color: 'var(--ink-200)' }}>prism</span>
          </span>
        </div>
        <nav style={{ display: 'flex', gap: 24, alignSelf: 'stretch', alignItems: 'center' }}>
          {NAV.map((n) => <NavLink key={n.key} label={n.label} href={n.href} active={active === n.key} />)}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>v{version || '—'}</span>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <StarButton />
        </div>
      </div>
    </header>
  );
}
