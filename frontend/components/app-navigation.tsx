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
  Menu,
  X,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { ThemeToggle } from "./theme-toggle";
import {
  DASHBOARD_URL_CHANGE_EVENT,
  dashboardDestination,
} from "@/lib/navigation-state";

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

export function AppNavigation() {
  const path = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [links, setLinks] = useState(destinations.map(({ href }) => href));
  useEffect(() => {
    const update = () =>
      setLinks(destinations.map(({ href }) => dashboardDestination(href)));
    update();
    window.addEventListener("popstate", update);
    window.addEventListener(DASHBOARD_URL_CHANGE_EVENT, update);
    return () => {
      window.removeEventListener("popstate", update);
      window.removeEventListener(DASHBOARD_URL_CHANGE_EVENT, update);
    };
  }, [path]);

  const activeDestination =
    destinations.find(({ href }) => href === path) ?? destinations[0];
  const activeGroup =
    navigationGroups.find((group) =>
      group.destinations.some(({ href }) => href === path),
    )?.label ?? "Workspace";

  return (
    <>
      <aside
        className={`site-sidebar${menuOpen ? " navigation-open" : ""}`}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setMenuOpen(false);
            event.currentTarget
              .querySelector<HTMLButtonElement>(".mobile-menu-toggle")
              ?.focus();
          }
        }}
      >
        <div className="site-brand-row">
          <a
            href={links[0]}
            onClick={(event) => {
              event.currentTarget.href = dashboardDestination("/");
            }}
            className="site-brand"
            aria-label="Norway Energy Atlas home"
          >
            <span className="site-mark">
              <Waves size={20} strokeWidth={1.5} aria-hidden="true" />
            </span>
            <span>
              Norway Energy Atlas
              <span className="site-subtitle">Production, demand &amp; weather</span>
            </span>
          </a>

          <button
            type="button"
            className="mobile-menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? (
              <X size={18} aria-hidden="true" />
            ) : (
              <Menu size={18} aria-hidden="true" />
            )}{" "}
            Menu
          </button>
        </div>
        <nav
          id="main-navigation"
          aria-label="Main navigation"
          className="site-navigation"
        >
          {navigationGroups.map((group) => (
            <div className="site-navigation-group" key={group.label}>

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
                        event.currentTarget.href = dashboardDestination(href);
                        setMenuOpen(false);
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
        <a className="site-source-link" href="https://github.com/TaoM29/norwegian-energy-dashboard">View source ↗</a>
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
