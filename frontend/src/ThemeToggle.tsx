import { useEffect, useLayoutEffect, useState } from 'react';
import { applyTheme, resolveTheme, type Theme } from '../../extension/theme.js';

const key = 'photo-vocabulary.theme';

export function ThemeToggle() {
  const [state, setState] = useState(() => {
    const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    try {
      const saved = localStorage.getItem(key);
      return { theme: resolveTheme(saved, systemDark), chosen: saved === 'light' || saved === 'dark', error: '' };
    } catch {
      return { theme: resolveTheme(null, systemDark), chosen: false, error: '無法讀取外觀設定，暫時使用系統主題。' };
    }
  });
  useLayoutEffect(() => { applyTheme(state.theme); }, [state.theme]);
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setState(current => current.chosen ? current : {
      ...current, theme: resolveTheme(null, media.matches),
    });
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const toggle = () => {
    const next: Theme = state.theme === 'dark' ? 'light' : 'dark';
    let error = '';
    try {
      localStorage.setItem(key, next);
    } catch {
      error = '外觀已切換，但無法儲存；重新開啟後可能不會保留。';
    }
    setState({ theme: next, chosen: true, error });
  };

  return <div className="theme-control">
    <button className="theme-toggle" type="button" aria-label="深色模式"
      aria-pressed={state.theme === 'dark'} title={state.theme === 'dark' ? '切換淺色模式' : '切換深色模式'}
      onClick={toggle}>{state.theme === 'dark' ? '淺色模式' : '深色模式'}</button>
    {state.error && <span className="theme-error" role="status">{state.error}</span>}
  </div>;
}
