/**
 * 界面上所有数字与时间的写法只此一处。
 *
 * 规范第 6 节要求「数字两边留一个空格，数字和单位之间也留」，而且同一个概念在通知、
 * 运行台、控制台三处必须同名 —— 分散在各组件里写第二遍，两处就会慢慢漂开。
 */

// 体积用等宽 + 定宽单位，好让一列数字对齐着扫
export function bytes(value) {
  let left = Number(value) || 0
  if (left <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unit = 0
  while (left >= 1024 && unit < units.length - 1) {
    left /= 1024
    unit += 1
  }
  const shown = unit === 0 || left >= 100 ? Math.round(left) : left.toFixed(1)
  return `${shown} ${units[unit]}`
}

// 与通知层的 _duration_text 同一个写法：写「3.1 秒」而不是「3100ms」
export function seconds(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value <= 0) return ''
  if (value < 1000) return '不到 1 秒'
  const total = value / 1000
  if (total < 60) return `${total.toFixed(1)} 秒`
  const mins = Math.floor(total / 60)
  const rest = Math.round(total % 60)
  return rest ? `${mins} 分 ${rest} 秒` : `${mins} 分`
}

export function shortTime(stamp) {
  return String(stamp || '').replace('T', ' ').slice(5, 16)
}

// 千分位只用窄空格分组会和「数字两边留空格」打架，所以整数一律原样输出
export function count(value) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? String(numeric) : '0'
}

/**
 * 「21 分钟前」。读的人关心的是「新不新」，不是几点几分 —— 精确时间戳留给执行记录。
 * 解析不出来就退回原样，绝不显示 Invalid Date。
 */
export function ago(stamp) {
  // 也收毫秒时间戳：网盘核对存的是 epoch，不是字符串
  if (typeof stamp === 'number') {
    if (!Number.isFinite(stamp) || stamp <= 0) return ''
    return agoFrom(stamp)
  }
  const text = String(stamp || '').trim()
  if (!text) return ''
  const parsed = Date.parse(text.includes('T') ? text : text.replace(' ', 'T'))
  if (!Number.isFinite(parsed)) return text
  const diff = Date.now() - parsed
  if (diff < 0) return shortTime(text)
  const relative = agoFrom(parsed)
  return relative || shortTime(text)
}

function agoFrom(epochMs) {
  const diff = Date.now() - epochMs
  if (diff < 0) return '刚刚'
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  return `${days} 天前`
}

// 网盘路径只留头尾：中间几层跟判断无关，末尾那个季目录才是「在库里的哪儿」
export function shortDir(cloudPath) {
  const parts = String(cloudPath || '').split('/').filter(Boolean)
  if (parts.length <= 1) return '/'
  const dirs = parts.slice(0, -1)
  if (dirs.length <= 2) return `/${dirs.join('/')}`
  return `/${dirs[0]}/…/${dirs[dirs.length - 1]}`
}

// 路径分隔符不写字面反斜杠，省掉一层转义坑（宿主可能跑在 Windows 上）
const PATH_SEPARATORS = ['/', String.fromCharCode(92)]

export function fileName(path) {
  let value = String(path || '')
  for (const separator of PATH_SEPARATORS) {
    const cut = value.lastIndexOf(separator)
    if (cut >= 0) value = value.slice(cut + 1)
  }
  return value
}
