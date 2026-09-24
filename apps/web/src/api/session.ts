import { useSyncExternalStore } from "react";

export type Me = {
  user_id: string;
  tenant_id: string;
  role: string;
  roles: string[];
  email: string | null;
  auth_method: string;
};

export type Session = {
  accessToken: string | null;
  refreshToken: string | null;
  apiKey: string | null;
  me: Me | null;
};

export const DEMO_PASSWORD = "changeme";

export const DEMO_API_KEY = "agt_demo_hr_local_docker_only_key";

export const SEEDED_USERS = [
  { email: "admin@platform.local", label: "Platform admin", role: "platform_admin", tenant: "platform" },
  { email: "user@hr.local", label: "HR app user", role: "app_user", tenant: "acme-hr" },
  { email: "user@eng.local", label: "Eng app user", role: "app_user", tenant: "acme-eng" },
  { email: "sec@hr.local", label: "HR security admin", role: "security_admin", tenant: "acme-hr" },
  { email: "view@eng.local", label: "Eng viewer", role: "viewer", tenant: "acme-eng" },
] as const;

const EMPTY: Session = { accessToken: null, refreshToken: null, apiKey: null, me: null };
const KEY = "aigw.session";
const listeners = new Set<() => void>();

function read(): Session {
  if (typeof sessionStorage === "undefined") {
    return EMPTY;
  }
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) {
      return EMPTY;
    }
    const parsed = JSON.parse(raw) as Partial<Session>;
    return {
      accessToken: parsed.accessToken ?? null,
      refreshToken: parsed.refreshToken ?? null,
      apiKey: parsed.apiKey ?? null,
      me: parsed.me ?? null,
    };
  } catch {
    return EMPTY;
  }
}

let current: Session = read();

function commit(next: Session) {
  current = next;
  if (typeof sessionStorage !== "undefined") {
    if (next.accessToken || next.refreshToken || next.apiKey || next.me) {
      sessionStorage.setItem(KEY, JSON.stringify(next));
    } else {
      sessionStorage.removeItem(KEY);
    }
  }
  listeners.forEach((listener) => listener());
}

export function getSession(): Session {
  return current;
}

export function saveSession(next: Session) {
  commit(next);
}

export function clearSession() {
  commit(EMPTY);
}

export function useSession(): Session {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => EMPTY,
  );
}

export function canChat(role: string | undefined): boolean {
  return role === "app_user" || role === "security_admin" || role === "platform_admin" || role === "service_account";
}

export function canGovern(role: string | undefined): boolean {
  return role === "security_admin" || role === "platform_admin";
}
