'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import {
  listDriveFiles,
  createFolder,
  uploadDriveFiles,
  deleteFiles,
  mergePDFs,
  splitPDF,
  downloadDriveFile,
  DriveItem,
} from '@/lib/api'
import { useDropzone } from 'react-dropzone'
import {
  FileText,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  Trash2,
  Zap,
  Upload,
  X,
} from 'lucide-react'

const API_BASE = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5015'}/api`

// ─── Upload Queue types ───────────────────────────────────────────────────────
type FileStatus = 'pending' | 'uploading' | 'processing' | 'completed' | 'failed'

interface QueueFile {
  id: string
  file: File
  status: FileStatus
  progress: number
  error?: string
  jobId?: string
  sourcePath?: string  // drive path if from drive
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ─── Main Page ────────────────────────────────────────────────────────────────
type ActiveTab = 'upload' | 'drive'

export default function OcrWorkPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('upload')

  return (
    <div className="relative flex min-h-screen w-full bg-background-light dark:bg-background-dark">
      <Sidebar />
      <main className="flex-1 flex flex-col p-6 lg:p-10 min-w-0">
        <div className="w-full max-w-7xl mx-auto flex flex-col flex-1">

          {/* Page Header */}
          <div className="mb-6">
            <h1 className="text-text-primary-light dark:text-text-primary-dark text-3xl font-bold leading-tight tracking-tight">
              OCR 작업하기
            </h1>
            <p className="text-text-secondary-light dark:text-text-secondary-dark text-base mt-1">
              파일을 직접 업로드하거나 드라이브에서 선택하여 OCR 처리를 시작하세요.
            </p>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-6 border-b border-border-light dark:border-border-dark">
            <button
              onClick={() => setActiveTab('upload')}
              className={`flex items-center gap-2 px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors -mb-px ${
                activeTab === 'upload'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-secondary-light dark:text-text-secondary-dark hover:text-text-primary-light dark:hover:text-text-primary-dark'
              }`}
            >
              <span className="material-symbols-outlined text-base">upload_file</span>
              직접 업로드
            </button>
            <button
              onClick={() => setActiveTab('drive')}
              className={`flex items-center gap-2 px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors -mb-px ${
                activeTab === 'drive'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-text-secondary-light dark:text-text-secondary-dark hover:text-text-primary-light dark:hover:text-text-primary-dark'
              }`}
            >
              <span className="material-symbols-outlined text-base">folder_open</span>
              드라이브 OCR
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1">
            {activeTab === 'upload' && <DirectUploadTab />}
            {activeTab === 'drive' && <DriveOcrTab />}
          </div>

        </div>
      </main>
    </div>
  )
}

