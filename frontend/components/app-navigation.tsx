"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Waves } from "lucide-react";
import { ThemeToggle } from "./theme-toggle";

const destinations = [
  ["/", "Overview"],
  ["/explore", "Explore"],
  ["/forecasts", "Forecasts"],
  ["/diagnostics", "Patterns"],
  ["/regional", "Regional & snow"],
  ["/methods", "Methods & data"],
];

function sharedDestination(path: string) {
  const current = new URLSearchParams(window.location.search);
  const shared = new URLSearchParams();
  for (const key of path === "/forecasts"
    ? ["area"]
    : ["area", "start", "end"]) {
    if (current.has(key)) shared.set(key, current.get(key)!);
  }
  return path + (shared.size ? `?${shared}` : "");
}

export function AppNavigation() {
  const path = usePathname();
  const [links, setLinks] = useState(destinations.map(([href]) => href));
  useEffect(() => {
    const update = () =>
      setLinks(destinations.map(([href]) => sharedDestination(href)));
    update();
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [path]);
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <a href="/" className="site-brand" aria-label="Norwegian energy home">
          <span className="site-mark">
            <Waves size={22} />
          </span>
          <span>
            norwegian energy
            <span className="site-subtitle">An interactive data story</span>
          </span>
        </a>
        <ThemeToggle />
        <nav aria-label="Main navigation" className="site-navigation">
          {destinations.map(([href, label], index) => (
            <a
              key={href}
              href={links[index]}
              aria-current={path === href ? "page" : undefined}
              onClick={(event) => {
                event.currentTarget.href = sharedDestination(href);
              }}
            >
              {label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}
