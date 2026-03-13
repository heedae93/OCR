'use client'

import { useCallback, useState, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { uploadFile } from '@/lib/api'
import { useRouter } from 'next/navigation'
import UploadOverlay, { UploadStage } from './UploadOverlay'

export default function UploadZone({ onUploadComplete }: { onUploadComplete?: () => void }) {
  const [showOverlay, setShowOverlay] = useState(false)
  const [uploadStage, setUploadStage] = useState<UploadStage>('uploading')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  const handleFileUpload = useCallback(async (file: File) => {
    setFileName(file.name)
    setShowOverlay(true)
    setUploadStage('uploading')
    setUploadProgress(0)
    setError(null)

    try {
      // Upload file with real progress tracking
      const { job_id } = await uploadFile(file, (progress) => {
        // Upload phase: 0-70%
        setUploadProgress(Math.round(progress * 0.7))
      })

      console.log('File uploaded, job ID:', job_id)

      // Processing phase: 70-95%
      setUploadStage('processing')
      setUploadProgress(75)

      // Simulate processing progress (server is converting pages)
      const processingInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 95) {
            clearInterval(processingInterval)
            return 95
          }
          return prev + 2
        })
      }, 200)

      // Small delay to show processing state
      await new Promise(resolve => setTimeout(resolve, 800))
      clearInterval(processingInterval)

      // Complete
      setUploadStage('complete')
      setUploadProgress(100)

      // Callback
      if (onUploadComplete) {
        onUploadComplete()
      }

      // Redirect after short delay to show completion
      await new Promise(resolve => setTimeout(resolve, 500))
      router.push(`/editor/${job_id}`)

    } catch (err: any) {
      console.error('Upload failed:', err)
      setUploadStage('error')
      setError(err.response?.data?.detail || err.message || '업로드에 실패했습니다.')

      // Hide overlay after showing error
      setTimeout(() => {
        setShowOverlay(false)
      }, 3000)
    }
  }, [onUploadComplete, router])

  // Handle clipboard paste
  useEffect(() => {
    const handlePaste = async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return

      for (let i = 0; i < items.length; i++) {
        const item = items[i]
        if (item.type.indexOf('image') !== -1) {
          const blob = item.getAsFile()
          if (blob) {
            const file = new File([blob], `pasted-image-${Date.now()}.png`, { type: blob.type })
            await handleFileUpload(file)
          }
        }
      }
    }

    window.addEventListener('paste', handlePaste)
    return () => window.removeEventListener('paste', handlePaste)
  }, [handleFileUpload])

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return
    const file = acceptedFiles[0]
    await handleFileUpload(file)
  }, [handleFileUpload])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
    },
    maxFiles: 1,
    disabled: showOverlay,
  })

  return (
    <>
      <div className="flex flex-col p-4 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark shadow-sm">
        <div
          {...getRootProps()}
          className={`flex flex-col items-center gap-6 rounded-lg border-2 border-dashed px-6 py-14 cursor-pointer transition-all duration-300 ${
            isDragActive
              ? 'border-primary bg-primary/5 scale-[1.02]'
              : showOverlay
              ? 'border-gray-300 dark:border-gray-600 opacity-50 cursor-not-allowed'
              : 'border-border-light dark:border-border-dark hover:border-primary/50 hover:bg-primary/5'
          }`}
        >
          <input {...getInputProps()} />

          <div className="text-primary">
            <span className="material-symbols-outlined !text-5xl">cloud_upload</span>
          </div>

          <div className="flex max-w-[480px] flex-col items-center gap-2">
            <p className="text-text-primary-light dark:text-text-primary-dark text-lg font-bold leading-tight tracking-[-0.015em] max-w-[480px] text-center">
              새 OCR 작업 시작
            </p>
            <p className="text-text-secondary-light dark:text-text-secondary-dark text-sm font-normal leading-normal max-w-[480px] text-center">
              {isDragActive
                ? '파일을 여기에 놓으세요'
                : '파일을 여기로 드래그 앤 드롭하거나 찾아보기로 검색 가능한 PDF로 변환을 시작하세요. 클립보드에서 이미지를 붙여넣기(Ctrl+V)할 수도 있습니다.'}
            </p>
          </div>

          <button className="flex min-w-[84px] max-w-[480px] cursor-pointer items-center justify-center overflow-hidden rounded-lg h-10 px-5 bg-primary text-white text-sm font-bold leading-normal tracking-wide hover:bg-primary/90 transition-colors">
            <span className="truncate">파일 찾아보기</span>
          </button>
        </div>
      </div>

      {/* Full-screen Upload Overlay */}
      <UploadOverlay
        isVisible={showOverlay}
        stage={uploadStage}
        progress={uploadProgress}
        fileName={fileName}
        errorMessage={error || undefined}
      />
    </>
  )
}
