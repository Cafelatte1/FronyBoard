const KEY_STORAGE = "fronyboard_api_key";

export function getKey(): string | null {
  return localStorage.getItem(KEY_STORAGE);
}

export function setKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key);
}

export function clearKey(): void {
  localStorage.removeItem(KEY_STORAGE);
}

export class Unauthorized extends Error {}

export async function api<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    headers: { Authorization: `Bearer ${getKey() ?? ""}` },
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
