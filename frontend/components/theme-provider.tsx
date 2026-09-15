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

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");

    const applyTheme = (mode: ThemeMode) => {
      const resolved = mode === "system" ? systemTheme(query) : mode;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.dataset.themeMode = mode;
      document.documentElement.style.colorScheme = resolved;
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
        document.documentElement.dataset.theme = resolved;
        document.documentElement.dataset.themeMode = nextTheme;
        document.documentElement.style.colorScheme = resolved;
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