// ─── Tab 1: 직접 업로드 ──────────────────────────────────────────────────────
function DirectUploadTab() {
  const [sessionName, setSessionName] = useState('')
  const [queue, setQueue] = useState<QueueFile[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const updateFile = (id: string, patch: Partial<QueueFile>) =>
    setQueue(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)))

  const fileToQueueItem = (file: File): QueueFile => ({
    id: `${Date.now()}-${Math.random()}`,
    file,
    status: 'pending',
    progress: 0,
  })

  const addFiles = useCallback((files: File[]) => {
    if (isRunning) return
    setQueue(prev => [...prev, ...files.map(fileToQueueItem)])
  }, [isRunning])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: addFiles,
    noClick: true,
    accept: {
      'application/pdf': ['.pdf'],
      'image/png': ['.png'],
      'image/jpeg': ['.jpg', '.jpeg'],
    },
  })

  const openFilePicker = async () => {
    if (isRunning) return
    try {
      const handles: FileSystemFileHandle[] = await (window as any).showOpenFilePicker({
        multiple: true,
        types: [{ description: 'OCR 지원 파일', accept: { 'application/pdf': ['.pdf'], 'image/png': ['.png'], 'image/jpeg': ['.jpg', '.jpeg'] } }],
      })
      const items: QueueFile[] = []
      for (const h of handles) items.push(fileToQueueItem(await h.getFile()))
      if (items.length) setQueue(prev => [...prev, ...items])
    } catch { /* cancelled */ }
  }

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(e.target.files || []))
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeFile = (id: string) => setQueue(prev => prev.filter(f => f.id !== id))
  const clearAll = () => { if (!isRunning) setQueue([]) }

  const pollStatus = (jobId: string, fileId: string): Promise<void> =>
    new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/status/${jobId}`)
          if (!res.ok) throw new Error('상태 조회 실패')
          const data = await res.json()
          const mapped = 50 + Math.round(((data.progress_percent ?? 0) / 100) * 50)
          updateFile(fileId, { progress: Math.min(mapped, 99) })
          if (data.status === 'completed') {
            clearInterval(interval)
            updateFile(fileId, { status: 'completed', progress: 100 })
            resolve()
          } else if (data.status === 'failed') {
            clearInterval(interval)
            updateFile(fileId, { status: 'failed', error: data.error_message || '처리 실패' })
            reject(new Error(data.error_message || '처리 실패'))
          }
        } catch (err) {
          clearInterval(interval)
          updateFile(fileId, { status: 'failed', error: String(err) })
          reject(err)
        }
      }, 2000)
    })

  const startProcessing = async () => {
    const pending = queue.filter(f => f.status === 'pending')
    if (!sessionName.trim() || pending.length === 0) {
      alert('세션 이름과 파일을 입력해주세요.')
      return
    }
    setIsRunning(true)
    setIsDone(false)

    let sessionId: string
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_name: sessionName, description: '' }),
      })
      if (!res.ok) throw new Error()
      sessionId = (await res.json()).session_id
    } catch {
      alert('세션 생성에 실패했습니다.')
      setIsRunning(false)
      return
    }

    for (const qf of pending) {
      try {
        updateFile(qf.id, { status: 'uploading', progress: 0 })
        const jobId = await new Promise<string>((resolve, reject) => {
          const xhr = new XMLHttpRequest()
          xhr.open('POST', `${API_BASE}/upload`)
          xhr.upload.onprogress = e => {
            if (e.lengthComputable)
              updateFile(qf.id, { progress: Math.round((e.loaded / e.total) * 50) })
          }
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try { resolve(JSON.parse(xhr.responseText).job_id) }
              catch { reject(new Error('응답 파싱 실패')) }
            } else {
              reject(new Error(`업로드 실패 (${xhr.status})`))
            }
          }
          xhr.onerror = () => reject(new Error('네트워크 오류'))
          const fd = new FormData()
          fd.append('file', qf.file)
          xhr.send(fd)
        })

        updateFile(qf.id, { status: 'processing', progress: 50, jobId })
        await fetch(`${API_BASE}/sessions/${sessionId}/documents`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId }),
        })
        await fetch(`${API_BASE}/process/${jobId}`, { method: 'POST' })
        await pollStatus(jobId, qf.id)
      } catch (err) {
        updateFile(qf.id, {
          status: 'failed',
          error: err instanceof Error ? err.message : '알 수 없는 오류',
        })
      }
    }

    setIsRunning(false)
    setIsDone(true)
  }

  const pendingCount = queue.filter(f => f.status === 'pending').length
  const completedCount = queue.filter(f => f.status === 'completed').length
  const failedCount = queue.filter(f => f.status === 'failed').length
  const hasFsApi = typeof window !== 'undefined' && 'showOpenFilePicker' in window

  return (
    <div className="flex flex-col lg:flex-row gap-6 h-full">

      {/* Left: Session + File Picker */}
      <div className="flex flex-col gap-4 lg:w-80 flex-shrink-0">
        {/* Session name */}
        <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-4">
          <label className="block text-sm font-semibold text-text-primary-light dark:text-text-primary-dark mb-2">
            세션 이름
          </label>
          <input
            type="text"
            value={sessionName}
            onChange={e => setSessionName(e.target.value)}
            placeholder="예: 2024년 보고서 OCR"
            disabled={isRunning}
            className={`w-full px-3 py-2 text-sm border rounded-lg bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-60 transition-colors ${
              !sessionName.trim() && pendingCount > 0
                ? 'border-orange-400 dark:border-orange-500'
                : 'border-border-light dark:border-border-dark'
            }`}
          />
          {!sessionName.trim() && pendingCount > 0 && (
            <p className="mt-1.5 text-xs text-orange-500">⚠ 세션 이름을 입력해야 시작됩니다</p>
          )}
        </div>

        {/* Drag & Drop Zone */}
        <div
          {...getRootProps()}
          className={`flex flex-col items-center justify-center gap-3 p-8 rounded-xl border-2 border-dashed transition-colors cursor-default ${
            isDragActive
              ? 'border-primary bg-primary/5'
              : 'border-border-light dark:border-border-dark bg-surface-light dark:bg-surface-dark hover:border-primary/50'
          }`}
        >
          <input {...getInputProps()} />
          <span className="material-symbols-outlined text-5xl text-text-secondary-light dark:text-text-secondary-dark">
            {isDragActive ? 'download' : 'cloud_upload'}
          </span>
          <p className="text-sm text-text-secondary-light dark:text-text-secondary-dark text-center">
            {isDragActive ? '여기에 놓으세요' : '파일을 드래그하여 놓거나\n아래 버튼으로 선택하세요'}
          </p>
          {hasFsApi ? (
            <button
              onClick={openFilePicker}
              disabled={isRunning}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary/90 disabled:opacity-40 transition-colors"
            >
              <Upload className="w-4 h-4" />
              파일 선택
            </button>
          ) : (
            <label className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-primary text-white rounded-lg hover:bg-primary/90 cursor-pointer transition-colors">
              <Upload className="w-4 h-4" />
              파일 선택
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg"
                className="hidden"
                onChange={handleFileInput}
                disabled={isRunning}
              />
            </label>
          )}
          <p className="text-xs text-text-secondary-light dark:text-text-secondary-dark">PDF · PNG · JPG 지원</p>
        </div>

        {/* Stats */}
        {queue.length > 0 && (
          <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-4 text-xs text-text-secondary-light dark:text-text-secondary-dark">
            전체 {queue.length} · 대기 {pendingCount} · 완료 {completedCount} · 실패 {failedCount}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2">
          <button
            onClick={startProcessing}
            disabled={isRunning || pendingCount === 0 || !sessionName.trim()}
            className="flex items-center justify-center gap-2 px-5 py-3 text-sm bg-primary hover:bg-primary/90 text-white rounded-xl disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-semibold"
          >
            {isRunning
              ? <><Loader2 className="w-4 h-4 animate-spin" />처리 중...</>
              : <><Zap className="w-4 h-4" />OCR 시작하기</>}
          </button>
          <button
            onClick={clearAll}
            disabled={isRunning || queue.length === 0}
            className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-text-secondary-light dark:text-text-secondary-dark hover:text-red-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            전체 지우기
          </button>
        </div>

        {isDone && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-sm text-green-700 dark:text-green-400">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            OCR 처리가 완료되었습니다.
          </div>
        )}
      </div>

      {/* Right: Queue list */}
      <div className="flex-1 bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark flex flex-col min-h-[400px]">
        {queue.length === 0 ? (
          <div className="flex flex-col items-center justify-center flex-1 py-20 text-text-secondary-light dark:text-text-secondary-dark">
            <FileText className="w-12 h-12 mb-3 opacity-20" />
            <p className="text-sm">파일을 선택하면 여기에 표시됩니다</p>
          </div>
        ) : (
          <ul className="divide-y divide-border-light dark:divide-border-dark overflow-y-auto">
            {queue.map(qf => (
              <li key={qf.id} className="px-5 py-4">
                <div className="flex items-center gap-3">
                  <div className="flex-shrink-0">
                    {qf.status === 'pending' && <Clock className="w-4 h-4 text-gray-400" />}
                    {qf.status === 'uploading' && <Upload className="w-4 h-4 text-blue-500 animate-pulse" />}
                    {qf.status === 'processing' && <Loader2 className="w-4 h-4 text-orange-500 animate-spin" />}
                    {qf.status === 'completed' && <CheckCircle className="w-4 h-4 text-green-500" />}
                    {qf.status === 'failed' && <AlertCircle className="w-4 h-4 text-red-500" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark truncate">{qf.file.name}</p>
                      {qf.status === 'pending' && !isRunning && (
                        <button onClick={() => removeFile(qf.id)} className="flex-shrink-0 p-0.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 transition-colors">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary-light dark:text-text-secondary-dark mt-0.5">
                      {formatBytes(qf.file.size)}
                      {qf.status === 'uploading' && ' · 업로드 중...'}
                      {qf.status === 'processing' && ' · OCR 처리 중...'}
                      {qf.status === 'completed' && ' · 완료'}
                    </p>
                    {(qf.status === 'uploading' || qf.status === 'processing') && (
                      <div className="mt-1.5 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full transition-all duration-300 ${qf.status === 'uploading' ? 'bg-blue-500' : 'bg-orange-500'}`}
                          style={{ width: `${qf.progress}%` }}
                        />
                      </div>
                    )}
                    {qf.status === 'completed' && (
                      <div className="mt-1.5 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                        <div className="h-1.5 rounded-full bg-green-500 w-full" />
                      </div>
                    )}
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
    </div>
  )
}

