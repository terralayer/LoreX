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
