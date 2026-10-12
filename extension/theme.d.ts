export type Theme = 'light' | 'dark';
export function resolveTheme(preference: unknown, systemDark: boolean): Theme;
export function applyTheme(theme: Theme): void;
