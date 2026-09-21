"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "energy-dashboard-theme";

type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function savedTheme(value: string | null): ThemeMode {
  return value === "light" ? "light" : "dark";
}

function applyDocumentTheme(theme: ThemeMode) {
  const root = document.documentElement;
  root.classList.add("theme-changing");
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  void root.offsetHeight;
  requestAnimationFrame(() =>
    requestAnimationFrame(() => root.classList.remove("theme-changing")),
  );
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>("dark");

  useEffect(() => {
    let initialTheme: ThemeMode = "dark";
    try {
      initialTheme = savedTheme(window.localStorage.getItem(THEME_STORAGE_KEY));
      // Normalize older "system" preferences to the new default.
      window.localStorage.setItem(THEME_STORAGE_KEY, initialTheme);
    } catch {
      // Dark remains the default when storage is unavailable.
    }
    setThemeState(initialTheme);
    applyDocumentTheme(initialTheme);

    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY && event.key !== null) return;
      const nextTheme = savedTheme(event.newValue);
      setThemeState(nextTheme);
      applyDocumentTheme(nextTheme);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme: (nextTheme) => {
        setThemeState(nextTheme);
        try {
          window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
        } catch {
          // The selected theme still applies when storage is unavailable.
        }
        applyDocumentTheme(nextTheme);
      },
    }),
    [theme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used within ThemeProvider");
  return value;
}
