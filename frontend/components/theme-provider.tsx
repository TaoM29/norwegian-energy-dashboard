"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = Exclude<ThemeMode, "system">;

export const THEME_STORAGE_KEY = "energy-dashboard-theme";

type ThemeContextValue = {
  theme: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function isThemeMode(value: string | null): value is ThemeMode {
  return value === "light" || value === "dark" || value === "system";
}

function systemTheme(query: MediaQueryList): ResolvedTheme {
  return query.matches ? "dark" : "light";
}

function applyDocumentTheme(resolved: ResolvedTheme, mode: ThemeMode) {
  const root = document.documentElement;
  root.classList.add("theme-changing");
  root.dataset.theme = resolved;
  root.dataset.themeMode = mode;
  root.style.colorScheme = resolved;
  void root.offsetHeight;
  requestAnimationFrame(() =>
    requestAnimationFrame(() => root.classList.remove("theme-changing")),
  );
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");

    const applyTheme = (mode: ThemeMode) => {
      const resolved = mode === "system" ? systemTheme(query) : mode;
      applyDocumentTheme(resolved, mode);
      setResolvedTheme(resolved);
    };

    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    } catch {
      // System preference remains the default when storage is unavailable.
    }
    const initialTheme = isThemeMode(stored) ? stored : "system";
    setThemeState(initialTheme);
    applyTheme(initialTheme);

    const handleSystemChange = () => {
      if (document.documentElement.dataset.themeMode === "system") {
        applyTheme("system");
      }
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      const nextTheme = isThemeMode(event.newValue) ? event.newValue : "system";
      setThemeState(nextTheme);
      applyTheme(nextTheme);
    };

    query.addEventListener("change", handleSystemChange);
    window.addEventListener("storage", handleStorage);
    return () => {
      query.removeEventListener("change", handleSystemChange);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      resolvedTheme,
      setTheme: (nextTheme) => {
        setThemeState(nextTheme);
        try {
          window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
        } catch {
          // The selected theme still applies when storage is unavailable.
        }
        const query = window.matchMedia("(prefers-color-scheme: dark)");
        const resolved =
          nextTheme === "system" ? systemTheme(query) : nextTheme;
        applyDocumentTheme(resolved, nextTheme);
        setResolvedTheme(resolved);
      },
    }),
    [resolvedTheme, theme],
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
