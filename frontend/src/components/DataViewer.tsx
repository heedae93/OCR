'use client'

import { useState, useMemo } from 'react'
import { X, Download, Copy, Check, FileJson, FileCode } from 'lucide-react'
import { OCRResult } from '@/types'

interface DataViewerProps {
  isOpen: boolean
  onClose: () => void
  ocrResults: OCRResult | null
  jobId: string
}

type ViewMode = 'json' | 'xml'

export default function DataViewer({ isOpen, onClose, ocrResults, jobId }: DataViewerProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('json')
  const [copied, setCopied] = useState(false)

  // Generate JSON string
  const jsonContent = useMemo(() => {
    if (!ocrResults) return ''
    return JSON.stringify(ocrResults, null, 2)
  }, [ocrResults])

  // Generate XML string (simplified ABBYY-like format)
  const xmlContent = useMemo(() => {
    if (!ocrResults) return ''

    let xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<document>\n'
    xml += `  <pages count="${ocrResults.page_count}">\n`

    ocrResults.pages?.forEach((page) => {
      xml += `    <page number="${page.page_number}" width="${page.width}" height="${page.height}">\n`
      xml += '      <textBlocks>\n'

      page.lines?.forEach((line, idx) => {
        const [x1, y1, x2, y2] = line.bbox || [0, 0, 0, 0]
        const confidence = line.confidence || 0
        const escapedText = line.text
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')

        xml += `        <textBlock id="${idx + 1}">\n`
        xml += `          <rect l="${x1}" t="${y1}" r="${x2}" b="${y2}"/>\n`
        xml += `          <text confidence="${(confidence * 100).toFixed(1)}">${escapedText}</text>\n`

        // Character-level confidence if available
        if (line.char_confidences && line.char_confidences.length > 0) {
          xml += '          <charConfidences>\n'
          line.char_confidences.forEach((conf, charIdx) => {
            const char = line.text[charIdx] || ''
            const escapedChar = char
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
            xml += `            <char value="${escapedChar}" confidence="${(conf * 100).toFixed(1)}"/>\n`
          })
          xml += '          </charConfidences>\n'
        }

        xml += '        </textBlock>\n'
      })

      xml += '      </textBlocks>\n'
      xml += '    </page>\n'
    })

    xml += '  </pages>\n'
    xml += '</document>'

    return xml
  }, [ocrResults])

  const currentContent = viewMode === 'json' ? jsonContent : xmlContent

  const handleCopy = async () => {
    await navigator.clipboard.writeText(currentContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const blob = new Blob([currentContent], {
      type: viewMode === 'json' ? 'application/json' : 'application/xml'
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${jobId}_ocr.${viewMode}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-900 rounded-lg shadow-2xl w-[90vw] max-w-4xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              OCR 데이터 뷰어
            </h2>

            {/* View Mode Tabs */}
            <div className="flex bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
              <button
                onClick={() => setViewMode('json')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  viewMode === 'json'
                    ? 'bg-white dark:bg-gray-700 text-primary shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <FileJson className="w-4 h-4" />
                JSON
              </button>
              <button
                onClick={() => setViewMode('xml')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  viewMode === 'xml'
                    ? 'bg-white dark:bg-gray-700 text-primary shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <FileCode className="w-4 h-4" />
                XML
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
              {copied ? '복사됨' : '복사'}
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-primary hover:bg-primary/90 rounded-lg transition-colors"
            >
              <Download className="w-4 h-4" />
              다운로드
            </button>
            <button
              onClick={onClose}
              className="p-1.5 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {ocrResults ? (
            <pre className="text-xs font-mono text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-words">
              {currentContent}
            </pre>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              OCR 결과가 없습니다
            </div>
          )}
        </div>

        {/* Footer Stats */}
        <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 text-xs text-gray-500 dark:text-gray-400">
          <div className="flex items-center justify-between">
            <span>
              {ocrResults?.page_count || 0}페이지 | {ocrResults?.pages?.reduce((acc, p) => acc + (p.lines?.length || 0), 0) || 0}개 텍스트 블록
            </span>
            <span>
              {(currentContent.length / 1024).toFixed(1)} KB
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
