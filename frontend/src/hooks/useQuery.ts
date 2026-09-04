import { useCallback, useEffect, useState } from 'react'
import { apiQuery } from '../data/api'

type QueryState<T> = {
  data: T | null
  loading: boolean
  error: string | null
}

type UseQueryOptions = {
  ttlMs?: number
  refreshMs?: number
  enabled?: boolean
}

export function useQuery<T>(key: string, url: string, options: UseQueryOptions = {}) {
  const ttlMs = options.ttlMs ?? 15_000
  const refreshMs = options.refreshMs ?? 0
  const enabled = options.enabled ?? true
  const [state, setState] = useState<QueryState<T>>({ data: null, loading: enabled, error: null })

  const load = useCallback((force = false) => {
    if (!enabled) return Promise.resolve(null)
    setState((current) => ({ ...current, loading: current.data === null, error: null }))
    return apiQuery<T>(key, url, { ttlMs, force })
      .then((data) => {
        setState({ data, loading: false, error: null })
        return data
      })
      .catch((error: unknown) => {
        setState((current) => ({
          ...current,
          loading: false,
          error: error instanceof Error ? error.message : 'Request failed',
        }))
        return null
      })
  }, [enabled, key, ttlMs, url])

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null })
      return
    }
    void load(false)
  }, [enabled, load])

  useEffect(() => {
    if (!enabled || refreshMs <= 0) return

    let timer: number | null = null
    const stop = () => {
      if (timer !== null) window.clearInterval(timer)
      timer = null
    }
    const start = () => {
      stop()
      if (document.visibilityState === 'visible') {
        timer = window.setInterval(() => void load(true), refreshMs)
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        void load(true)
        start()
      } else {
        stop()
      }
    }

    start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [enabled, load, refreshMs])

  return { ...state, refresh: () => load(true) }
}
