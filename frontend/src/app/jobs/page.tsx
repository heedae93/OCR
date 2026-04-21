'use client'

import { useState, useEffect } from 'react'
import Sidebar from '@/components/Sidebar'
import { useRouter } from 'next/navigation'
import { API_BASE_URL } from '@/lib/api'

interface Job {
  job_id: string
  filename: string
  status: string
  progress_percent: number
  total_pages: number
  created_at: string
  completed_at?: string
  processing_time_seconds?: number
  total_text_blocks?: number
  average_confidence?: number
  is_double_column?: boolean
  pdf_url?: string
}

interface SessionGroup {
  session_id: string
  session_name: string
  jobs: Job[]
  expanded: boolean
}

interface Statistics {
  total_jobs: number
  status_counts: { [key: string]: number }
  total_pages_processed: number
  average_processing_time_seconds: number
  storage_used_mb: number
}

export default function JobsPage() {
  const router = useRouter()
  const [groups, setGroups] = useState<SessionGroup[]>([])
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  useEffect(() => {
    loadData()
    loadStatistics()
  }, [statusFilter])

  // 처리 중인 작업이 있으면 3초마다 자동 새로고침
  useEffect(() => {
    const hasProcessing = groups.some(g => g.jobs.some(j => j.status === 'processing' || j.status === 'queued'))
    if (!hasProcessing) return
    const timer = setInterval(() => {
      loadData({ silent: true })
      loadStatistics()
    }, 3000)
    return () => clearInterval(timer)
  }, [groups])

  const loadData = async ({ silent = false }: { silent?: boolean } = {}) => {
    try {
      if (!silent) setLoading(true)
      const user = JSON.parse(localStorage.getItem('user') || '{}')
      const userId = user.user_id || ''

      // 세션 목록과 작업 목록 동시 로드
      const [sessionsRes, jobsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/sessions?user_id=${userId}`),
        fetch(`${API_BASE_URL}/api/jobs?${new URLSearchParams({ user_id: userId, limit: '100' })}`)
      ])

      const sessions = sessionsRes.ok ? await sessionsRes.json() : []
      const jobs: Job[] = jobsRes.ok ? await jobsRes.json() : []

      // job_id → session 매핑
      const jobToSession: Record<string, { session_id: string; session_name: string }> = {}
      for (const session of sessions) {
        for (const doc of session.documents || []) {
          jobToSession[doc.job_id] = { session_id: session.session_id, session_name: session.session_name }
        }
      }

      // 세션별 그룹핑
      const groupMap: Record<string, SessionGroup> = {}
      for (const job of jobs) {
        const sessionInfo = jobToSession[job.job_id]
        const key = sessionInfo ? sessionInfo.session_id : '__unassigned__'
        const name = sessionInfo ? sessionInfo.session_name : '세션 미지정'
        if (!groupMap[key]) {
          groupMap[key] = { session_id: key, session_name: name, jobs: [], expanded: true }
        }
        groupMap[key].jobs.push(job)
      }

      // 세션 순서 맞춤 (세션 목록 순서 → 미지정 마지막)
      const ordered: SessionGroup[] = []
      for (const session of sessions) {
        if (groupMap[session.session_id]) ordered.push(groupMap[session.session_id])
      }
      if (groupMap['__unassigned__']) ordered.push(groupMap['__unassigned__'])

      setGroups(ordered)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const loadStatistics = async () => {
    try {
      const user = JSON.parse(localStorage.getItem('user') || '{}')
      const response = await fetch(`${API_BASE_URL}/api/jobs/statistics/summary?user_id=${user.user_id || ''}`)
      const data = await response.json()
      setStatistics(data)
    } catch (error) {
      console.error('Failed to load statistics:', error)
    }
  }

  const toggleGroup = (sessionId: string) => {
    setGroups(prev => prev.map(g => g.session_id === sessionId ? { ...g, expanded: !g.expanded } : g))
  }

  const handleDelete = async (jobId: string) => {
    if (!confirm('정말 이 작업을 삭제하시겠습니까?')) return
    try {
      const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`, { method: 'DELETE' })
      if (response.ok) { loadData(); loadStatistics() }
    } catch (error) {
      console.error('Failed to delete job:', error)
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-'
    return new Date(dateString).toLocaleString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds.toFixed(1)}초`
    return `${Math.floor(seconds / 60)}분 ${Math.floor(seconds % 60)}초`
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
      case 'processing': return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
      case 'failed': return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
      default: return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed': return '완료'
      case 'processing': return '처리 중'
      case 'failed': return '실패'
      case 'queued': return '대기 중'
      default: return status
    }
  }

  // 필터링
  const filteredGroups = groups.map(g => ({
    ...g,
    jobs: g.jobs.filter(job => {
      const matchStatus = statusFilter === 'all' || job.status === statusFilter
      const matchSearch = !searchQuery || job.filename.toLowerCase().includes(searchQuery.toLowerCase())
      return matchStatus && matchSearch
    })
  })).filter(g => g.jobs.length > 0)

  return (
    <div className="bg-background-light dark:bg-background-dark min-h-screen">
      <Sidebar />
      <main className="flex-1 ml-64 p-6 lg:p-10">
        <div className="w-full max-w-7xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-3xl font-bold text-text-primary-light dark:text-text-primary-dark">작업 내역</h1>
          </div>

          {/* Statistics Cards */}
          {statistics && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
              {[
                { label: '총 작업 수', value: statistics.total_jobs },
                { label: '처리된 페이지', value: statistics.total_pages_processed },
                { label: '평균 처리 시간', value: formatDuration(statistics.average_processing_time_seconds) },
                { label: '사용 용량', value: `${statistics.storage_used_mb} MB` },
              ].map(({ label, value }) => (
                <div key={label} className="bg-surface-light dark:bg-surface-dark p-6 rounded-xl border border-border-light dark:border-border-dark">
                  <div className="text-sm text-text-secondary-light dark:text-text-secondary-dark mb-1">{label}</div>
                  <div className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">{value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Search and Filter */}
          <div className="bg-surface-light dark:bg-surface-dark p-4 rounded-xl border border-border-light dark:border-border-dark mb-6">
            <div className="flex flex-col md:flex-row gap-4">
              <input
                type="text"
                placeholder="파일명 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 px-4 py-2 bg-background-light dark:bg-background-dark border border-border-light dark:border-border-dark rounded-lg text-text-primary-light dark:text-text-primary-dark"
              />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-4 py-2 bg-background-light dark:bg-background-dark border border-border-light dark:border-border-dark rounded-lg text-text-primary-light dark:text-text-primary-dark"
              >
                <option value="all">모든 상태</option>
                <option value="completed">완료</option>
                <option value="processing">처리 중</option>
                <option value="failed">실패</option>
                <option value="queued">대기 중</option>
              </select>
              <button onClick={() => { void loadData() }} className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors">
                검색
              </button>
            </div>
          </div>

          {/* Groups */}
          {loading ? (
            <div className="flex items-center justify-center p-16">
              <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
            </div>
          ) : filteredGroups.length === 0 ? (
            <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-16 text-center text-text-secondary-light dark:text-text-secondary-dark">
              작업 내역이 없습니다
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {filteredGroups.map(group => (
                <div key={group.session_id} className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark overflow-hidden">
                  {/* 세션 헤더 */}
                  <button
                    onClick={() => toggleGroup(group.session_id)}
                    className="w-full flex items-center justify-between px-6 py-4 bg-background-light dark:bg-background-dark hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <span className="material-symbols-outlined text-primary">folder_open</span>
                      <span className="font-semibold text-text-primary-light dark:text-text-primary-dark">{group.session_name}</span>
                      <span className="px-2 py-0.5 text-xs rounded-full bg-primary/10 text-primary font-medium">
                        {group.jobs.length}개
                      </span>
                    </div>
                    <span className={`material-symbols-outlined text-text-secondary-light dark:text-text-secondary-dark transition-transform duration-200 ${group.expanded ? 'rotate-180' : ''}`}>
                      expand_more
                    </span>
                  </button>

                  {/* 작업 목록 */}
                  {group.expanded && (
                    <div className="overflow-x-auto">
                      <table className="w-full">
                        <thead className="border-t border-border-light dark:border-border-dark">
                          <tr>
                            {['파일명', '상태', '페이지', '생성일', '처리 시간', '작업'].map(h => (
                              <th key={h} className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border-light dark:divide-border-dark">
                          {group.jobs.map(job => (
                            <tr key={job.job_id} className="hover:bg-background-light dark:hover:bg-background-dark transition-colors">
                              <td className="px-6 py-4">
                                <button onClick={() => router.push(`/editor/${job.job_id}`)}
                                  className="text-sm font-medium text-primary hover:text-primary/80 text-left">
                                  {job.filename}
                                </button>
                                {job.is_double_column && (
                                  <span className="ml-2 px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded text-xs">더블 컬럼</span>
                                )}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusColor(job.status)}`}>
                                  {getStatusText(job.status)}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary-light dark:text-text-secondary-dark">
                                {job.total_pages}p
                                {job.total_text_blocks && <div className="text-xs">{job.total_text_blocks} 블록</div>}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary-light dark:text-text-secondary-dark">
                                {formatDate(job.created_at)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary-light dark:text-text-secondary-dark">
                                {formatDuration(job.processing_time_seconds)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-3">
                                {job.status === 'completed' && job.pdf_url && (
                                  <button
                                    onClick={async () => {
                                      const url = `${API_BASE_URL}${job.pdf_url}`
                                      const res = await fetch(url)
                                      const blob = await res.blob()
                                      const a = document.createElement('a')
                                      a.href = window.URL.createObjectURL(blob)
                                      a.download = job.filename || `${job.job_id}.pdf`
                                      a.click()
                                      window.URL.revokeObjectURL(a.href)
                                    }}
                                    className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
                                    다운로드
                                  </button>
                                )}
                                <button onClick={() => handleDelete(job.job_id)}
                                  className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300">
                                  삭제
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
