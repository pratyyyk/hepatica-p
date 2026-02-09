"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useSession } from "@/lib/session";

export default function LandingPage() {
  const router = useRouter();
  const { loading, session } = useSession();

  useEffect(() => {
    if (loading) return;
    if (session?.authenticated) {
      router.replace("/patients");
      return;
    }
    router.replace("/login");
  }, [loading, router, session?.authenticated]);

  return (
    <main className="center">
      <div className="spinner" />
      <div className="muted">Booting console...</div>
    </main>
  );
}

