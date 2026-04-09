'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import { API_BASE_URL } from '@/lib/api'

interface Summary {
  total_jobs: number
  status_counts: { [key: string]: number }
  total_pages_processed: number
  average_processing_time_seconds: number
  storage_used_mb: number
  today_completed: number
}

interface Trend {
  labels: string[]
  completed: number[]
  failed: number[]
}

type Period = 'daily' | 'weekly' | 'monthly'

export default function StatisticsPage() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [trend, setTrend] = useState<Trend | null>(null)
  const [period, setPeriod] = useState<Period>('daily')
  const [loading, setLoading] = useState(true)

  const getUserId = () => {
    try {
      const user = JSON.parse(localStorage.getItem('user') || '{}')
      return user.user_id || ''
    } catch { return '' }
  }

  useEffect(() => {
    const userId = getUserId()
    Promise.all([
      fetch(`${API_BASE_URL}/api/jobs/statistics/summary?user_id=${userId}`).then(r => r.json()),
    ]).then(([s]) => {
      setSummary(s)
      setLoading(false)
    })
  }, [])

  useEffect(() => {
    const userId = getUserId()
    fetch(`${API_BASE_URL}/api/jobs/statistics/trend?user_id=${userId}&period=${period}`)
      .then(r => r.json())
      .then(setTrend)
  }, [period])

  const formatDuration = (s: number) => {
    if (!s) return '-'
    if (s < 60) return `${s.toFixed(1)}초`
    return `${Math.floor(s / 60)}분 ${Math.floor(s % 60)}초`
  }

  const maxVal = trend ? Math.max(...trend.completed, ...trend.failed, 1) : 1
  const BAR_HEIGHT = 160

  const summaryCards = summary ? [
    { label: '전체 작업', value: summary.total_jobs, icon: 'folder_open', color: 'text-blue-500' },
    { label: '완료', value: summary.status_counts['completed'] ?? 0, icon: 'check_circle', color: 'text-green-500' },
    { label: '실패', value: summary.status_counts['failed'] ?? 0, icon: 'error', color: 'text-red-500' },
    { label: '오늘 처리', value: summary.today_completed, icon: 'today', color: 'text-primary' },
    { label: '총 페이지', value: `${summary.total_pages_processed}p`, icon: 'description', color: 'text-purple-500' },
    { label: '평균 처리시간', value: formatDuration(summary.average_processing_time_seconds), icon: 'timer', color: 'text-orange-500' },
    { label: '사용 용량', value: `${summary.storage_used_mb} MB`, icon: 'storage', color: 'text-teal-500' },
  ] : []

  return (
    <div className="relative flex min-h-screen w-full bg-background-light dark:bg-background-dark">
      <Sidebar />
      <main className="flex-1 p-6 lg:p-10 overflow-auto">
        <div className="w-full max-w-6xl mx-auto flex flex-col gap-8">
          <h1 className="text-3xl font-bold text-text-primary-light dark:text-text-primary-dark">통계</h1>

          {/* Summary Cards */}
          {loading ? (
            <div className="flex items-center justify-center p-16">
              <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
              {summaryCards.map(({ label, value, icon, color }) => (
                <div key={label} className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-4 flex flex-col gap-2">
                  <span className={`material-symbols-outlined ${color}`}>{icon}</span>
                  <div className="text-xl font-bold text-text-primary-light dark:text-text-primary-dark">{value}</div>
                  <div className="text-xs text-text-secondary-light dark:text-text-secondary-dark">{label}</div>
                </div>
              ))}
            </div>
          )}

          {/* Trend Chart */}
          <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-text-primary-light dark:text-text-primary-dark">처리량 추이</h2>
              <div className="flex gap-1 bg-background-light dark:bg-background-dark rounded-lg p-1">
                {(['daily', 'weekly', 'monthly'] as Period[]).map(p => (
                  <button
                    key={p}
                    onClick={() => setPeriod(p)}
                    className={`px-3 py-1.5 text-sm rounded-md transition-all ${
                      period === p
                        ? 'bg-primary text-white font-semibold'
                        : 'text-text-secondary-light dark:text-text-secondary-dark hover:text-text-primary-light dark:hover:text-text-primary-dark'
                    }`}
                  >
                    {p === 'daily' ? '일별' : p === 'weekly' ? '주별' : '월별'}
                  </button>
                ))}
              </div>
            </div>

            {/* Legend */}
            <div className="flex gap-4 mb-4">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm bg-primary" />
                <span className="text-xs text-text-secondary-light dark:text-text-secondary-dark">완료</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm bg-red-400" />
                <span className="text-xs text-text-secondary-light dark:text-text-secondary-dark">실패</span>
              </div>
            </div>

            {/* Bar Chart */}
            {trend ? (
              <div className="overflow-x-auto">
                <div style={{ minWidth: trend.labels.length * 52 }}>
                  {/* Y-axis guide lines */}
                  <div className="relative" style={{ height: BAR_HEIGHT + 24 }}>
                    {[0, 0.25, 0.5, 0.75, 1].map(ratio => (
                      <div
                        key={ratio}
                        className="absolute left-0 right-0 border-t border-border-light dark:border-border-dark"
                        style={{ bottom: ratio * BAR_HEIGHT + 24 }}
                      >
                        <span className="absolute -top-2.5 -left-1 text-xs text-text-secondary-light dark:text-text-secondary-dark pr-1" style={{ fontSize: 10 }}>
                          {ratio === 0 ? '' : Math.round(maxVal * ratio)}
                        </span>
                      </div>
                    ))}

                    {/* Bars */}
                    <div className="absolute bottom-6 left-6 right-0 flex items-end gap-1" style={{ height: BAR_HEIGHT }}>
                      {trend.labels.map((_label, i) => {
                        const ch = Math.round((trend.completed[i] / maxVal) * BAR_HEIGHT)
                        const fh = Math.round((trend.failed[i] / maxVal) * BAR_HEIGHT)
                        return (
                          <div key={i} className="flex-1 flex flex-col items-center gap-0.5 group relative">
                            {/* Tooltip */}
                            <div className="absolute bottom-full mb-1 hidden group-hover:flex flex-col items-center z-10">
                              <div className="bg-gray-800 dark:bg-gray-700 text-white text-xs rounded px-2 py-1 whitespace-nowrap">
                                완료 {trend.completed[i]} / 실패 {trend.failed[i]}
                              </div>
                              <div className="w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-800 dark:border-t-gray-700" />
                            </div>
                            <div className="w-full flex items-end gap-0.5" style={{ height: BAR_HEIGHT }}>
                              <div
                                className="flex-1 bg-primary/80 hover:bg-primary rounded-t transition-all duration-300"
                                style={{ height: ch || 1 }}
                              />
                              <div
                                className="flex-1 bg-red-400/80 hover:bg-red-400 rounded-t transition-all duration-300"
                                style={{ height: fh || (trend.failed[i] > 0 ? 1 : 0) }}
                              />
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    {/* X labels */}
                    <div className="absolute bottom-0 left-6 right-0 flex gap-1" style={{ height: 20 }}>
                      {trend.labels.map((label, i) => (
                        <div key={i} className="flex-1 text-center overflow-hidden" style={{ fontSize: 9 }}>
                          <span className="text-text-secondary-light dark:text-text-secondary-dark truncate block">
                            {label}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center" style={{ height: BAR_HEIGHT }}>
                <span className="material-symbols-outlined animate-spin text-primary text-3xl">progress_activity</span>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
