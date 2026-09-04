// 运行台的纯计算：日期归一、状态判定、连续天数、打卡带。
// 只吃 /status 返回的数据，不碰 DOM，也不引 Vue。

// 后端把这些状态视为「今天这枚卡打上了」
const SIGNED = new Set(['全部成功', '签到成功', '今日已签到'])

const pad = value => String(value).padStart(2, '0')

export function dayKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function midnight(date = new Date()) {
  const copy = new Date(date)
  copy.setHours(0, 0, 0, 0)
  return copy
}

// 后端时间是 'YYYY-MM-DD HH:MM:SS'，也可能是 '-' 或 '今天 ...'
export function datePart(value, today = dayKey(new Date())) {
  if (!value) return ''
  const text = String(value)
  if (text.startsWith('今天')) return today
  const matched = text.match(/\d{4}-\d{2}-\d{2}/)
  return matched ? matched[0] : ''
}

export function shortTime(value) {
  if (!value || value === '-') return '—'
  const matched = String(value).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/)
  return matched ? `${matched[2]}-${matched[3]} ${matched[4]}:${matched[5]}` : String(value)
}

export function shortDate(value) {
  const day = datePart(value)
  return day ? day.slice(5) : '—'
}

export function isSigned(status) {
  return SIGNED.has(status)
}

// 一次执行落到哪一档：3 全签 / 2 部分 / 1 失败 / 0 无记录
export function rankOf(status) {
  if (SIGNED.has(status)) return 3
  if (status === '部分成功') return 2
  if (status === '执行失败') return 1
  return 0
}

export const RANK_WORD = { 3: '全部成功', 2: '部分成功', 1: '执行失败', 0: '没有记录' }

/**
 * 连续签到天数：从今天（今天还没签就从昨天）往回连数有成功记录的日子。
 */
export function streakOf(history, now = new Date()) {
  const signed = new Set()
  for (const entry of history || []) {
    if (SIGNED.has(entry.status) || Number(entry.success_count) > 0) {
      const day = datePart(entry.time)
      if (day) signed.add(day)
    }
  }
  if (!signed.size) return 0

  const cursor = midnight(now)
  if (!signed.has(dayKey(cursor))) cursor.setDate(cursor.getDate() - 1)
  let days = 0
  while (signed.has(dayKey(cursor))) {
    days += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return days
}

/**
 * 打卡带：最近 span 天，每天取当天最好的一档。返回从早到晚的格子。
 */
export function tapeOf(history, span = 30, now = new Date()) {
  const best = {}
  for (const entry of history || []) {
    const day = datePart(entry.time)
    if (day) best[day] = Math.max(best[day] || 0, rankOf(entry.status))
  }

  const today = dayKey(midnight(now))
  const cells = []
  for (let back = span - 1; back >= 0; back -= 1) {
    const cursor = midnight(now)
    cursor.setDate(cursor.getDate() - back)
    const day = dayKey(cursor)
    cells.push({
      day,
      label: day.slice(5),
      rank: best[day] || 0,
      today: day === today,
    })
  }
  return cells
}

/**
 * 今天这一格的结论，直接用来写标题。
 */
export function todayVerdict(status = {}, now = new Date()) {
  const today = dayKey(midnight(now))
  const ranToday = datePart(status.last_run, today) === today
  const total = Number(status.enabled_site_count) || 0

  if (!ranToday) {
    return {
      rank: 0,
      headline: total ? '今天还没签' : '还没有启用站点',
      detail: total ? `${total} 个站点在等这一次` : '去设置里打开一个站点、填好账号',
    }
  }
  const rank = rankOf(status.last_status)
  const done = Number(status.last_result?.success_count) || 0
  const left = Math.max(total - done, 0)
  if (rank === 3) return { rank, headline: '今天都签上了', detail: `${done} / ${total} 个站点` }
  if (rank === 2) return { rank, headline: `今天 ${left} 个没签上`, detail: '看下面的原因，处理完再跑一次' }
  return { rank, headline: '今天一个都没签上', detail: '看下面的原因，处理完再跑一次' }
}

/**
 * 漏签补跑的一句话。后端每半小时巡检一次「今天该签、还没签成」，
 * 这里只负责把它的状态说成人话，不参与判断。
 */
export function catchupNote(status = {}) {
  const catchup = status.catchup || {}
  if (!catchup.pending) return null
  const used = Number(catchup.used) || 0
  const max = Number(catchup.max) || 0
  const due = catchup.due_at || ''
  if (max && used >= max) {
    return {
      tone: 'bad',
      headline: `今天的自动重试用完了`,
      detail: '处理完下面的原因，手动再跑一次。',
    }
  }
  return {
    tone: 'hold',
    headline: due ? `今天 ${due} 那次没签上` : '今天这次没签上',
    detail: used
      ? `已经自动再试 ${used} 次，还剩 ${max - used} 次。`
      : '没签上的每半小时自动再试一次。',
  }
}

// ── 读数格式：与后端 plugins/checkin/__init__.py 的通知层逐字对齐 ──────
//
// 同一个数在通知里、运行台卡片里、站点行里必须长一个样。后端那几个函数
// （_traffic_text / _points_gained / _looks_like_markup / _short_reason）在这里各有
// 一份等价实现 —— 界面读的是 /status 里的原始明细，后端不下发成品字符串。
// 改任何一处都要同时改另一处。

const POINTS_PATTERNS = [
  /今日积分\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)/,
  /本次签到增加\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*积分/,
  /(?:获得|奖励|增加)\s*([0-9]+(?:\.[0-9]+)?)\s*积分/,
]

