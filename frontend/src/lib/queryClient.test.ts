import { describe, expect, it } from 'vitest'

import { QueryClient } from './queryClient'

describe('QueryClient', () => {
  it('coalesces simultaneous same-key loads', async () => {
    let calls = 0
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    const client = new QueryClient(() => 1_000)
    const loader = async () => {
      calls += 1
      await gate
      return { value: 42 }
    }

    const first = client.get('same', loader, 10_000)
    const second = client.get('same', loader, 10_000)
    release()

    expect(await first).toEqual({ value: 42 })
    expect(await second).toEqual({ value: 42 })
    expect(calls).toBe(1)
  })

  it('serves fresh TTL entries and refetches after expiration', async () => {
    let now = 10_000
    let calls = 0
    const client = new QueryClient(() => now)
    const loader = async () => ++calls

    expect(await client.get('ttl', loader, 500)).toBe(1)
    now += 499
    expect(await client.get('ttl', loader, 500)).toBe(1)
    expect(calls).toBe(1)

    now += 2
    expect(await client.get('ttl', loader, 500)).toBe(2)
    expect(calls).toBe(2)
  })

  it('invalidates keys by prefix', async () => {
    let calls = 0
    const client = new QueryClient(() => 1_000)
    const loader = async () => ++calls

    await client.get('library:0', loader, 10_000)
    client.invalidate('library:')
    expect(await client.get('library:0', loader, 10_000)).toBe(2)
  })
})
