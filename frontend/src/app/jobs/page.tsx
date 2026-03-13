'use client'

import { useState, useEffect } from 'react'
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

interface Statistics {
  total_jobs: number
  status_counts: { [key: string]: number }
  total_pages_processed: number
  average_processing_time_seconds: number
  storage_used_mb: number
}

export default function JobsPage() {
  const router = useRouter()
  const [jobs, setJobs] = useState<Job[]>([])
  const [statistics, setStatistics] = useState<Statistics | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  useEffect(() => {
    loadJobs()
    loadStatistics()
  }, [statusFilter])

  const loadJobs = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        user_id: 'user001',
        limit: '50'
      })

      if (statusFilter !== 'all') {
        params.append('status', statusFilter)
      }

      if (searchQuery) {
        params.append('search', searchQuery)
      }

      const response = await fetch(`${API_BASE_URL}/api/jobs?${params}`)
      const data = await response.json()
      setJobs(data)
    } catch (error) {
      console.error('Failed to load jobs:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadStatistics = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/jobs/statistics/summary?user_id=user001`)
      const data = await response.json()
      setStatistics(data)
    } catch (error) {
      console.error('Failed to load statistics:', error)
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    loadJobs()
  }

  const handleDelete = async (jobId: string) => {
    if (!confirm('정말 이 작업을 삭제하시겠습니까?')) return

    try {
      const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`, {
        method: 'DELETE'
      })

      if (response.ok) {
        loadJobs()
        loadStatistics()
      }
    } catch (error) {
      console.error('Failed to delete job:', error)
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-'
    const date = new Date(dateString)
    return date.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds.toFixed(1)}초`
    const minutes = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${minutes}분 ${secs}초`
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

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-text-primary-light dark:text-text-primary-dark">
            작업 내역
          </h1>
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors"
          >
            새 작업 시작
          </button>
        </div>

        {/* Statistics Cards */}
        {statistics && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-surface-light dark:bg-surface-dark p-6 rounded-xl border border-border-light dark:border-border-dark">
              <div className="text-sm text-text-secondary-light dark:text-text-secondary-dark mb-1">
                총 작업 수
              </div>
              <div className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">
                {statistics.total_jobs}
              </div>
            </div>

            <div className="bg-surface-light dark:bg-surface-dark p-6 rounded-xl border border-border-light dark:border-border-dark">
              <div className="text-sm text-text-secondary-light dark:text-text-secondary-dark mb-1">
                처리된 페이지
              </div>
              <div className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">
                {statistics.total_pages_processed}
              </div>
            </div>

            <div className="bg-surface-light dark:bg-surface-dark p-6 rounded-xl border border-border-light dark:border-border-dark">
              <div className="text-sm text-text-secondary-light dark:text-text-secondary-dark mb-1">
                평균 처리 시간
              </div>
              <div className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">
                {formatDuration(statistics.average_processing_time_seconds)}
              </div>
            </div>

            <div className="bg-surface-light dark:bg-surface-dark p-6 rounded-xl border border-border-light dark:border-border-dark">
              <div className="text-sm text-text-secondary-light dark:text-text-secondary-dark mb-1">
                사용 용량
              </div>
              <div className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">
                {statistics.storage_used_mb} MB
              </div>
            </div>
          </div>
        )}

        {/* Search and Filter */}
        <div className="bg-surface-light dark:bg-surface-dark p-4 rounded-xl border border-border-light dark:border-border-dark mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <form onSubmit={handleSearch} className="flex-1">
              <input
                type="text"
                placeholder="파일명 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-4 py-2 bg-background-light dark:bg-background-dark border border-border-light dark:border-border-dark rounded-lg text-text-primary-light dark:text-text-primary-dark"
              />
            </form>

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

            <button
              onClick={loadJobs}
              className="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors"
            >
              검색
            </button>
          </div>
        </div>

        {/* Jobs Table */}
        <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-text-secondary-light dark:text-text-secondary-dark">
              로딩 중...
            </div>
          ) : jobs.length === 0 ? (
            <div className="p-8 text-center text-text-secondary-light dark:text-text-secondary-dark">
              작업 내역이 없습니다
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-background-light dark:bg-background-dark border-b border-border-light dark:border-border-dark">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                      파일명
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                      상태
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                      페이지
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                      생성일
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                      처리 시간
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                      작업
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light dark:divide-border-dark">
                  {jobs.map((job) => (
                    <tr key={job.job_id} className="hover:bg-background-light dark:hover:bg-background-dark transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">
                          {job.filename}
                        </div>
                        {job.is_double_column && (
                          <div className="text-xs text-text-secondary-light dark:text-text-secondary-dark">
                            <span className="inline-block px-2 py-0.5 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded">
                              더블 컬럼
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getStatusColor(job.status)}`}>
                          {getStatusText(job.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary-light dark:text-text-secondary-dark">
                        {job.total_pages} 페이지
                        {job.total_text_blocks && (
                          <div className="text-xs">
                            {job.total_text_blocks} 텍스트 블록
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary-light dark:text-text-secondary-dark">
                        {formatDate(job.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-text-secondary-light dark:text-text-secondary-dark">
                        {formatDuration(job.processing_time_seconds)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-2">
                        {job.status === 'completed' && job.pdf_url && (
                          <>
                            <button
                              onClick={() => router.push(`/editor/${job.job_id}`)}
                              className="text-primary hover:text-primary/80"
                            >
                              편집
                            </button>
                            <a
                              href={`${API_BASE_URL}${job.pdf_url}`}
                              download
                              className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                            >
                              다운로드
                            </a>
                          </>
                        )}
                        <button
                          onClick={() => handleDelete(job.job_id)}
                          className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                        >
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
      </div>
    </div>
  )
}
