export class HttpError extends Error {
  readonly status: number;
  readonly url: string;

  constructor(url: string, status: number, message: string) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
    this.url = url;
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * Minimal typed JSON GET helper. Every backend call in the dashboard goes
 * through here so timeouts, non-2xx handling and error text stay consistent.
 */
export async function getJson<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { signal, timeoutMs = 8000 } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    const text = await response.text();
    if (!response.ok) {
      throw new HttpError(url, response.status, `${response.status} ${response.statusText}${text ? ` - ${truncate(text, 180)}` : ''}`);
    }
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new HttpError(url, response.status, 'Response was not valid JSON');
    }
  } catch (error) {
    if (error instanceof HttpError) throw error;
    if ((error as Error).name === 'AbortError') {
      throw new HttpError(url, 0, `Request timed out after ${timeoutMs} ms`);
    }
    throw new HttpError(url, 0, `Unreachable: ${(error as Error).message || 'network error'}`);
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

/** POST JSON (used only for the scheduler `POST /decision` probe). */
export async function postJson<T>(url: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  const { signal, timeoutMs = 10000 } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const text = await response.text();
    if (!response.ok) {
      let detail = text;
      try {
        const parsed = JSON.parse(text) as { detail?: string };
        if (parsed?.detail) detail = parsed.detail;
      } catch {
        /* keep raw text */
      }
      throw new HttpError(url, response.status, detail || `${response.status} ${response.statusText}`);
    }
    return JSON.parse(text) as T;
  } catch (error) {
    if (error instanceof HttpError) throw error;
    if ((error as Error).name === 'AbortError') {
      throw new HttpError(url, 0, `Request timed out after ${timeoutMs} ms`);
    }
    throw new HttpError(url, 0, `Unreachable: ${(error as Error).message || 'network error'}`);
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}
