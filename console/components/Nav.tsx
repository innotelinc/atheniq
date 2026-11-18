"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { StaffRole } from "@/lib/staff-policy";

const GROUPS: {
  label: string;
  items: { href: string; label: string; icon: React.ReactNode; roles?: StaffRole[] }[];
}[] = [
  {
    label: "School",
    items: [
      {
        href: "/",
        label: "Dashboard",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="9" rx="1.5" />
            <rect x="14" y="3" width="7" height="5" rx="1.5" />
            <rect x="14" y="12" width="7" height="9" rx="1.5" />
            <rect x="3" y="16" width="7" height="5" rx="1.5" />
          </svg>
        ),
      },
      {
        href: "/programs",
        label: "Degrees & programs",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 7l9-4 9 4-9 4-9-4z" />
            <path d="M6 10v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5" />
          </svg>
        ),
      },
    ],
  },
  {
    label: "Teach",
    items: [
      {
        href: "/admissions",
        label: "Admissions",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 3h9l4 4v14H6z" />
            <path d="M14 3v5h5" />
            <path d="M9 13h6M9 17h4" />
          </svg>
        ),
      },
      {
        href: "/courses",
        label: "Courses",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5z" />
            <path d="M4 5.5v15" />
          </svg>
        ),
      },
      {
        href: "/generate",
        label: "Course studio",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
            <circle cx="12" cy="12" r="3.2" />
          </svg>
        ),
      },
    ],
  },
  {
    label: "Award",
    items: [
      {
        href: "/credentials",
        label: "Credentials",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="9" r="5" />
            <path d="M8.5 13.5L7 22l5-2.2L17 22l-1.5-8.5" />
          </svg>
        ),
      },
      {
        href: "/verify",
        label: "Verification",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 3l7 3v6c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3z" />
            <path d="M9 12l2 2 4-4" />
          </svg>
        ),
      },
    ],
  },
  {
    label: "Platform",
    items: [
      {
        href: "/security",
        label: "Security",
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="4" y="10" width="16" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 018 0v3" />
          </svg>
        ),
      },
      {
        href: "/website",
        label: "Website",
        roles: ["registrar"],
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="9" />
            <path d="M3 12h18M12 3c2.6 2.4 4 5.6 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.6-4-9s1.4-6.6 4-9z" />
          </svg>
        ),
      },
      {
        href: "/integrations",
        label: "Integrations",
        roles: ["registrar"],
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 3v4M15 3v4M6 7h12v5a6 6 0 01-12 0V7z" />
            <path d="M12 18v3" />
          </svg>
        ),
      },
      {
        href: "/health",
        label: "Health",
        roles: ["registrar"],
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 12h4l2.5-6 4 12L16 12h5" />
          </svg>
        ),
      },
      {
        href: "/staff",
        label: "Staff",
        roles: ["registrar"],
        icon: (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="9" cy="8" r="3.2" />
            <path d="M3.5 20c0-3.2 2.5-5.5 5.5-5.5s5.5 2.3 5.5 5.5" />
            <path d="M16 5.2a3 3 0 010 5.6M17.5 20c0-2.4-.9-4.2-2.4-5.3" />
          </svg>
        ),
      },
    ],
  },
];

export function Nav({ role }: { role?: StaffRole }) {
  const pathname = usePathname() || "/";
  return (
    <nav className="nav">
      {GROUPS.map((group) => (
        <div className="nav-group" key={group.label}>
          <span className="nav-label">{group.label}</span>
          {group.items
            .filter((item) => !item.roles || (role ? item.roles.includes(role) : false))
            .map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-link${active ? " active" : ""}`}
              >
                {item.icon}
                {item.label}
              </Link>
            );
            })}
        </div>
      ))}
    </nav>
  );
}
