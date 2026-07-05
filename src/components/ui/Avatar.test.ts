import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Avatar from './Avatar.vue'

describe('Avatar', () => {
  it('renders <img> with src when provided', () => {
    const wrapper = mount(Avatar, { props: { name: 'Алиса', src: '/api/files/1', size: 40 } })
    expect(wrapper.find('img').exists()).toBe(true)
    expect(wrapper.find('img').attributes('src')).toBe('/api/files/1')
  })

  it('renders initials when no src', () => {
    const wrapper = mount(Avatar, { props: { name: 'Иван Петров', size: 40 } })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toBe('ИП')
  })

  it('deterministic color: same name → same style', () => {
    const w1 = mount(Avatar, { props: { name: 'Алиса' } })
    const w2 = mount(Avatar, { props: { name: 'Алиса' } })
    expect(w1.find('div').attributes('style')).toBe(w2.find('div').attributes('style'))
    expect(w1.find('div').attributes('style')).toContain('background-color')
  })

  it('single name → first 2 letters uppercased', () => {
    const wrapper = mount(Avatar, { props: { name: 'Admin' } })
    expect(wrapper.text()).toBe('AD')
  })
})
