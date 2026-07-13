import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import P115PathSelector from '@/components/P115PathSelector.vue'

describe('P115PathSelector.vue', () => {
  it('initializes with root directory', () => {
    const wrapper = mount(P115PathSelector, {
      props: {
        modelValue: true,
        api: {}
      },
      stubs: {
        VDialog: { template: '<div><slot /></div>' }
      }
    })

    expect(wrapper.vm.breadcrumbs[0].cid).toBe('0')
    expect(wrapper.vm.breadcrumbs[0].name).toBe('115云盘')
  })

  it('can go back to parent directory', async () => {
    const wrapper = mount(P115PathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    wrapper.vm.breadcrumbs = [
      { cid: '0', name: '115云盘' },
      { cid: '123', name: 'movies' }
    ]

    await wrapper.vm.goBack()

    expect(wrapper.vm.breadcrumbs.length).toBe(1)
    expect(wrapper.vm.breadcrumbs[0].cid).toBe('0')
  })

  it('emits selected event with correct values', async () => {
    const wrapper = mount(P115PathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    wrapper.vm.breadcrumbs = [
      { cid: '0', name: '115云盘' },
      { cid: '123', name: 'movies' }
    ]

    await wrapper.vm.selectCurrentDirectory()

    expect(wrapper.emitted('selected')).toBeTruthy()
    expect(wrapper.emitted('selected')[0]).toEqual(['123', 'movies'])
  })
})
