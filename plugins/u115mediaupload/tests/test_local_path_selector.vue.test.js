import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import LocalPathSelector from '@/components/LocalPathSelector.vue'

describe('LocalPathSelector.vue', () => {
  it('renders dialog when modelValue is true', () => {
    const wrapper = mount(LocalPathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    expect(wrapper.find('.v-dialog').exists()).toBe(true)
  })

  it('emits close event when cancel button clicked', async () => {
    const wrapper = mount(LocalPathSelector, {
      props: {
        modelValue: true,
        api: {}
      },
      stubs: {
        VDialog: { template: '<div><slot /></div>' }
      }
    })

    await wrapper.find('.v-btn').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('displays breadcrumbs correctly', async () => {
    const wrapper = mount(LocalPathSelector, {
      props: {
        modelValue: true,
        api: {}
      }
    })

    wrapper.vm.breadcrumbs = [
      { name: '媒体库', path: '' },
      { name: 'movies', path: 'movies' }
    ]

    await wrapper.vm.$nextTick()

    const breadcrumbs = wrapper.findAll('.v-breadcrumbs-item')
    expect(breadcrumbs.length).toBe(2)
  })
})
