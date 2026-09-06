/**
 * 媒体清单的筛选。
 *
 * 结构照着安全清理台那套：同一组里单选、不同组之间是「而且」、标记那一组可以多选叠加，
 * 每个选项后面的计数会把**你已经选了的其它维度**算进去 —— 所以「电影 12」这个数字的意思
 * 是「在当前其它筛选下，电影有 12 条」，不是「全库有 12 部电影」。不这么算的话，勾了两个
 * 条件之后所有计数都会对不上眼前的清单。
 *
 * 计数放前端算是有意的：放后端就得为每一次勾选往返一趟。
 */

export const FLAG_LABELS = {
  pending_delete: '等你确认删除',
  season_gap: '季集不全',
  strm_gone: 'STRM 缺一部分',
  duplicate: '重复生成',
  untracked: '记录外',
  unlinkable: '取不到链',
  source_left: '源文件还占地方',
}

export const LIBRARY_LABELS = {
  yes: '已入库（在网盘上）',
  no: '未入库（本地待传）',
  unknown: '判不出来',
}

export function createFilterState() {
  return { kind: 'all', library: 'all', channel: 'all', cloud: 'all', flags: [] }
}

/**
 * 通道那一组的选项是运行时才知道的，所以整份组定义要按数据生成。
 *
 * **没有「全部」这个选项**：一组里什么都没选就是全部，点掉选中的那个就回到全部。这样每个
 * 筹码都自己说清了自己是什么，组标题就不必存在了 —— 三个组各摆一个「全部」的话，去掉标题
 * 之后没人分得清哪个「全部」管哪一维。
 *
 * 做种和「网盘上还在不在」两维还没定，后端给了 has_* 才画对应的组。
 */
export function buildGroups(channels = [], options = {}) {
  const groups = [
    {
      id: 'kind',
      label: '资源类型',
      multi: false,
      options: [
        { id: 'movie', label: '电影' },
        { id: 'tv', label: '剧集' },
      ],
    },
    {
      id: 'library',
      label: '入库状态',
      multi: false,
      options: [
        { id: 'yes', label: '已入库' },
        { id: 'no', label: '未入库' },
        { id: 'unknown', label: '判不出来' },
      ],
    },
    {
      id: 'channel',
      label: '通道',
      multi: false,
      options: channels.map(channel => ({ id: channel.id, label: channel.label })),
    },
    {
      id: 'flags',
      label: '待处理 / 质量',
      multi: true,
      options: Object.entries(FLAG_LABELS).map(([id, label]) => ({
        id,
        label,
        tone: id === 'pending_delete' ? 'hold' : 'warning',
      })),
    },
  ]
  // 网盘核对是按预算的手动动作，所以「还没核对」是一个正经选项而不是缺省值：
  // 没问过 115 就说没问过，不拿「还在」凑数。
  if (options.hasCloudCheck) {
    groups.splice(3, 0, {
      id: 'cloud',
      label: '网盘状态',
      multi: false,
      options: [
        { id: 'yes', label: '网盘还在' },
        { id: 'no', label: '网盘上没了', tone: 'warning' },
        { id: 'unchecked', label: '还没核对' },
      ],
    })
  }
  if (options.hasSeeding) {
    groups.splice(3, 0, {
      id: 'seeding',
      label: '做种约束',
      multi: false,
      options: [
        { id: 'seeding', label: '还在做种', tone: 'warning' },
        { id: 'free', label: '没在做种' },
      ],
    })
  }
  return groups
}

export function matches(row, state) {
  const filters = state || createFilterState()
  if (filters.kind !== 'all' && row.kind !== filters.kind) return false
  if (filters.library !== 'all' && row.in_library !== filters.library) return false
  if (filters.channel !== 'all' && row.channel_id !== filters.channel) return false
  if (filters.cloud !== 'all' && (row.cloud_state || 'unchecked') !== filters.cloud) return false
  if (filters.seeding === 'seeding' && !row.seeding) return false
  if (filters.seeding === 'free' && row.seeding) return false
  const flags = Array.isArray(filters.flags) ? filters.flags : []
  return flags.every(flag => (row.flags || []).includes(flag))
}

/** 某个选项在「当前其它维度」下能筛出多少条。 */
export function optionCount(rows, state, groupId, optionId) {
  const next = { ...createFilterState(), ...(state || {}) }
  next.flags = Array.isArray(state?.flags) ? [...state.flags] : []
  if (groupId === 'flags') {
    next.flags = optionId === 'all' ? [] : [...new Set([...next.flags, optionId])]
  } else {
    next[groupId] = optionId
  }
  return (rows || []).filter(row => matches(row, next)).length
}

/**
 * 两个排序键。默认是入库时间升序 —— 打开清单先看见在库里待得最久的那些，那才是要动手的。
 * 还没入库的行没有入库时间，无论正序倒序都排在最后：它们还没进过库，混在时间轴里没有意义。
 */
export const SORTS = {
  library: { label: '入库时间', pick: row => Number(row.library_at || 0) },
  size: { label: '体积', pick: row => Number(row.size || 0) },
}

export function filterRows(rows, { state, search, sort = 'library', descending = false } = {}) {
  const query = String(search || '').trim().toLowerCase()
  const pick = (SORTS[sort] || SORTS.library).pick
  const sign = descending ? -1 : 1
  return [...(rows || [])]
    .filter(row => {
      if (!matches(row, state)) return false
      if (!query) return true
      const text = `${row.title || ''} ${row.year || ''} ${row.folder || ''} ${row.cloud_folder || ''}`
      return text.toLowerCase().includes(query)
    })
    .sort((left, right) => {
      const a = pick(left)
      const b = pick(right)
      // 没有值的排最后，不受升降序影响
      if (!a !== !b) return a ? -1 : 1
      return (a - b) * sign
        || String(left.title || '').localeCompare(String(right.title || ''), 'zh-CN')
    })
}
