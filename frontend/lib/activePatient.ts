"use client";

import { useEffect, useState } from "react";

const KEY = "hp_active_patient_id";

export function getActivePatientId(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(KEY) || "";
}

export function setActivePatientId(id: string) {
  if (typeof window === "undefined") return;
  if (!id) {
    window.localStorage.removeItem(KEY);
    return;
  }
  window.localStorage.setItem(KEY, id);
}

export function useActivePatientId() {
  const [activePatientId, setActive] = useState<string>(() => getActivePatientId());

  useEffect(() => {
    function onStorage(e: StorageEvent) {
      if (e.key === KEY) {
        setActive(getActivePatientId());
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function update(id: string) {
    setActivePatientId(id);
    setActive(id);
  }

  return { activePatientId, setActivePatientId: update };
}

