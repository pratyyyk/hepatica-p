"use client";

import { useEffect, useState } from "react";

const KEY = "hp_active_patient_id";
const CHANGE_EVENT = "hp:active-patient-changed";

export function getActivePatientId(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(KEY) || "";
}

function emitActivePatientChange() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function setActivePatientId(id: string) {
  if (typeof window === "undefined") return;
  if (!id) {
    window.localStorage.removeItem(KEY);
    emitActivePatientChange();
    return;
  }
  window.localStorage.setItem(KEY, id);
  emitActivePatientChange();
}

export function useActivePatientId() {
  const [activePatientId, setActive] = useState<string>(() => getActivePatientId());

  useEffect(() => {
    function syncFromStorage() {
      setActive(getActivePatientId());
    }

    function onStorage(e: StorageEvent) {
      if (e.key === KEY) {
        syncFromStorage();
      }
    }

    window.addEventListener("storage", onStorage);
    window.addEventListener(CHANGE_EVENT, syncFromStorage);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(CHANGE_EVENT, syncFromStorage);
    };
  }, []);

  function update(id: string) {
    setActivePatientId(id);
    setActive(getActivePatientId());
  }

  return { activePatientId, setActivePatientId: update };
}
