// 签到台账的纯计算：日期归一、状态判定、连续天数、打卡带。
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
      detail: total ? `${total} 个站点在等这一次执行` : '去配置页启用站点并填好账号',
    }
  }
  const rank = rankOf(status.last_status)
  const done = Number(status.last_result?.success_count) || 0
  if (rank === 3) return { rank, headline: '今天已签完', detail: `${done} / ${total} 个站点签到成功` }
  if (rank === 2) return { rank, headline: '今天签了一半', detail: `${done} / ${total} 个站点成功，其余可以再跑一次` }
  return { rank, headline: '今天没签上', detail: status.last_result?.message || '看站点行的原因，处理后再跑一次' }
}
