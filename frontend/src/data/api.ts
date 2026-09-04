type CacheEntry<T> = {
  value?: T
  expiresAt: number
  inFlight?: Promise<T>
}

const cache = new Map<string, CacheEntry<unknown>>()

export type QueryOptions = {
  ttlMs?: number
  force?: boolean
}

export function invalidateQuery(key: string) {
  cache.delete(key)
}

export function clearQueryCache() {
  cache.clear()
}

export function apiQuery<T>(key: string, url: string, options: QueryOptions = {}): Promise<T> {
  const ttlMs = options.ttlMs ?? 15_000
  const now = Date.now()
  const existing = cache.get(key) as CacheEntry<T> | undefined

  if (!options.force && existing?.value !== undefined && existing.expiresAt > now) {
    return Promise.resolve(existing.value)
  }
  if (existing?.inFlight) {
    return existing.inFlight
  }

  const inFlight = fetch(url, { headers: { Accept: 'application/json' } })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Request failed: ${response.status}`)
      return response.json() as Promise<T>
    })
    .then((value) => {
      cache.set(key, { value, expiresAt: Date.now() + ttlMs })
      return value
    })
    .catch((error) => {
      const current = cache.get(key) as CacheEntry<T> | undefined
      if (current?.inFlight === inFlight) cache.delete(key)
      throw error
    })

  cache.set(key, {
    value: existing?.value,
    expiresAt: existing?.expiresAt ?? 0,
    inFlight,
  })
  return inFlight
}

export async function apiMutation<T = unknown>(
  url: string,
  method: 'POST' | 'PATCH' | 'DELETE',
  body?: unknown,
): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: body === undefined
      ? { Accept: 'application/json' }
      : { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`
    try {
      const payload = await response.json() as { detail?: string }
      if (payload.detail) detail = payload.detail
    } catch {
      // Keep the status-only error when the response is not JSON.
    }
    throw new Error(detail)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
