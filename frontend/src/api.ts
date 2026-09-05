const TOKEN_STORAGE = "fronyboard_session";
const USER_STORAGE = "fronyboard_user";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE);
}

export function getUsername(): string | null {
  return localStorage.getItem(USER_STORAGE);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_STORAGE);
  localStorage.removeItem(USER_STORAGE);
}

export class Unauthorized extends Error {}

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (res.status === 401) throw new Error("Invalid username or password.");
  if (!res.ok) throw new Error(res.statusText);
  const body = await res.json();
  localStorage.setItem(TOKEN_STORAGE, body.token);
  localStorage.setItem(USER_STORAGE, body.username);
}

export async function logout(): Promise<void> {
  const token = getToken();
  if (token) {
    await fetch("/api/logout", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
  clearSession();
}

export async function api<T>(path: string): Promise<T> {
  return request(path, {});
}

export async function apiSend<T>(path: string, method: "POST" | "DELETE" | "PATCH", body?: unknown): Promise<T> {
  return request(path, {
    method,
    ...(body !== undefined && {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  });
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (res.status === 401) throw new Unauthorized("unauthorized");
  if (!res.ok) {
    let message = res.statusText;
    try {
      message = (await res.json()).error ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}