const trimNumber = value => {
  const text = String(value ?? '').trim()
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text
}

/** 流量读数。过 1 GB 就换单位，小数点后的 MB 是噪音。 */
export function trafficText(megabytes) {
  const value = Number(megabytes)
  if (!Number.isFinite(value) || value <= 0) return ''
  if (value >= 1024) return `${(value / 1024).toFixed(2)} GB`
  return value >= 10 ? `${Math.round(value)} MB` : `${trimNumber(value.toFixed(1))} MB`
}

export function trafficMb(item) {
  const value = Number(String(item?.reward_mb ?? '').trim())
  return Number.isFinite(value) && value > 0 ? value : 0
}

/** 站点把积分写在回执正文里，三家写法不同，这里收敛成一个数。0 不算到手。 */
export function pointsGained(message) {
  const text = String(message ?? '')
  for (const pattern of POINTS_PATTERNS) {
    const matched = text.match(pattern)
    if (matched) {
      const value = trimNumber(matched[1])
      return value === '0' ? '' : value
    }
  }
  return ''
}

/** 这段「原因」其实是页面源码吗？花括号、尖括号、`属性: 值;` 正常人话里不会出现。 */
export function looksLikeMarkup(text) {
  return /[{}<>]|[A-Za-z-]+\s*:\s*[^;]{1,20};/.test(String(text ?? ''))
}

const REASON_LIMIT = 24

/** 把失败原因压成一句读得完的话，在第一个说得完整的分句处收住。 */
export function shortReason(message, name = '') {
  let text = String(message ?? '').trim().replace(/\s+/g, ' ')
  // 界面里不能说「去运行台看」——人已经在运行台里了，那句话在通知里才成立
  if (!text || text === '-' || looksLikeMarkup(text)) return '站点没给原因'
  if (name && text.startsWith(name)) text = text.slice(name.length).replace(/^[\s：:的]+/, '') || text
  const head = text.slice(0, REASON_LIMIT)
  const cut = [...head].findIndex((char, index) => index >= 4 && '，。；！？,;.'.includes(char))
  if (cut < 0) return text.length <= REASON_LIMIT ? text : `${head}…`
  return cut === text.length - 1 ? text.slice(0, cut) : `${text.slice(0, cut)}…`
}

// ── 执行记录卡片：与 115 轻量助手的记录卡同构 ─────────────────────────
//
// 卡片三段，两个插件逐字相同：
//   ① 左边一句结论（着色）+ 右边一个次要读数（这边是站点数，115 那边是耗时）
//   ② 完整时间戳，等宽次要色
//   ③ 一排读数丸：只报有意义的那几个，避免整排 0
// 展开出来的站点行照通知里的写法：状态位 + 站点名 + 拿到了什么。同一件事在通知、
// 运行台、站点行三处只有一种说法。

const VERDICT = {
  3: { text: '都签上了', tone: 'on' },
  2: { text: '签上一部分', tone: 'warn' },
  1: { text: '没签上', tone: 'bad' },
  0: { text: '没有记录', tone: '' },
}

/** 一次执行的结论。整批都是「今日已签到」时说清是早就签过了，别当成这次的战果。 */
export function runVerdict(entry = {}) {
  const details = entry.details || []
  const rank = rankOf(entry.status)
  if (rank === 3 && details.length && details.every(item => item.status === '今日已签到')) {
    return { text: '早就签过了', tone: 'on' }
  }
  return VERDICT[rank] || VERDICT[0]
}

/** 一排读数丸：这次到手了什么，出事了几个。什么都没有就说「没有变化」。 */
export function runTally(entry = {}) {
  const details = entry.details || []
  const signed = details.filter(item => isSigned(item.status))
  const traffic = signed.reduce((sum, item) => sum + trafficMb(item), 0)
  const points = signed.reduce((sum, item) => sum + Number(pointsGained(item.message) || 0), 0)
  const parts = []
  if (traffic > 0) parts.push({ text: `+${trafficText(traffic)}`, tone: '' })
  if (points > 0) parts.push({ text: `+${trimNumber(points.toFixed(2))} 积分`, tone: '' })
  const failed = Number(entry.failure_count) || 0
  if (failed > 0) parts.push({ text: `${failed} 个没签上`, tone: 'bad' })
  return parts.length ? parts : [{ text: '没有变化', tone: '' }]
}

/**
 * 一个站点在某次执行里的一行：状态位 + 站点名 + 拿到了什么，与通知里那几行同构。
 * 记号用带色的 ✓ / ✕ 而不是通知里的 ✅ / ❌：通知那边没有颜色可用，只能靠 emoji 自带
 * 的红绿；界面里颜色是现成的，几何记号更安静，也和 2px 状态线是同一套语汇。
 */
export function siteRow(item = {}) {
  const name = item.site_name || item.site || '-'
  if (!isSigned(item.status)) {
    return { mark: '✕', tone: 'bad', name, note: shortReason(item.message, name) }
  }
  const notes = []
  const traffic = trafficText(trafficMb(item))
  if (traffic) notes.push(`+${traffic}`)
  const points = pointsGained(item.message)
  if (points) notes.push(`+${points} 积分`)
  const stock = String(item.total_traffic ?? '').trim()
  if (stock && !['-', '0', '0.00 GB'].includes(stock)) notes.push(`累计 ${stock}`)
  if (!notes.length && item.status === '今日已签到') notes.push('今天已经签过了')
  return { mark: '✓', tone: 'on', name, note: notes.join(' · ') }
}
