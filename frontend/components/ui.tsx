"use client";

import { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Card(props: HTMLAttributes<HTMLDivElement>) {
  const { className = "", ...rest } = props;
  return <div className={`card ${className}`.trim()} {...rest} />;
}

export function CardHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="cardHeader">
      <h2 className="cardTitle">{title}</h2>
      {subtitle && <p className="cardSubtitle">{subtitle}</p>}
    </header>
  );
}

export function Button(props: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "danger" | "ghost" }) {
  const { className = "", tone = "primary", ...rest } = props;
  return <button className={`btn btn-${tone} ${className}`.trim()} {...rest} />;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="labelRow">
        <span className="label">{label}</span>
        {hint && <span className="hint">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return <input className={`input ${className}`.trim()} {...rest} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  const { className = "", ...rest } = props;
  return <select className={`input ${className}`.trim()} {...rest} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className = "", ...rest } = props;
  return <textarea className={`input ${className}`.trim()} {...rest} />;
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "warn" | "danger" }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