// ─── Tab 2: 드라이브 OCR ─────────────────────────────────────────────────────
function DriveOcrTab() {
  const router = useRouter()
  const [currentPath, setCurrentPath] = useState('')
  const [items, setItems] = useState<DriveItem[]>([])
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [uploading, setUploading] = useState(false)

  // OCR Queue state
  const [ocrQueue, setOcrQueue] = useState<QueueFile[]>([])
  const [isOcrRunning, setIsOcrRunning] = useState(false)
  const [ocrSessionName, setOcrSessionName] = useState('')
  const [ocrDone, setOcrDone] = useState(false)
  const [showOcrPanel, setShowOcrPanel] = useState(false)

  const fetchFiles = useCallback(async () => {
    try {
      setLoading(true)
      const data = await listDriveFiles(currentPath)
      setItems(data.items)
    } catch (error) {
      console.error('Failed to fetch files:', error)
    } finally {
      setLoading(false)
    }
  }, [currentPath])

  useEffect(() => { fetchFiles() }, [fetchFiles])

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return
    setUploading(true)
    try {
      await uploadDriveFiles(acceptedFiles, currentPath)
      await fetchFiles()
    } catch (error) {
      console.error('Upload failed:', error)
      alert('파일 업로드에 실패했습니다.')
    } finally {
      setUploading(false)
    }
  }, [currentPath, fetchFiles])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    noClick: true,
    noKeyboard: true,
  })

  const handleFolderClick = (item: DriveItem) => {
    if (item.type === 'folder') {
      setCurrentPath(item.path)
      setSelectedItems(new Set())
    }
  }

  const handleFileDoubleClick = (item: DriveItem) => {
    if (item.type === 'file' && item.is_ocr_processed) {
      const jobId = item.path.replace('.pdf', '')
      router.push(`/editor/${jobId}`)
    }
  }

  const handleItemSelect = (path: string) => {
    const newSelected = new Set(selectedItems)
    if (newSelected.has(path)) newSelected.delete(path)
    else newSelected.add(path)
    setSelectedItems(newSelected)
  }

  const handleSelectAll = () => {
    if (selectedItems.size === items.length) setSelectedItems(new Set())
    else setSelectedItems(new Set(items.map(item => item.path)))
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    try {
      await createFolder(newFolderName, currentPath)
      setShowNewFolderDialog(false)
      setNewFolderName('')
      await fetchFiles()
    } catch (error) {
      console.error('Failed to create folder:', error)
      alert('폴더 생성에 실패했습니다.')
    }
  }

  const handleDelete = async () => {
    if (selectedItems.size === 0) return
    if (!confirm(`${selectedItems.size}개의 항목을 삭제하시겠습니까?`)) return
    try {
      await deleteFiles(Array.from(selectedItems))
      setSelectedItems(new Set())
      await fetchFiles()
    } catch (error) {
      alert('삭제에 실패했습니다.')
    }
  }

  const handleMerge = async () => {
    const selectedPaths = Array.from(selectedItems)
    const pdfFiles = items.filter(item =>
      selectedPaths.includes(item.path) && item.type === 'file' && item.name.endsWith('.pdf')
    )
    if (pdfFiles.length < 2) { alert('병합할 PDF 파일을 2개 이상 선택해주세요.'); return }
    const outputName = prompt('병합된 PDF 파일 이름을 입력하세요:', 'merged.pdf')
    if (!outputName) return
    try {
      await mergePDFs(selectedPaths, outputName)
      setSelectedItems(new Set())
      await fetchFiles()
      alert('PDF 병합이 완료되었습니다.')
    } catch { alert('PDF 병합에 실패했습니다.') }
  }

  const handleSplit = async () => {
    if (selectedItems.size !== 1) { alert('분할할 PDF 파일을 1개만 선택해주세요.'); return }
    const path = Array.from(selectedItems)[0]
    const item = items.find(i => i.path === path)
    if (!item || item.type !== 'file' || !item.name.endsWith('.pdf')) { alert('PDF 파일을 선택해주세요.'); return }
    const input = prompt('페이지 범위를 입력하세요 (예: 1-5,6-10):')
    if (!input) return
    try {
      const ranges = input.split(',').map(range => {
        const [start, end] = range.trim().split('-').map(Number)
        return [start, end] as [number, number]
      })
      await splitPDF(path, ranges)
      setSelectedItems(new Set())
      await fetchFiles()
      alert('PDF 분할이 완료되었습니다.')
    } catch { alert('PDF 분할에 실패했습니다.') }
  }

  // OCR: 선택 파일 또는 폴더 내 파일을 큐에 추가하고 패널 열기
  const handleStartOcr = async () => {
    if (selectedItems.size === 0) return

    // Collect all file paths to process
    const filesToProcess: DriveItem[] = []

    for (const selectedPath of selectedItems) {
      const item = items.find(i => i.path === selectedPath)
      if (!item) continue

      if (item.type === 'folder') {
        // Get files inside the folder
        try {
          const folderData = await listDriveFiles(item.path)
          const folderFiles = folderData.items.filter(
            i => i.type === 'file' && (i.name.endsWith('.pdf') || i.name.endsWith('.png') || i.name.endsWith('.jpg') || i.name.endsWith('.jpeg'))
          )
          filesToProcess.push(...folderFiles)
        } catch { /* skip */ }
      } else if (
        item.type === 'file' &&
        (item.name.endsWith('.pdf') || item.name.endsWith('.png') || item.name.endsWith('.jpg') || item.name.endsWith('.jpeg'))
      ) {
        filesToProcess.push(item)
      }
    }

    if (filesToProcess.length === 0) {
      alert('OCR 처리 가능한 파일(PDF, PNG, JPG)이 없습니다.')
      return
    }

    // Build queue items (file content loaded on demand)
    const queueItems: QueueFile[] = filesToProcess.map(item => ({
      id: `${Date.now()}-${Math.random()}`,
      file: new File([], item.name),  // placeholder, real file fetched when processing
      status: 'pending',
      progress: 0,
      sourcePath: item.path,
    }))

    setOcrQueue(queueItems)
    setOcrSessionName('')
    setOcrDone(false)
    setShowOcrPanel(true)
  }

  const updateOcrFile = (id: string, patch: Partial<QueueFile>) =>
    setOcrQueue(prev => prev.map(f => (f.id === id ? { ...f, ...patch } : f)))

  const pollOcrStatus = (jobId: string, fileId: string): Promise<void> =>
    new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/status/${jobId}`)
          if (!res.ok) throw new Error('상태 조회 실패')
          const data = await res.json()
          const mapped = 50 + Math.round(((data.progress_percent ?? 0) / 100) * 50)
          updateOcrFile(fileId, { progress: Math.min(mapped, 99) })
          if (data.status === 'completed') {
            clearInterval(interval)
            updateOcrFile(fileId, { status: 'completed', progress: 100 })
            resolve()
          } else if (data.status === 'failed') {
            clearInterval(interval)
            updateOcrFile(fileId, { status: 'failed', error: data.error_message || '처리 실패' })
            reject(new Error(data.error_message || '처리 실패'))
          }
        } catch (err) {
          clearInterval(interval)
          updateOcrFile(fileId, { status: 'failed', error: String(err) })
          reject(err)
        }
      }, 2000)
    })

  const startDriveOcr = async () => {
    const pending = ocrQueue.filter(f => f.status === 'pending')
    if (!ocrSessionName.trim() || pending.length === 0) {
      alert('세션 이름을 입력해주세요.')
      return
    }
    setIsOcrRunning(true)
    setOcrDone(false)

    let sessionId: string
    try {
      const res = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_name: ocrSessionName, description: '' }),
      })
      if (!res.ok) throw new Error()
      sessionId = (await res.json()).session_id
    } catch {
      alert('세션 생성에 실패했습니다.')
      setIsOcrRunning(false)
      return
    }

    for (const qf of pending) {
      try {
        updateOcrFile(qf.id, { status: 'uploading', progress: 5 })

        // Download file from drive
        let realFile: File
        try {
          realFile = await downloadDriveFile(qf.sourcePath!)
        } catch {
          updateOcrFile(qf.id, { status: 'failed', error: '드라이브 파일 다운로드 실패' })
          continue
        }

        updateOcrFile(qf.id, { file: realFile, progress: 10 })

        const jobId = await new Promise<string>((resolve, reject) => {
          const xhr = new XMLHttpRequest()
          xhr.open('POST', `${API_BASE}/upload`)
          xhr.upload.onprogress = e => {
            if (e.lengthComputable)
              updateOcrFile(qf.id, { progress: 10 + Math.round((e.loaded / e.total) * 40) })
          }
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try { resolve(JSON.parse(xhr.responseText).job_id) }
              catch { reject(new Error('응답 파싱 실패')) }
            } else {
              reject(new Error(`업로드 실패 (${xhr.status})`))
            }
          }
          xhr.onerror = () => reject(new Error('네트워크 오류'))
          const fd = new FormData()
          fd.append('file', realFile)
          xhr.send(fd)
        })

        updateOcrFile(qf.id, { status: 'processing', progress: 50, jobId })
        await fetch(`${API_BASE}/sessions/${sessionId}/documents`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId }),
        })
        await fetch(`${API_BASE}/process/${jobId}`, { method: 'POST' })
        await pollOcrStatus(jobId, qf.id)
      } catch (err) {
        updateOcrFile(qf.id, {
          status: 'failed',
          error: err instanceof Error ? err.message : '알 수 없는 오류',
        })
      }
    }

    setIsOcrRunning(false)
    setOcrDone(true)
    await fetchFiles()
  }

  const getBreadcrumbs = () => {
    if (!currentPath) return [{ name: '드라이브', path: '' }]
    const parts = currentPath.split('/')
    const breadcrumbs = [{ name: '드라이브', path: '' }]
    parts.forEach((part, index) => {
      breadcrumbs.push({ name: part, path: parts.slice(0, index + 1).join('/') })
    })
    return breadcrumbs
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '--'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
  }

  const formatDate = (isoDate: string) => {
    const date = new Date(isoDate)
    return date.toLocaleString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const ocrPending = ocrQueue.filter(f => f.status === 'pending').length
  const ocrCompleted = ocrQueue.filter(f => f.status === 'completed').length
  const ocrFailed = ocrQueue.filter(f => f.status === 'failed').length

  return (
    <div className="flex flex-col lg:flex-row gap-6">

      {/* Drive browser */}
      <div className="flex-1 min-w-0" {...getRootProps()}>
        <input {...getInputProps()} />

        {/* Drive header */}
        <div className="flex flex-wrap justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            {getBreadcrumbs().map((crumb, index) => (
              <div key={crumb.path} className="flex items-center gap-2">
                {index > 0 && (
                  <span className="material-symbols-outlined text-text-secondary-light dark:text-text-secondary-dark text-sm">chevron_right</span>
                )}
                <button
                  onClick={() => { setCurrentPath(crumb.path); setSelectedItems(new Set()) }}
                  className="text-sm text-text-primary-light dark:text-text-primary-dark hover:text-primary font-medium"
                >
                  {crumb.name}
                </button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <label className="flex h-9 cursor-pointer items-center justify-center gap-2 rounded-lg bg-primary px-3 text-sm font-semibold text-white hover:bg-primary/90">
              <span className="material-symbols-outlined text-lg">cloud_upload</span>
              파일 업로드
              <input type="file" multiple className="hidden" onChange={e => { if (e.target.files) { onDrop(Array.from(e.target.files)); e.target.value = '' } }} />
            </label>
            <button
              onClick={() => setShowNewFolderDialog(true)}
              className="flex h-9 items-center gap-2 rounded-lg bg-primary/10 px-3 text-sm font-semibold text-primary hover:bg-primary/20"
            >
              <span className="material-symbols-outlined text-lg">create_new_folder</span>
              새 폴더
            </button>
          </div>
        </div>

        {/* Toolbar */}
        {selectedItems.size > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg bg-primary/10 dark:bg-primary/20 p-3">
            <span className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">{selectedItems.size}개 선택됨</span>
            <div className="h-4 w-px bg-border-light dark:bg-border-dark" />
            <button
              onClick={handleStartOcr}
              className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-white text-sm font-semibold hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-base">document_scanner</span>
              OCR 작업 시작
            </button>
            <button onClick={handleMerge} className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-white dark:bg-surface-dark hover:bg-gray-100 dark:hover:bg-gray-700 text-sm">
              <span className="material-symbols-outlined text-base">merge</span>병합
            </button>
            <button onClick={handleSplit} className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-white dark:bg-surface-dark hover:bg-gray-100 dark:hover:bg-gray-700 text-sm">
              <span className="material-symbols-outlined text-base">call_split</span>분할
            </button>
            <button onClick={handleDelete} className="flex items-center gap-1 px-3 py-1.5 rounded-md bg-red-500 hover:bg-red-600 text-white text-sm">
              <span className="material-symbols-outlined text-base">delete</span>삭제
            </button>
          </div>
        )}

        {/* File list */}
        <div className="relative bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark shadow-sm">
          {isDragActive && (
            <div className="absolute inset-0 bg-primary/10 border-2 border-dashed border-primary rounded-xl flex items-center justify-center z-10">
              <div className="text-center">
                <span className="material-symbols-outlined text-6xl text-primary">cloud_upload</span>
                <p className="text-xl font-bold text-primary mt-2">파일을 여기에 놓으세요</p>
              </div>
            </div>
          )}

          {uploading ? (
            <div className="flex items-center justify-center py-20">
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                <p className="text-text-secondary-light dark:text-text-secondary-dark text-sm">업로드 중...</p>
              </div>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="flex flex-col items-center gap-2">
                <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                <p className="text-text-secondary-light dark:text-text-secondary-dark text-sm">로딩 중...</p>
              </div>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-text-secondary-light dark:text-text-secondary-dark">
              <span className="material-symbols-outlined text-6xl mb-4">folder_open</span>
              <p className="text-lg font-medium">폴더가 비어있습니다</p>
              <p className="text-sm mt-2">파일을 업로드하거나 폴더를 생성하세요</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead className="border-b border-border-light dark:border-border-dark">
                  <tr>
                    <th className="px-4 py-3 w-12">
                      <input type="checkbox" checked={selectedItems.size === items.length && items.length > 0} onChange={handleSelectAll} className="w-4 h-4 text-primary rounded" />
                    </th>
                    <th className="px-4 py-3 text-xs font-semibold text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">이름</th>
                    <th className="px-4 py-3 text-xs font-semibold text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider hidden md:table-cell">수정한 날짜</th>
                    <th className="px-4 py-3 text-xs font-semibold text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider hidden sm:table-cell">크기</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-light dark:divide-border-dark">
                  {items.map(item => (
                    <tr
                      key={item.path}
                      className={`hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer ${selectedItems.has(item.path) ? 'bg-primary/5 dark:bg-primary/10' : ''}`}
                    >
                      <td className="px-4 py-3">
                        <input type="checkbox" checked={selectedItems.has(item.path)} onChange={() => handleItemSelect(item.path)} onClick={e => e.stopPropagation()} className="w-4 h-4 text-primary rounded" />
                      </td>
                      <td className="px-4 py-3" onClick={() => handleFolderClick(item)} onDoubleClick={() => handleFileDoubleClick(item)}>
                        <div className="flex items-center gap-3">
                          <span className={`material-symbols-outlined ${item.type === 'folder' ? 'text-yellow-500' : 'text-primary'}`}>
                            {item.type === 'folder' ? 'folder' : 'description'}
                          </span>
                          <span className="text-text-primary-light dark:text-text-primary-dark text-sm font-medium">{item.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-text-secondary-light dark:text-text-secondary-dark hidden md:table-cell">{formatDate(item.modified)}</td>
                      <td className="px-4 py-3 text-sm text-text-secondary-light dark:text-text-secondary-dark hidden sm:table-cell">{formatFileSize(item.size)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* OCR Queue Panel */}
      {showOcrPanel && (
        <div className="lg:w-80 flex-shrink-0 flex flex-col gap-3">
          <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark flex flex-col">
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border-light dark:border-border-dark">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-primary text-lg">document_scanner</span>
                <span className="text-sm font-semibold text-text-primary-light dark:text-text-primary-dark">OCR 처리 큐</span>
                {isOcrRunning && <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />}
              </div>
              {!isOcrRunning && (
                <button onClick={() => setShowOcrPanel(false)} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400">
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Session name input */}
            <div className="px-4 py-3 border-b border-border-light dark:border-border-dark">
              <input
                type="text"
                value={ocrSessionName}
                onChange={e => setOcrSessionName(e.target.value)}
                placeholder="세션 이름 입력"
                disabled={isOcrRunning}
                className="w-full px-3 py-2 text-sm border border-border-light dark:border-border-dark rounded-lg bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-60"
              />
            </div>

            {/* Queue list */}
            <div className="overflow-y-auto max-h-80">
              <ul className="divide-y divide-border-light dark:divide-border-dark">
                {ocrQueue.map(qf => (
                  <li key={qf.id} className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-shrink-0">
                        {qf.status === 'pending' && <Clock className="w-3.5 h-3.5 text-gray-400" />}
                        {qf.status === 'uploading' && <Upload className="w-3.5 h-3.5 text-blue-500 animate-pulse" />}
                        {qf.status === 'processing' && <Loader2 className="w-3.5 h-3.5 text-orange-500 animate-spin" />}
                        {qf.status === 'completed' && <CheckCircle className="w-3.5 h-3.5 text-green-500" />}
                        {qf.status === 'failed' && <AlertCircle className="w-3.5 h-3.5 text-red-500" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-text-primary-light dark:text-text-primary-dark truncate">{qf.file.name || qf.sourcePath?.split('/').pop()}</p>
                        {(qf.status === 'uploading' || qf.status === 'processing') && (
                          <div className="mt-1 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1">
                            <div
                              className={`h-1 rounded-full transition-all duration-300 ${qf.status === 'uploading' ? 'bg-blue-500' : 'bg-orange-500'}`}
                              style={{ width: `${qf.progress}%` }}
                            />
                          </div>
                        )}
                        {qf.status === 'completed' && (
                          <div className="mt-1 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1">
                            <div className="h-1 rounded-full bg-green-500 w-full" />
                          </div>
                        )}
                        {qf.status === 'failed' && qf.error && (
                          <p className="text-xs text-red-500 mt-0.5">{qf.error}</p>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            {/* Stats + Start button */}
            <div className="px-4 py-2 border-t border-border-light dark:border-border-dark text-xs text-text-secondary-light dark:text-text-secondary-dark">
              전체 {ocrQueue.length} · 대기 {ocrPending} · 완료 {ocrCompleted} · 실패 {ocrFailed}
            </div>

            {ocrDone && (
              <div className="mx-4 mb-2 flex items-center gap-2 p-2 rounded-lg bg-green-50 dark:bg-green-900/20 text-xs text-green-700 dark:text-green-400">
                <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
                OCR 처리 완료!
              </div>
            )}

            <div className="px-4 pb-4">
              <button
                onClick={startDriveOcr}
                disabled={isOcrRunning || ocrPending === 0 || !ocrSessionName.trim()}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm bg-primary hover:bg-primary/90 text-white rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-semibold"
              >
                {isOcrRunning
                  ? <><Loader2 className="w-4 h-4 animate-spin" />처리 중...</>
                  : <><Zap className="w-4 h-4" />OCR 시작하기</>}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-surface-light dark:bg-surface-dark shadow-2xl p-6">
            <h2 className="text-xl font-bold text-text-primary-light dark:text-text-primary-dark mb-4">새 폴더 만들기</h2>
            <input
              type="text"
              value={newFolderName}
              onChange={e => setNewFolderName(e.target.value)}
              onKeyPress={e => e.key === 'Enter' && handleCreateFolder()}
              placeholder="폴더 이름"
              className="w-full rounded-lg border border-border-light dark:border-border-dark bg-background-light dark:bg-background-dark px-4 py-3 text-text-primary-light dark:text-text-primary-dark focus:outline-none focus:ring-2 focus:ring-primary"
              autoFocus
            />
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => { setShowNewFolderDialog(false); setNewFolderName('') }}
                className="flex-1 rounded-lg px-4 py-2 bg-gray-200 dark:bg-surface-dark hover:bg-gray-300 dark:hover:bg-gray-700 text-text-primary-light dark:text-text-primary-dark font-medium"
              >
                취소
              </button>
              <button
                onClick={handleCreateFolder}
                className="flex-1 rounded-lg px-4 py-2 bg-primary hover:bg-primary/90 text-white font-bold"
              >
                만들기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
