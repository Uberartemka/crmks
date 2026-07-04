import { describe, it, expect } from 'vitest'
import { useConfirm } from './useConfirm'

describe('useConfirm', () => {
  it('confirm() resolves true on resolve(true)', async () => {
    const { confirm, resolve, visible } = useConfirm()
    const p = confirm({ title: 'Test?' })
    expect(visible.value).toBe(true)
    resolve(true)
    expect(await p).toBe(true)
    expect(visible.value).toBe(false)
  })

  it('confirm() resolves false on resolve(false)', async () => {
    const { confirm, resolve } = useConfirm()
    const p = confirm({ title: 'Test?' })
    resolve(false)
    expect(await p).toBe(false)
  })

  it('parallel confirm() resolves previous as false (no hung promise)', async () => {
    const { confirm, resolve, visible } = useConfirm()
    const p1 = confirm({ title: 'First?' })
    const p2 = confirm({ title: 'Second?' })
    expect(await p1).toBe(false)
    expect(visible.value).toBe(true)
    resolve(true)
    expect(await p2).toBe(true)
  })
})
