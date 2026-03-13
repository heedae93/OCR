'use client'

import { useEffect, useState } from 'react'

export type UploadStage = 'uploading' | 'processing' | 'complete' | 'error'

interface UploadOverlayProps {
  isVisible: boolean
  stage: UploadStage
  progress: number
  fileName: string
  errorMessage?: string
}

export default function UploadOverlay({
  isVisible,
  stage,
  progress,
  fileName,
  errorMessage
}: UploadOverlayProps) {
  const [animatedProgress, setAnimatedProgress] = useState(0)

  // Smooth progress animation
  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedProgress(progress)
    }, 50)
    return () => clearTimeout(timer)
  }, [progress])

  if (!isVisible) return null

  const getStageInfo = () => {
    switch (stage) {
      case 'uploading':
        return {
          icon: 'cloud_upload',
          title: '파일 업로드 중',
          subtitle: '서버로 파일을 전송하고 있습니다...',
          color: 'text-primary'
        }
      case 'processing':
        return {
          icon: 'settings',
          title: '파일 처리 중',
          subtitle: '페이지를 분석하고 미리보기를 생성하고 있습니다...',
          color: 'text-orange-500'
        }
      case 'complete':
        return {
          icon: 'check_circle',
          title: '완료!',
          subtitle: '에디터로 이동합니다...',
          color: 'text-green-500'
        }
      case 'error':
        return {
          icon: 'error',
          title: '오류 발생',
          subtitle: errorMessage || '업로드에 실패했습니다.',
          color: 'text-red-500'
        }
    }
  }

  const stageInfo = getStageInfo()
  const displayProgress = stage === 'complete' ? 100 : animatedProgress

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center">
      {/* Backdrop with strong blur */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-lg" />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-6 p-8 max-w-md w-full mx-4">
        {/* Main progress card */}
        <div className="w-full bg-white dark:bg-gray-800 rounded-2xl shadow-2xl p-8 flex flex-col items-center gap-6">
          {/* Animated icon */}
          <div className={`relative ${stage === 'processing' ? 'animate-spin' : ''}`} style={{ animationDuration: '2s' }}>
            <div className={`w-20 h-20 rounded-full flex items-center justify-center ${
              stage === 'uploading' ? 'bg-primary/10' :
              stage === 'processing' ? 'bg-orange-500/10' :
              stage === 'complete' ? 'bg-green-500/10' :
              'bg-red-500/10'
            }`}>
              <span className={`material-symbols-outlined !text-4xl ${stageInfo.color} ${
                stage === 'complete' ? 'fill' : ''
              }`}>
                {stageInfo.icon}
              </span>
            </div>
            {/* Pulse ring for uploading */}
            {stage === 'uploading' && (
              <div className="absolute inset-0 rounded-full border-4 border-primary/30 animate-ping" />
            )}
          </div>

          {/* Progress percentage */}
          <div className="text-center">
            <div className="text-5xl font-bold text-gray-900 dark:text-white mb-2">
              {displayProgress}%
            </div>
            <h2 className={`text-lg font-semibold ${stageInfo.color}`}>
              {stageInfo.title}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {stageInfo.subtitle}
            </p>
          </div>

          {/* Progress bar */}
          <div className="w-full">
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ease-out ${
                  stage === 'uploading' ? 'bg-gradient-to-r from-primary to-primary-light' :
                  stage === 'processing' ? 'bg-gradient-to-r from-orange-500 to-yellow-500' :
                  stage === 'complete' ? 'bg-gradient-to-r from-green-500 to-emerald-400' :
                  'bg-red-500'
                }`}
                style={{ width: `${displayProgress}%` }}
              />
            </div>
          </div>

          {/* File name */}
          <div className="flex items-center gap-2 px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg max-w-full">
            <span className="material-symbols-outlined text-gray-500 dark:text-gray-400 text-lg">
              description
            </span>
            <span className="text-sm text-gray-700 dark:text-gray-300 truncate">
              {fileName}
            </span>
          </div>
        </div>

        {/* Tips */}
        <p className="text-xs text-white/60 text-center">
          대용량 파일은 처리 시간이 더 소요될 수 있습니다.
        </p>
      </div>
    </div>
  )
}
