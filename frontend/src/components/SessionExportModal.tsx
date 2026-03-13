'use client'

import { useState, useEffect } from 'react'
import { X, Loader2, FileText, Code, FileJson, FileSpreadsheet, Archive, Download, Files, Table } from 'lucide-react'

interface SessionExportModalProps {
  isOpen: boolean
  onClose: () => void
  sessionId: string
  sessionName: string
  selectedCount: number
  onExport: (formats: string[], asZip: boolean) => Promise<void>
}

type ExportFormat = 'pdf' | 'txt' | 'xml' | 'json' | 'excel'

const exportOptions: {
  value: ExportFormat
  title: string
  description: string
  icon: React.ReactNode
  color: string
  bgColor: string
}[] = [
  {
    value: 'pdf',
    title: 'PDF',
    description: '검색 가능한 PDF (Hidden Layer)',
    icon: <FileText className="w-6 h-6" />,
    color: 'text-red-500',
    bgColor: 'bg-red-500/10',
  },
  {
    value: 'txt',
    title: 'TXT',
    description: 'OCR 텍스트 추출',
    icon: <FileText className="w-6 h-6" />,
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-500/10',
  },
  {
    value: 'xml',
    title: 'XML',
    description: '좌표, 신뢰도 포함',
    icon: <Code className="w-6 h-6" />,
    color: 'text-orange-500',
    bgColor: 'bg-orange-500/10',
  },
  {
    value: 'excel',
    title: 'Excel',
    description: '페이지별 인식률 통계',
    icon: <FileSpreadsheet className="w-6 h-6" />,
    color: 'text-green-600',
    bgColor: 'bg-green-500/10',
  },
  {
    value: 'json',
    title: 'JSON',
    description: 'OCR 전체 데이터',
    icon: <FileJson className="w-6 h-6" />,
    color: 'text-yellow-600',
    bgColor: 'bg-yellow-500/10',
  },
]

