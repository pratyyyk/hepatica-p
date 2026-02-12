"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

import { useActivePatientId } from "@/lib/activePatient";
import { useSession } from "@/lib/session";
import { HepaticaLogo } from "@/components/HepaticaLogo";
import { Button, Pill } from "@/components/ui";

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link className={`navLink ${active ? "navLinkActive" : ""}`.trim()} href={href}>
      {label}
    </Link>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { session, loading, logout } = useSession();
  const { activePatientId } = useActivePatientId();
  const activePatientLabel =
    activePatientId && activePatientId.length > 16
      ? `${activePatientId.slice(0, 8)}...${activePatientId.slice(-4)}`
      : activePatientId;

  useEffect(() => {
    if (!loading && !session?.authenticated) {
      router.replace("/login");
    }
  }, [loading, router, session?.authenticated]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">
            <HepaticaLogo size={46} />
          </div>
          <div>
            <div className="brandTitle">Hepatica</div>
            <div className="brandSubtitle">Liver Risk Platform</div>
          </div>
        </div>

        <nav className="nav">
          <div className="navSectionLabel">Clinical Operations</div>
          <NavLink href="/patients" label="Patients" />
          <NavLink href="/assistant" label="Doctor Assistant" />
          <div className="navSectionLabel">Assessment Stages</div>
          <NavLink href="/assessments/stage1" label="Stage 1 Assessment" />
          <NavLink href="/assessments/stage2" label="Stage 2 Scan" />
          <NavLink href="/assessments/stage3" label="Stage 3 Monitoring" />
          <div className="navSectionLabel">Records</div>
          <NavLink href="/reports" label="Reports" />
        </nav>

        <div className="sidebarFoot">
          <div className="meta">
            <Pill tone="neutral">Role: DOCTOR</Pill>
            {activePatientId ? <Pill tone="ok">Active: {activePatientLabel}</Pill> : <Pill tone="warn">No active patient</Pill>}
          </div>
          <Button
            tone="ghost"
            onClick={() => {
              void logout();
            }}
          >
            Logout
          </Button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbarLeft">
            <div className="topbarTitle">Clinical Liver Assessment Workspace</div>
            <div className="topbarSub">
              Review Stage 1 clinical scores, Stage 2 imaging findings, and Stage 3 monitoring trends.
            </div>
            <div className="topbarKpis">
              <span>Stage 1 Clinical</span>
              <span>Stage 2 Imaging</span>
              <span>Stage 3 Monitoring</span>
            </div>
          </div>
          <div className="topbarRight">
            {session?.email ? <Pill tone="neutral">{session.email}</Pill> : <Pill tone="warn">Signed out</Pill>}
          </div>
        </header>

        <div className="content">{children}</div>
      </div>
    </div>
  );
}
