"use client";

import { ReactNode } from "react";

import { SessionProvider } from "@/lib/session";

export default function Providers({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}