export default function SessionExportModal({
  isOpen,
  onClose,
  sessionId,
  sessionName,
  selectedCount,
  onExport
}: SessionExportModalProps) {
  const [selectedFormats, setSelectedFormats] = useState<Set<ExportFormat>>(new Set(['pdf']))
  const [asZip, setAsZip] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setIsVisible(true)
    } else {
      const timer = setTimeout(() => setIsVisible(false), 200)
      return () => clearTimeout(timer)
    }
  }, [isOpen])

  if (!isVisible && !isOpen) return null

  const toggleFormat = (format: ExportFormat) => {
    setSelectedFormats(prev => {
      const newSet = new Set(prev)
      if (newSet.has(format)) {
        // Don't allow deselecting if it's the only one
        if (newSet.size > 1) {
          newSet.delete(format)
        }
      } else {
        newSet.add(format)
      }
      return newSet
    })
  }

  const handleExport = async () => {
    if (selectedFormats.size === 0) return

    try {
      setExporting(true)
      await onExport(Array.from(selectedFormats), asZip && selectedFormats.size > 1)
      onClose()
    } catch (error) {
      console.error('Export failed:', error)
      alert('내보내기에 실패했습니다.')
    } finally {
      setExporting(false)
    }
  }

  const needsPackaging = selectedFormats.size > 1 || selectedCount > 1

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-200 ${
        isOpen ? 'bg-black/50 backdrop-blur-sm' : 'bg-transparent pointer-events-none'
      }`}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className={`w-full max-w-lg rounded-2xl bg-surface-light dark:bg-surface-dark shadow-2xl flex flex-col overflow-hidden border border-border-light dark:border-border-dark max-h-[85vh] transition-all duration-200 ${
          isOpen ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border-light dark:border-border-dark">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <Download className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                세션 내보내기
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {sessionName} · {selectedCount}개 문서 선택됨
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={exporting}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {/* Format Selection */}
          <div className="mb-5">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <Files className="w-4 h-4 text-primary" />
              내보내기 형식 선택 (복수 선택 가능)
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {exportOptions.map(option => {
                const isSelected = selectedFormats.has(option.value)
                return (
                  <button
                    key={option.value}
                    onClick={() => toggleFormat(option.value)}
                    disabled={exporting}
                    className={`relative flex flex-col items-center p-4 rounded-xl border-2 transition-all duration-200 group ${
                      isSelected
                        ? 'border-primary bg-primary/5 dark:bg-primary/10 shadow-md'
                        : 'border-gray-200 dark:border-gray-700 hover:border-primary/50 hover:bg-gray-50 dark:hover:bg-gray-800'
                    }`}
                  >
                    {/* Selected indicator */}
                    {isSelected && (
                      <div className="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                        <svg className="w-3 h-3 text-white" fill="none" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" stroke="currentColor">
                          <path d="M5 13l4 4L19 7"></path>
                        </svg>
                      </div>
                    )}

                    <div className={`w-12 h-12 rounded-xl ${option.bgColor} flex items-center justify-center mb-2 transition-transform duration-200 group-hover:scale-110`}>
                      <span className={option.color}>{option.icon}</span>
                    </div>
                    <p className={`font-semibold text-sm ${
                      isSelected ? 'text-primary' : 'text-gray-900 dark:text-white'
                    }`}>
                      {option.title}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 text-center mt-1">
                      {option.description}
                    </p>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Packaging Option */}
          {needsPackaging && (
            <div className="mb-5">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                <Archive className="w-4 h-4 text-primary" />
                패키징 옵션
              </h3>
              <div className="flex gap-3">
                <button
                  onClick={() => setAsZip(true)}
                  disabled={exporting}
                  className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border-2 transition-all ${
                    asZip
                      ? 'border-primary bg-primary/5 dark:bg-primary/10'
                      : 'border-gray-200 dark:border-gray-700 hover:border-primary/50'
                  }`}
                >
                  <Archive className={`w-5 h-5 ${asZip ? 'text-primary' : 'text-gray-500'}`} />
                  <div className="text-left">
                    <p className={`font-medium text-sm ${asZip ? 'text-primary' : 'text-gray-900 dark:text-white'}`}>
                      ZIP 파일
                    </p>
                    <p className="text-xs text-gray-500">하나의 압축 파일로</p>
                  </div>
                </button>
                <button
                  onClick={() => setAsZip(false)}
                  disabled={exporting}
                  className={`flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border-2 transition-all ${
                    !asZip
                      ? 'border-primary bg-primary/5 dark:bg-primary/10'
                      : 'border-gray-200 dark:border-gray-700 hover:border-primary/50'
                  }`}
                >
                  <Files className={`w-5 h-5 ${!asZip ? 'text-primary' : 'text-gray-500'}`} />
                  <div className="text-left">
                    <p className={`font-medium text-sm ${!asZip ? 'text-primary' : 'text-gray-900 dark:text-white'}`}>
                      개별 파일
                    </p>
                    <p className="text-xs text-gray-500">각각 다운로드</p>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* Summary */}
          <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4">
            <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-2">내보내기 요약</h4>
            <ul className="text-xs text-gray-600 dark:text-gray-400 space-y-1">
              <li>• 선택된 문서: {selectedCount}개</li>
              <li>• 형식: {Array.from(selectedFormats).map(f => f.toUpperCase()).join(', ')}</li>
              {needsPackaging && (
                <li>• 패키징: {asZip ? 'ZIP 압축 파일' : '개별 파일 다운로드'}</li>
              )}
            </ul>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-5 border-t border-border-light dark:border-border-dark bg-gray-50 dark:bg-gray-800/50">
          <button
            onClick={onClose}
            disabled={exporting}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            취소
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || selectedFormats.size === 0}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-primary hover:bg-primary/90 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {exporting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                내보내는 중...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                내보내기
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
