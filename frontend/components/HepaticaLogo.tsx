"use client";

import { useId } from "react";

type HepaticaLogoProps = {
  size?: number;
  className?: string;
};

export function HepaticaLogo({ size = 52, className = "" }: HepaticaLogoProps) {
  const id = useId().replace(/:/g, "");
  const bgId = `hepatica-bg-${id}`;
  const shapeId = `hepatica-shape-${id}`;

  return (
    <svg
      aria-hidden="true"
      className={className}
      height={size}
      viewBox="0 0 64 64"
      width={size}
    >
      <defs>
        <linearGradient id={bgId} x1="8" x2="56" y1="6" y2="58">
          <stop offset="0%" stopColor="#0c6f84" />
          <stop offset="100%" stopColor="#164d73" />
        </linearGradient>
        <linearGradient id={shapeId} x1="19" x2="48" y1="18" y2="45">
          <stop offset="0%" stopColor="#f8fdff" />
          <stop offset="100%" stopColor="#dcecf6" />
        </linearGradient>
      </defs>

      <rect fill={`url(#${bgId})`} height="60" rx="16" width="60" x="2" y="2" />
      <path
        d="M17.5 34C17.5 24.4 25.3 16.6 34.9 16.6H46.5V27.5C46.5 37.4 38.4 45.5 28.5 45.5H17.5V34Z"
        fill={`url(#${shapeId})`}
      />
      <path d="M24 31.4H34" fill="none" stroke="#0f5b73" strokeLinecap="round" strokeWidth="2.6" />
      <path d="M29 26.4V36.4" fill="none" stroke="#0f5b73" strokeLinecap="round" strokeWidth="2.6" />
      <path
        d="M33.5 25.5C36.9 25.5 39.6 28.2 39.6 31.6C39.6 35.2 36.7 38.1 33.1 38.1"
        fill="none"
        stroke="#0f5b73"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <circle cx="48" cy="17" fill="#8ad9cf" r="3.4" />
    </svg>
  );
}
