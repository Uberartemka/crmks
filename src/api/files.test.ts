import { describe, it, expect } from 'vitest'
import { filesApi } from './files'

describe('filesApi', () => {
  it('url(id) builds the correct download path', () => {
    expect(filesApi.url(42)).toBe('/api/files/42')
  })

  it('thumbnailUrl(id) builds the correct thumbnail path', () => {
    expect(filesApi.thumbnailUrl(42)).toBe('/api/files/42/thumbnail')
  })
})
