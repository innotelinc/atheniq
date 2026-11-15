import Link from "next/link";
import type { ReactNode } from "react";
import { cx, humanStatus, statusTone } from "@/lib/format";

export function Card({
  title,
  subtitle,
  action,
  children,
  footer,
  className,
  accent,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  accent?: boolean;
}) {
  return (
    <section className={cx("card", accent && "accent", className)}>
      {(title || action) && (
        <header className="card-head">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {action && <div className="row">{action}</div>}
        </header>
      )}
      {children}
      {footer && <footer className="card-foot">{footer}</footer>}
    </section>
  );
}

export function Stat({
  label,
  value,
  hint,
  unit,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  unit?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {value}
        {unit && <small> {unit}</small>}
      </div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Badge({ status, label }: { status: string; label?: string }) {
  return <span className={cx("chip", statusTone(status))}>{label ?? humanStatus(status)}</span>;
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <span style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
    </div>
  );
}

export function Empty({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{body}</p>
      {action && <div className="row" style={{ justifyContent: "center", marginTop: 14 }}>{action}</div>}
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {subtitle && <div className="page-sub">{subtitle}</div>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </div>
  );
}

export function Banner({
  tone,
  title,
  children,
}: {
  tone?: "warn" | "bad" | "ok";
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx("banner", tone)}>
      <div>
        {title && <div className="banner-title">{title}</div>}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function Crumbs({ items }: { items: { href?: string; label: string }[] }) {
  return (
    <div className="crumbs">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`} className="row" style={{ gap: 8 }}>
          {i > 0 && <span aria-hidden="true">/</span>}
          {item.href ? <Link href={item.href}>{item.label}</Link> : <span>{item.label}</span>}
        </span>
      ))}
    </div>
  );
}

export function Topbar({ children }: { children: ReactNode }) {
  return <div className="topbar">{children}</div>;
}
