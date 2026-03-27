'use client'

import { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  X,
  FileText,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  Trash2,
  Zap,
  Upload
} from 'lucide-react'

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5015'}/api`

type FileStatus = 'pending' | 'uploading' | 'processing' | 'completed' | 'failed'

interface QueueFile {
  id: string
  file: File
  status: FileStatus
  progress: number
  error?: string
  jobId?: string
}

interface Props {
  onClose: () => void
  onComplete: () => void
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function UploadQueueModal({ onClose, onComplete }: Props) {
  const [sessionName, setSessionName] = useState('')
  const [queue, setQueue] = useState<QueueFile[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isDone, setIsDone] = useState(false)

  const updateFile = (id: string, patch: Partial<QueueFile>) => {
    setQueue(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)))
  }

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (isRunning) return
      const newFiles: QueueFile[] = acceptedFiles.map(file => ({
        id: `${Date.now()}-${Math.random()}`,
        file,
        status: 'pending',
        progress: 0
      }))
      setQueue(prev => [...prev, ...newFiles])
    },
    [isRunning]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg']
    },
    multiple: true,
    disabled: isRunning
  })

  const removeFile = (id: string) => {
    setQueue(prev => prev.filter(f => f.id !== id))
  }

  const clearAll = () => {
    if (isRunning) return
    setQueue([])
  }

  const pollStatus = (jobId: string, fileId: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/status/${jobId}`)
          if (!res.ok) throw new Error('상태 조회 실패')
          const data = await res.json()
          const raw: number = data.progress_percent ?? 0
          const mapped = 50 + Math.round((raw / 100) * 50)
          updateFile(fileId, { progress: Math.min(mapped, 99) })

          if (data.status === 'completed') {
            clearInterval(interval)
            updateFile(fileId, { status: 'completed', progress: 100 })
            resolve()
          } else if (data.status === 'failed') {
            clearInterval(interval)
            updateFile(fileId, {
              status: 'failed',
              error: data.error_message || '처리 실패'
            })
            reject(new Error(data.error_message || '처리 실패'))
          }
        } catch (err) {
          clearInterval(interval)
          updateFile(fileId, { status: 'failed', error: String(err) })
          reject(err)
        }
      }, 2000)
    })
  }

  const startProcessing = async () => {
    const pendingFiles = queue.filter(f => f.status === 'pending')
    if (!sessionName.trim() || pendingFiles.length === 0) {
      alert('세션 이름과 파일을 입력해주세요.')
      return
    }

    setIsRunning(true)

    // 1. Create session
    let sessionId: string
    try {
      const sessionRes = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_name: sessionName, description: '' })
      })
      if (!sessionRes.ok) throw new Error('세션 생성 실패')
      const sessionData = await sessionRes.json()
      sessionId = sessionData.session_id
    } catch (err) {
      alert('세션 생성에 실패했습니다.')
      setIsRunning(false)
      return
    }

    // 2. Process files sequentially
    for (const qf of pendingFiles) {
      try {
        // a. Upload via XHR for progress
        updateFile(qf.id, { status: 'uploading', progress: 0 })

        const jobId = await new Promise<string>((resolve, reject) => {
          const xhr = new XMLHttpRequest()
          xhr.open('POST', `${API_BASE}/upload`)

          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              const pct = Math.round((e.loaded / e.total) * 50)
              updateFile(qf.id, { progress: pct })
            }
          }

          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                const data = JSON.parse(xhr.responseText)
                resolve(data.job_id)
              } catch {
                reject(new Error('응답 파싱 실패'))
              }
            } else {
              reject(new Error(`업로드 실패 (${xhr.status})`))
            }
          }

          xhr.onerror = () => reject(new Error('네트워크 오류'))

          const formData = new FormData()
          formData.append('file', qf.file)
          xhr.send(formData)
        })

        // b. Add document to session
        updateFile(qf.id, { status: 'processing', progress: 50, jobId })

        await fetch(`${API_BASE}/sessions/${sessionId}/documents`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId })
        })

        // c. Start OCR processing
        await fetch(`${API_BASE}/process/${jobId}`, { method: 'POST' })

        // d. Poll status
        await pollStatus(jobId, qf.id)
      } catch (err) {
        updateFile(qf.id, {
          status: 'failed',
          error: err instanceof Error ? err.message : '알 수 없는 오류'
        })
      }
    }

    setIsRunning(false)
    setIsDone(true)
    onComplete()
  }

  const pendingCount = queue.filter(f => f.status === 'pending').length
  const completedCount = queue.filter(f => f.status === 'completed').length
  const failedCount = queue.filter(f => f.status === 'failed').length
  const allDoneOrFailed = queue.length > 0 && queue.every(f => f.status === 'completed' || f.status === 'failed')

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-blue-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">파일 업로드 큐</h2>
          </div>
          <button
            onClick={onClose}
            disabled={isRunning}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Session name */}
        <div className="px-6 py-3 border-b border-gray-200 dark:border-gray-700">
          <input
            type="text"
            value={sessionName}
            onChange={e => setSessionName(e.target.value)}
            placeholder="세션 이름 입력 (예: 2024년 보고서 OCR)"
            disabled={isRunning}
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
          />
        </div>

        {/* Body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Dropzone */}
          <div className="w-64 flex-shrink-0 p-4 border-r border-gray-200 dark:border-gray-700 flex flex-col">
            <div
              {...getRootProps()}
              className={`
                flex-1 flex flex-col items-center justify-center rounded-xl border-2 border-dashed transition-colors cursor-pointer
                ${isRunning
                  ? 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/30 cursor-not-allowed opacity-50'
                  : isDragActive
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500 bg-gray-50 dark:bg-gray-800/50'
                }
              `}
            >
              <input {...getInputProps()} />
              <Upload className={`w-10 h-10 mb-3 ${isDragActive ? 'text-blue-500' : 'text-gray-400 dark:text-gray-500'}`} />
              {isDragActive ? (
                <p className="text-sm text-blue-600 dark:text-blue-400 text-center font-medium">파일을 놓으세요</p>
              ) : (
                <>
                  <p className="text-sm text-gray-600 dark:text-gray-400 text-center font-medium mb-1">
                    파일을 드래그하거나
                  </p>
                  <p className="text-sm text-blue-600 dark:text-blue-400 text-center">클릭하여 선택</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 text-center mt-3">
                    PDF, PNG, JPG 지원
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Right: Queue list */}
          <div className="flex-1 flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              {queue.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-500">
                  <FileText className="w-12 h-12 mb-3 opacity-40" />
                  <p className="text-sm">파일을 추가하세요</p>
                </div>
              ) : (
                <ul className="divide-y divide-gray-100 dark:divide-gray-800">
                  {queue.map(qf => (
                    <li key={qf.id} className="px-4 py-3">
                      <div className="flex items-start gap-3">
                        {/* Status icon */}
                        <div className="mt-0.5 flex-shrink-0">
                          {qf.status === 'pending' && (
                            <Clock className="w-5 h-5 text-gray-400" />
                          )}
                          {qf.status === 'uploading' && (
                            <Upload className="w-5 h-5 text-blue-500 animate-pulse" />
                          )}
                          {qf.status === 'processing' && (
                            <Loader2 className="w-5 h-5 text-orange-500 animate-spin" />
                          )}
                          {qf.status === 'completed' && (
                            <CheckCircle className="w-5 h-5 text-green-500" />
                          )}
                          {qf.status === 'failed' && (
                            <AlertCircle className="w-5 h-5 text-red-500" />
                          )}
                        </div>

                        {/* File info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {qf.file.name}
                            </p>
                            {qf.status === 'pending' && !isRunning && (
                              <button
                                onClick={() => removeFile(qf.id)}
                                className="flex-shrink-0 p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                            {formatBytes(qf.file.size)}
                            {qf.status === 'uploading' && ' · 업로드 중...'}
                            {qf.status === 'processing' && ' · OCR 처리 중...'}
                            {qf.status === 'completed' && ' · 완료'}
                          </p>

                          {/* Progress bar */}
                          {(qf.status === 'uploading' || qf.status === 'processing') && (
                            <div className="mt-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                              <div
                                className={`h-1.5 rounded-full transition-all duration-300 ${
                                  qf.status === 'uploading' ? 'bg-blue-500' : 'bg-orange-500'
                                }`}
                                style={{ width: `${qf.progress}%` }}
                              />
                            </div>
                          )}
                          {qf.status === 'completed' && (
                            <div className="mt-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                              <div className="h-1.5 rounded-full bg-green-500 w-full" />
                            </div>
                          )}

                          {/* Error */}
                          {qf.status === 'failed' && qf.error && (
                            <p className="text-xs text-red-500 mt-1">{qf.error}</p>
                          )}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Queue footer summary */}
            {queue.length > 0 && (
              <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 text-xs text-gray-500 dark:text-gray-400">
                대기 {pendingCount} / 완료 {completedCount} / 실패 {failedCount}
              </div>
            )}
          </div>
        </div>

        {/* Footer buttons */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
          <button
            onClick={clearAll}
            disabled={isRunning || queue.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            전체 지우기
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              disabled={isRunning}
              className="px-4 py-2 text-sm bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isDone || allDoneOrFailed ? '닫기' : '취소'}
            </button>
            <button
              onClick={startProcessing}
              disabled={isRunning || pendingCount === 0 || !sessionName.trim()}
              className="flex items-center gap-2 px-5 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {isRunning ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  처리 중...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  시작하기
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
