import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PathMappingEditor from '@/components/PathMappingEditor.vue'

describe('PathMappingEditor Integration', () => {
  it('can add new mapping', async () => {
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings: [],
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const addBtn = wrapper.find('[icon="mdi-plus"]')
    await addBtn.trigger('click')

    expect(wrapper.emitted('update:mappings')).toBeTruthy()
    expect(wrapper.emitted('update:mappings')[0][0].length).toBe(1)
  })

  it('can toggle mapping enabled state', async () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/b', targetCid: '1' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const switchComponent = wrapper.findComponent({ name: 'VSwitch' })
    await switchComponent.vm.$emit('update:modelValue', false)

    expect(wrapper.emitted('update:mappings')[0][0][0].enabled).toBe(false)
  })

  it('can remove mapping', async () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/b', targetCid: '1' },
      { enabled: true, source: '/c', sourceDesc: 'c', target: '/d', targetCid: '2' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const deleteBtns = wrapper.findAll('[icon="mdi-delete-outline"]')
    await deleteBtns[0].trigger('click')

    expect(wrapper.emitted('update:mappings')[0][0].length).toBe(1)
    expect(wrapper.emitted('update:mappings')[0][0][0].source).toBe('/c')
  })

  it('handles local path selection', async () => {
    const mappings = [
      { enabled: true, source: '', sourceDesc: '', target: '/', targetCid: '0' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    wrapper.vm.editingIndex = 0
    await wrapper.vm.onLocalPathSelected('movies/action')

    expect(wrapper.emitted('update:mappings')).toBeTruthy()
    const updated = wrapper.emitted('update:mappings')[0][0][0]
    expect(updated.source).toBe('movies/action')
    expect(updated.sourceDesc).toBe('action')
  })

  it('handles P115 path selection', async () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/', targetCid: '0' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    wrapper.vm.editingIndex = 0
    await wrapper.vm.onP115PathSelected('12345', '115Movies')

    expect(wrapper.emitted('update:mappings')).toBeTruthy()
    const updated = wrapper.emitted('update:mappings')[0][0][0]
    expect(updated.target).toBe('115Movies')
    expect(updated.targetCid).toBe('12345')
  })

  it('renders empty state when no mappings', () => {
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings: [],
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    expect(wrapper.text()).toContain('暂无路径映射')
  })

  it('shows save button when mappings exist', () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/b', targetCid: '1' }
    ]
    const wrapper = mount(PathMappingEditor, {
      props: {
        api: {},
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      }
    })

    const saveBtn = wrapper.find('[icon="mdi-content-save"]')
    expect(saveBtn.exists()).toBe(true)
  })

  it('emits toast on save error', async () => {
    const mappings = [
      { enabled: true, source: '/a', sourceDesc: 'a', target: '/b', targetCid: '1' }
    ]

    const mockApi = {}
    const mockPluginRequest = vi.fn().mockResolvedValue({ success: false, msg: '保存失败' })

    // Mock the pluginRequest function
    vi.mock('../utils/plugin', () => ({
      pluginRequest: mockPluginRequest
    }))

    const wrapper = mount(PathMappingEditor, {
      props: {
        api: mockApi,
        mappings,
      },
      stubs: {
        LocalPathSelector: true,
        P115PathSelector: true,
      },
      global: {
        mocks: {
          pluginRequest: mockPluginRequest
        }
      }
    })

    await wrapper.vm.saveMappings()

    expect(wrapper.emitted('toast')).toBeTruthy()
  })
})
