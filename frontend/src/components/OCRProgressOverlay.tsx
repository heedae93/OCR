'use client'

import { useEffect, useState } from 'react'

interface OCRProgressOverlayProps {
  isVisible: boolean
  progress: number
  currentPage: number
  totalPages: number
  stage?: string
  onCancel?: () => void
}

export default function OCRProgressOverlay({
  isVisible,
  progress,
  currentPage,
  totalPages,
  stage = 'OCR 처리 중...',
  onCancel
}: OCRProgressOverlayProps) {
  const [animatedProgress, setAnimatedProgress] = useState(0)

  // Smooth progress animation
  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedProgress(progress)
    }, 100)
    return () => clearTimeout(timer)
  }, [progress])

  if (!isVisible) return null

  const progressPercent = Math.min(Math.max(animatedProgress, 0), 100)
  const circumference = 2 * Math.PI * 45 // radius = 45
  const strokeDashoffset = circumference - (progressPercent / 100) * circumference

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop with blur */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-md" />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-8 p-10 max-w-md w-full mx-4">
        {/* Circular Progress */}
        <div className="relative">
          {/* Background glow */}
          <div className="absolute inset-0 rounded-full bg-primary/20 blur-2xl scale-150" />

          {/* SVG Progress Ring */}
          <svg className="w-40 h-40 transform -rotate-90 relative z-10" viewBox="0 0 100 100">
            {/* Background circle */}
            <circle
              cx="50"
              cy="50"
              r="45"
              stroke="currentColor"
              strokeWidth="6"
              fill="none"
              className="text-white/10"
            />
            {/* Progress circle */}
            <circle
              cx="50"
              cy="50"
              r="45"
              stroke="url(#progressGradient)"
              strokeWidth="6"
              fill="none"
              strokeLinecap="round"
              style={{
                strokeDasharray: circumference,
                strokeDashoffset: strokeDashoffset,
                transition: 'stroke-dashoffset 0.5s ease-out'
              }}
            />
            {/* Gradient definition */}
            <defs>
              <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#4A90E2" />
                <stop offset="100%" stopColor="#6BA3E8" />
              </linearGradient>
            </defs>
          </svg>

          {/* Center content */}
          <div className="absolute inset-0 flex flex-col items-center justify-center z-20">
            <span className="text-4xl font-bold text-white">
              {Math.round(progressPercent)}%
            </span>
            {totalPages > 0 && (
              <span className="text-sm text-white/70 mt-1">
                {currentPage} / {totalPages}
              </span>
            )}
          </div>
        </div>

        {/* Status text */}
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-primary rounded-full animate-pulse" />
            <span className="text-lg font-semibold text-white">
              {stage}
            </span>
          </div>

          {/* Sub-status */}
          {totalPages > 0 && (
            <p className="text-sm text-white/60">
              페이지 {currentPage} 처리 중...
            </p>
          )}
        </div>

        {/* Progress bar (secondary indicator) */}
        <div className="w-full max-w-xs">
          <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-primary to-primary-light rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Tips or cancel button */}
        <div className="flex flex-col items-center gap-4 mt-4">
          <p className="text-xs text-white/40 text-center max-w-[280px]">
            OCR 처리는 페이지 수와 복잡도에 따라 시간이 소요됩니다.
            <br />
            처리 중에는 다른 작업을 수행할 수 있습니다.
          </p>

          {onCancel && (
            <button
              onClick={onCancel}
              className="px-6 py-2 rounded-lg border border-white/20 text-white/70 text-sm font-medium hover:bg-white/10 hover:text-white transition-all duration-200"
            >
              백그라운드에서 계속
            </button>
          )}
        </div>

        {/* Decorative elements */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 pointer-events-none">
          <div className="absolute inset-0 border border-white/5 rounded-full animate-ping" style={{ animationDuration: '3s' }} />
          <div className="absolute inset-4 border border-white/5 rounded-full animate-ping" style={{ animationDuration: '3s', animationDelay: '1s' }} />
          <div className="absolute inset-8 border border-white/5 rounded-full animate-ping" style={{ animationDuration: '3s', animationDelay: '2s' }} />
        </div>
      </div>
    </div>
  )
}
