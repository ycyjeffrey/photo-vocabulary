export function resolveTheme(preference, systemDark) {
  return preference === 'light' || preference === 'dark' ? preference : systemDark ? 'dark' : 'light';
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#0a092d' : '#4255ff');
}
