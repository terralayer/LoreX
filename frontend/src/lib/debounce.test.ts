import { afterEach, describe, expect, it, vi } from 'vitest'

import { debounce } from './debounce'

afterEach(() => {
  vi.useRealTimers()
})

describe('debounce', () => {
  it('collapses rapid calls into the latest invocation', () => {
    vi.useFakeTimers()
    const calls: string[] = []
    const run = debounce((value: string) => calls.push(value), 250)

    run('p')
    run('pr')
    run('project')
    vi.advanceTimersByTime(249)
    expect(calls).toEqual([])
    vi.advanceTimersByTime(1)
    expect(calls).toEqual(['project'])
  })

  it('can cancel a pending invocation', () => {
    vi.useFakeTimers()
    const calls: string[] = []
    const run = debounce((value: string) => calls.push(value), 250)

    run('cancelled')
    run.cancel()
    vi.advanceTimersByTime(500)
    expect(calls).toEqual([])
  })
})
