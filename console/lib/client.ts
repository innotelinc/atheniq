export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  [key: string]: unknown;
}

export async function api<T>(url: string, init?: RequestInit): Promise<ApiResult<T>> {
  try {
    const response = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
    const text = await response.text();
    const parsed = text ? (JSON.parse(text) as ApiResult<T>) : ({ ok: response.ok } as ApiResult<T>);
    if (!response.ok && !parsed.error) {
      parsed.error = `Request failed with HTTP ${response.status}.`;
    }
    return parsed;
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}
