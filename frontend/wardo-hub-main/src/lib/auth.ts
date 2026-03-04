const DEFAULT_API_URL = "http://localhost:8001";
const API_BASE_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL;
const AUTH_DB_TARGET_KEY = "auth_db_target";

type AuthRole = string | null;

type AuthState = {
  token: string | null;
  role: AuthRole;
  email: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
};

const hasWindow = () => typeof window !== "undefined";

const base64UrlDecode = (value: string) => {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padLength = (4 - (normalized.length % 4)) % 4;
    const padded = `${normalized}${"=".repeat(padLength)}`;
    return window.atob(padded);
  } catch {
    return "";
  }
};

const decodeTokenPayload = (token: string) => {
  const parts = String(token || "").split(".");
  if (parts.length < 2) return null;
  const decoded = base64UrlDecode(parts[1]);
  if (!decoded) return null;
  try {
    return JSON.parse(decoded) as { exp?: number };
  } catch {
    return null;
  }
};

const hasStaleAuthKeys = () => {
  if (!hasWindow()) return false;
  return ["token", "role", "email", "profile"].some((key) => Boolean(localStorage.getItem(key)));
};

export const isTokenValid = (token: string | null | undefined) => {
  const normalized = String(token || "").trim();
  if (!normalized) return false;
  const payload = decodeTokenPayload(normalized);
  if (!payload || typeof payload.exp !== "number") return false;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return payload.exp > nowSeconds + 10;
};

export const clearAuthState = (preserveDbTarget = true) => {
  if (!hasWindow()) return;
  const dbTarget = preserveDbTarget ? localStorage.getItem(AUTH_DB_TARGET_KEY) : null;
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("email");
  localStorage.removeItem("profile");
  if (!preserveDbTarget) {
    localStorage.removeItem(AUTH_DB_TARGET_KEY);
    return;
  }
  if (dbTarget) {
    localStorage.setItem(AUTH_DB_TARGET_KEY, dbTarget);
  } else {
    localStorage.removeItem(AUTH_DB_TARGET_KEY);
  }
};

export const sanitizeAuthState = () => {
  if (!hasWindow()) return null;
  const token = localStorage.getItem("token");
  if (!token) {
    if (hasStaleAuthKeys()) {
      clearAuthState();
    }
    return null;
  }
  if (!isTokenValid(token)) {
    clearAuthState();
    return null;
  }
  return token;
};

export const getAuthState = (): AuthState => {
  if (!hasWindow()) {
    return {
      token: null,
      role: null,
      email: null,
      isAuthenticated: false,
      isAdmin: false,
    };
  }

  const token = localStorage.getItem("token");
  const tokenIsValid = isTokenValid(token);
  const role = tokenIsValid ? localStorage.getItem("role") : null;
  const email = tokenIsValid ? localStorage.getItem("email") : null;

  return {
    token: tokenIsValid ? token : null,
    role,
    email,
    isAuthenticated: Boolean(tokenIsValid),
    isAdmin: role === "admin",
  };
};

export const getValidToken = () => sanitizeAuthState();

export const storeAuthState = ({
  token,
  role,
  email,
}: {
  token: string;
  role: string;
  email?: string | null;
}) => {
  if (!hasWindow()) return;
  localStorage.setItem("token", token);
  localStorage.setItem("role", role);
  if (email) {
    localStorage.setItem("email", email);
  } else {
    localStorage.removeItem("email");
  }
  // Profile is user-specific cache; drop it on any new login.
  localStorage.removeItem("profile");
};

export const syncAuthDbTarget = async () => {
  if (!hasWindow()) {
    return { changed: false, current: null as string | null };
  }

  sanitizeAuthState();

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 1500);

  try {
    const response = await fetch(`${API_BASE_URL}/health/db`, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      return { changed: false, current: null as string | null };
    }

    const data = await response.json().catch(() => ({}));
    const current = typeof data?.db_target === "string" ? data.db_target : null;
    if (!current) {
      return { changed: false, current: null as string | null };
    }

    const previous = localStorage.getItem(AUTH_DB_TARGET_KEY);
    const changed = Boolean(previous && previous !== current);
    if (changed && hasStaleAuthKeys()) {
      clearAuthState();
    }

    localStorage.setItem(AUTH_DB_TARGET_KEY, current);
    return { changed, current };
  } catch {
    return { changed: false, current: null as string | null };
  } finally {
    window.clearTimeout(timer);
  }
};

