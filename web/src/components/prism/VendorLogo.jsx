/* PRISM web — логотип вендора модели. Реальные бренд-иконки из simple-icons
   (Claude, Gemini, DeepSeek, Qwen, Xiaomi, Yandex). Для вендоров без иконки
   (OpenAI, Zhipu, Sber) — откат на монограмму Avatar (инициалы в цвете). */
import React from 'react';
import { siClaude, siGooglegemini, siDeepseek, siQwen, siXiaomi, siYandexcloud } from 'simple-icons';
import { Avatar } from '../core/Avatar.jsx';

// вендор (как в models.yaml) → бренд-иконка
const ICONS = {
  anthropic: siClaude,
  google: siGooglegemini,
  deepseek: siDeepseek,
  alibaba: siQwen,
  xiaomi: siXiaomi,
  yandex: siYandexcloud,
};

export function VendorLogo({ vendor, name = '?', size = 32, style = {} }) {
  const icon = ICONS[vendor];
  if (!icon) return <Avatar name={name} size={size} style={style} />; // OpenAI/Zhipu/Sber и пр.
  const hex = `#${icon.hex}`;
  return (
    <span
      title={icon.title}
      style={{
        width: size, height: size, flex: 'none', display: 'inline-grid', placeItems: 'center',
        borderRadius: 'var(--radius-md)', background: `${hex}1f`, border: '1px solid var(--line)', ...style,
      }}>
      <svg width={Math.round(size * 0.56)} height={Math.round(size * 0.56)} viewBox="0 0 24 24" fill={hex} aria-hidden="true">
        <path d={icon.path} />
      </svg>
    </span>
  );
}
