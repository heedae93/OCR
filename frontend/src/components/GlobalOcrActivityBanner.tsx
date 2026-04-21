'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock3,
  ExternalLink,
  Loader2,
} from 'lucide-react'
import { useOcrActivity } from '@/contexts/OcrActivityContext'

const STORAGE_KEY = 'ocr-activity-banner-ui'

function getStatusText(status: 'queued' | 'processing' | 'completed' | 'failed') {
  switch (status) {
    case 'queued':
      return '큐 대기 중'
    case 'processing':
      return '워커 처리 중'
    case 'completed':
      return '완료'
    case 'failed':
      return '실패'
  }
}

export default function GlobalOcrActivityBanner() {
  const { trackedJobs, activeJobs, dismissFinishedJobs } = useOcrActivity()
  const [collapsed, setCollapsed] = useState(false)

  const completedCount = trackedJobs.filter(job => job.status === 'completed').length
  const failedCount = trackedJobs.filter(job => job.status === 'failed').length

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (!saved) return
      const parsed = JSON.parse(saved) as { collapsed?: boolean }
      setCollapsed(Boolean(parsed.collapsed))
    } catch (error) {
      console.warn('Failed to restore OCR banner UI state:', error)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ collapsed }))
  }, [collapsed])

  if (trackedJobs.length === 0) {
    return null
  }

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="fixed top-5 right-5 z-50 flex items-center gap-2 rounded-full border border-border-light dark:border-border-dark bg-surface-light/95 dark:bg-surface-dark/95 px-4 py-3 shadow-xl backdrop-blur hover:bg-surface-light dark:hover:bg-surface-dark"
      >
        {activeJobs.length > 0 ? (
          <Loader2 className="w-4 h-4 text-primary animate-spin" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-green-500" />
        )}
        <span className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">
          OCR 작업 {activeJobs.length > 0 ? `${activeJobs.length}개 진행 중` : '열기'}
        </span>
        <ChevronDown className="w-4 h-4 text-text-secondary-light dark:text-text-secondary-dark" />
      </button>
    )
  }

  return (
    <div className="fixed top-5 right-5 z-50 w-[380px] max-w-[calc(100vw-1.5rem)] rounded-2xl border border-border-light dark:border-border-dark bg-surface-light/95 dark:bg-surface-dark/95 shadow-2xl backdrop-blur">
      <div className="flex items-start justify-between gap-3 border-b border-border-light dark:border-border-dark px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-text-primary-light dark:text-text-primary-dark">
            {activeJobs.length > 0 ? (
              <Loader2 className="w-4 h-4 text-primary animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-green-500" />
            )}
            OCR 백그라운드 작업
          </div>
          <p className="mt-1 text-xs text-text-secondary-light dark:text-text-secondary-dark">
            {activeJobs.length > 0
              ? `${activeJobs.length}개 작업이 진행 중입니다.`
              : `진행 중인 작업은 없고 최근 작업 ${trackedJobs.length}개가 남아 있습니다.`}
          </p>
        </div>
        <button
          onClick={() => setCollapsed(true)}
          className="rounded-lg p-1 text-text-secondary-light dark:text-text-secondary-dark hover:bg-black/5 dark:hover:bg-white/5"
          title="접기"
        >
          <ChevronUp className="w-4 h-4" />
        </button>
      </div>

      {(completedCount > 0 || failedCount > 0) && (
        <div className="flex items-center justify-between gap-3 border-b border-border-light dark:border-border-dark px-4 py-2.5">
          <p className="text-xs text-text-secondary-light dark:text-text-secondary-dark">
            완료 {completedCount} · 실패 {failedCount}
          </p>
          <button
            onClick={dismissFinishedJobs}
            className="text-xs font-medium text-text-secondary-light dark:text-text-secondary-dark hover:text-primary"
          >
            완료/실패 항목 지우기
          </button>
        </div>
      )}

      <div className="max-h-[420px] overflow-y-auto px-4 py-3">
        <div className="flex flex-col gap-2">
          {trackedJobs.map(job => (
            <div
              key={job.id}
              className="rounded-xl border border-border-light dark:border-border-dark bg-background-light/70 dark:bg-background-dark/70 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text-primary-light dark:text-text-primary-dark">
                    {job.filename}
                  </p>
                  <p className="truncate text-xs text-text-secondary-light dark:text-text-secondary-dark">
                    {job.sessionName}
                  </p>
                </div>
                <div className="shrink-0 text-xs font-medium">
                  {job.status === 'failed' ? (
                    <span className="inline-flex items-center gap-1 text-red-500">
                      <AlertCircle className="w-3.5 h-3.5" />
                      {getStatusText(job.status)}
                    </span>
                  ) : job.status === 'completed' ? (
                    <span className="inline-flex items-center gap-1 text-green-500">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      {getStatusText(job.status)}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-primary">
                      <Clock3 className="w-3.5 h-3.5" />
                      {getStatusText(job.status)}
                    </span>
                  )}
                </div>
              </div>

              {(job.status === 'queued' || job.status === 'processing') && (
                <div className="mt-2">
                  <div className="h-1.5 w-full rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className="h-1.5 rounded-full bg-primary transition-all duration-300"
                      style={{ width: `${Math.max(8, Math.min(job.progressPercent, 100))}%` }}
                    />
                  </div>
                  <p className="mt-1 text-[11px] text-text-secondary-light dark:text-text-secondary-dark">
                    {job.status === 'queued'
                      ? 'Redis 큐에 등록되어 워커를 기다리는 중입니다.'
                      : `${Math.round(job.progressPercent)}% 처리 중`}
                  </p>
                </div>
              )}

              {job.status === 'failed' && job.error && (
                <p className="mt-1 text-[11px] text-red-500">{job.error}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-end gap-3 border-t border-border-light dark:border-border-dark px-4 py-3 text-sm">
        <Link href="/jobs" className="text-text-secondary-light dark:text-text-secondary-dark hover:text-primary">
          작업 내역
        </Link>
        <Link href="/ocr-work" className="inline-flex items-center gap-1 font-medium text-primary hover:text-primary/80">
          OCR 작업하기
          <ExternalLink className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  )
}
