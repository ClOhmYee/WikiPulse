export const THEME_KEY = "wikipulse.theme";

export function readTheme() {
  try {
    return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function saveTheme(theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // The in-memory preference still works when browser storage is unavailable.
  }
}

export function applyTheme(theme, onboarding) {
  const effective = onboarding ? "dark" : theme;
  document.documentElement.dataset.theme = effective;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", effective === "light" ? "#f3f7ff" : "#050a0f");
}
