"use client";

import { Sun, Moon } from "lucide-react";
import { useTheme, type ThemeMode } from "./theme-provider";

const options: { value: ThemeMode; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      className={`theme-toggle ${className}`.trim()}
      role="group"
      aria-label="Color theme"
    >
      {options.map(({ value, label }) => (
        <button
          className="theme-toggle__option"
          type="button"
          key={value}
          aria-label={label}
          title={`${label} theme`}
          aria-pressed={theme === value}
          onClick={() => setTheme(value)}
        >
          {value === "light" ? (
            <Sun size={15} aria-hidden="true" />
          ) : (
            <Moon size={15} aria-hidden="true" />
          )}
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
