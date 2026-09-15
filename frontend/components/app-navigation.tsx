"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity,
  BarChart3,
  BookOpen,
  Compass,
  LayoutDashboard,
  Map,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { ThemeToggle } from "./theme-toggle";

type Destination = {
  href: string;
  label: string;
  icon: LucideIcon;
  title?: string;
};

const navigationGroups: { label: string; destinations: Destination[] }[] = [
  {
    label: "Workspace",
    destinations: [
      {
        href: "/",
        label: "Overview",
        title: "Energy overview",
        icon: LayoutDashboard,
      },
      { href: "/explore", label: "Explore", icon: Compass },
      { href: "/regional", label: "Regional", icon: Map },
    ],
  },
  {
    label: "Analysis",
    destinations: [
      { href: "/forecasts", label: "Forecasts", icon: BarChart3 },
      { href: "/diagnostics", label: "Patterns", icon: Activity },
    ],
  },
  {
    label: "Project",
    destinations: [{ href: "/methods", label: "Methods", icon: BookOpen }],
  },
];

const destinations = navigationGroups.flatMap((group) => group.destinations);

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
  const [links, setLinks] = useState(destinations.map(({ href }) => href));
  useEffect(() => {
    const update = () =>
      setLinks(destinations.map(({ href }) => sharedDestination(href)));
    update();
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [path]);

  const activeDestination =
    destinations.find(({ href }) => href === path) ?? destinations[0];
  const activeGroup =
    navigationGroups.find((group) =>
      group.destinations.some(({ href }) => href === path),
    )?.label ?? "Workspace";

  return (
    <>
      <aside className="site-sidebar">
        <a href="/" className="site-brand" aria-label="Norwegian energy home">
          <span className="site-mark">
            <Waves size={20} strokeWidth={1.5} aria-hidden="true" />
          </span>
          <span>
            norwegian energy
            <span className="site-subtitle">Data workspace</span>
          </span>
        </a>

        <nav aria-label="Main navigation" className="site-navigation">
          {navigationGroups.map((group) => (
            <div className="site-navigation-group" key={group.label}>
              <span className="site-navigation-label">{group.label}</span>
              <div className="site-navigation-links">
                {group.destinations.map(({ href, label, icon: Icon }) => {
                  const index = destinations.findIndex(
                    (destination) => destination.href === href,
                  );
                  return (
                    <a
                      key={href}
                      href={links[index]}
                      aria-current={path === href ? "page" : undefined}
                      onClick={(event) => {
                        event.currentTarget.href = sharedDestination(href);
                      }}
                    >
                      <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
                      <span>{label}</span>
                    </a>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      <header className="site-header">
        <div className="site-header-context" aria-label="Current workspace">
          <span>{activeGroup}</span>
          <span aria-hidden="true">/</span>
          <strong>{activeDestination.title ?? activeDestination.label}</strong>
        </div>
        <ThemeToggle />
      </header>
    </>
  );
}
