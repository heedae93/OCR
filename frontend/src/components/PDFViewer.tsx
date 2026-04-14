'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { OCRResult } from '@/types'

interface MaskedBox {
  type: string
  value: string
  masked_value?: string
  page: number | null
  bbox: number[] | null
}

interface PDFViewerProps {
  pdfUrl: string
  currentPage: number
  onPageChange: (page: number) => void
  zoom?: number
  fitToWidth?: boolean
  onZoomChange?: (zoom: number) => void
  ocrResults?: OCRResult | null
  showTextLayer?: boolean
  showOCRComparison?: boolean
  showAccuracy?: boolean
  showMasking?: boolean
  maskingData?: MaskedBox[]
  highlightedLineIndex?: number | null
  children?: React.ReactNode
  onPageDimensionsChange?: (width: number, height: number) => void
}

export default function PDFViewer({
  pdfUrl,
  currentPage,
  onPageChange,
  zoom = 100,
  fitToWidth = false,
  onZoomChange,
  ocrResults,
  showTextLayer = false,
  showOCRComparison = false,
  showAccuracy = false,
  showMasking = false,
  maskingData = [],
  highlightedLineIndex = null,
  children,
  onPageDimensionsChange
}: PDFViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [pdf, setPdf] = useState<any>(null)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [pageWidth, setPageWidth] = useState(0)
  const [pageHeight, setPageHeight] = useState(0)
  const [pageLoading, setPageLoading] = useState(false)
  const [containerWidth, setContainerWidth] = useState(0)
  const [nativePageWidth, setNativePageWidth] = useState(0)

  // Page cache for faster navigation
  const pageCacheRef = useRef<Map<number, any>>(new Map())

  // Calculate effective zoom when fitToWidth is enabled
  const effectiveZoom = fitToWidth && containerWidth > 0 && nativePageWidth > 0
    ? Math.round((containerWidth - 64) / nativePageWidth * 100) // 64px for padding
    : zoom

  const scale = effectiveZoom / 100

  // Measure container width
  useEffect(() => {
    if (!containerRef.current) return

    const measureContainer = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.clientWidth)
      }
    }

    measureContainer()

    const resizeObserver = new ResizeObserver(measureContainer)
    resizeObserver.observe(containerRef.current)

    return () => resizeObserver.disconnect()
  }, [])

  // Notify parent of effective zoom when fitToWidth changes calculated zoom
  useEffect(() => {
    if (fitToWidth && onZoomChange && effectiveZoom !== zoom) {
      onZoomChange(effectiveZoom)
    }
  }, [fitToWidth, effectiveZoom, zoom, onZoomChange])

  useEffect(() => {
    let cancelled = false

    const loadPDF = async () => {
      try {
        setLoading(true)
        setLoadingProgress(0)

        // Always load PDF with PDF.js (we need it for rendering)
        const pdfjsLib = await import('pdfjs-dist')
        pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`

        // Optimized loading for large PDFs
        const loadingTask = pdfjsLib.getDocument({
          url: pdfUrl,
          // Don't fetch all data upfront - load on demand
          disableAutoFetch: true,
          // Enable streaming for faster initial load
          disableStream: false,
          // Smaller chunk size for faster first page
          rangeChunkSize: 65536 * 4, // 256KB chunks
        })

        // Track loading progress
        loadingTask.onProgress = (progress: { loaded: number; total: number }) => {
          if (progress.total > 0) {
            const percent = Math.round((progress.loaded / progress.total) * 100)
            setLoadingProgress(percent)
          }
        }

        const pdfDoc = await loadingTask.promise

        if (cancelled) return

        setPdf(pdfDoc)

        // For multi-page documents with OCR, use OCR page count
        // Otherwise use PDF page count
        const pageCount = (ocrResults && ocrResults.page_count > 1)
          ? ocrResults.page_count
          : pdfDoc.numPages

        console.log(`[PDFViewer] Loaded PDF: ${pdfDoc.numPages} pages, OCR: ${ocrResults?.page_count || 0} pages, using: ${pageCount}`)
        setTotalPages(pageCount)
        setLoading(false)

        // Clear page cache when PDF changes
        pageCacheRef.current.clear()
      } catch (error) {
        if (!cancelled) {
          console.error('PDF 로드 실패:', error)
          setLoading(false)
        }
      }
    }

    loadPDF()

    return () => {
      cancelled = true
    }
  }, [pdfUrl, ocrResults])

  useEffect(() => {
    if (!canvasRef.current || !pdf) return

    let cancelled = false
    let renderTask: any = null

    const renderPage = async () => {
      const canvas = canvasRef.current!
      const context = canvas.getContext('2d')!

      setPageLoading(true)

      try {
        // Check cache first
        let page = pageCacheRef.current.get(currentPage)
        if (!page) {
          page = await pdf.getPage(currentPage)
          // Cache the page for future use (limit cache size)
          if (pageCacheRef.current.size > 10) {
            // Remove oldest entries
            const firstKey = pageCacheRef.current.keys().next().value
            if (firstKey !== undefined) pageCacheRef.current.delete(firstKey)
          }
          pageCacheRef.current.set(currentPage, page)
        }

        if (cancelled) return

        // Get native dimensions (scale = 1.0) for fit-to-width calculation
        const nativeViewport = page.getViewport({ scale: 1, dontFlip: false })
        if (nativePageWidth !== nativeViewport.width) {
          setNativePageWidth(nativeViewport.width)
        }

        const viewport = page.getViewport({ scale, dontFlip: false })

        // Cancel any ongoing render task before starting a new one
        if (renderTask) {
          try {
            renderTask.cancel()
          } catch (e) {
            // Ignore cancellation errors
          }
        }

        canvas.height = viewport.height
        canvas.width = viewport.width

        if (cancelled) return

        // Update dimensions only if they changed to prevent infinite loop
        if (pageWidth !== viewport.width || pageHeight !== viewport.height) {
          setPageWidth(viewport.width)
          setPageHeight(viewport.height)

          // Notify parent of page dimensions
          if (onPageDimensionsChange) {
            onPageDimensionsChange(viewport.width, viewport.height)
          }
        }

        const renderContext = {
          canvasContext: context,
          viewport: viewport,
        }

        renderTask = page.render(renderContext)
        await renderTask.promise

        if (!cancelled) {
          renderTask = null
          setPageLoading(false)
        }

        // Prefetch adjacent pages
        const prefetchPages = [currentPage - 1, currentPage + 1].filter(p => p >= 1 && p <= totalPages)
        prefetchPages.forEach(async (pageNum) => {
          if (!pageCacheRef.current.has(pageNum)) {
            try {
              const prefetchPage = await pdf.getPage(pageNum)
              if (pageCacheRef.current.size <= 10) {
                pageCacheRef.current.set(pageNum, prefetchPage)
              }
            } catch (e) {
              // Ignore prefetch errors
            }
          }
        })
      } catch (error: any) {
        if (!cancelled && error?.name !== 'RenderingCancelledException') {
          console.error('페이지 렌더링 실패:', error)
        }
        setPageLoading(false)
      }
    }

    renderPage()

    return () => {
      cancelled = true
      if (renderTask) {
        try {
          renderTask.cancel()
        } catch (e) {
          // Ignore cancellation errors
        }
      }
    }
  }, [pdf, currentPage, effectiveZoom, scale, ocrResults, totalPages, nativePageWidth])

  // Get current page OCR data
  const currentPageOCR = ocrResults?.pages?.find(p => p.page_number === currentPage)

  // Debug: log page matching
  useEffect(() => {
    if (ocrResults) {
      console.log(`[PDFViewer] Current page: ${currentPage}, Total OCR pages: ${ocrResults.pages?.length || 0}`)
      console.log(`[PDFViewer] Found OCR data for page ${currentPage}:`, currentPageOCR ? 'YES' : 'NO')
      if (currentPageOCR) {
        console.log(`[PDFViewer] Page ${currentPage} has ${currentPageOCR.lines?.length || 0} lines`)
      }
    }
  }, [currentPage, ocrResults, currentPageOCR])

  // Calculate scale factor between OCR coordinates (from image) and display coordinates
  const getScaleFactor = () => {
    if (!currentPageOCR || !pageWidth || !pageHeight) return { scaleX: 1, scaleY: 1 }

    // OCR coordinates are from the original image dimensions (300 DPI)
    // Canvas is rendered by PDF.js at a specific scale
    // We need to match OCR image coordinates to canvas pixel coordinates
    const scaleX = pageWidth / currentPageOCR.width
    const scaleY = pageHeight / currentPageOCR.height

    console.log('Scale factors:', {
      scaleX,
      scaleY,
      canvasWidth: pageWidth,
      canvasHeight: pageHeight,
      ocrImageWidth: currentPageOCR.width,
      ocrImageHeight: currentPageOCR.height,
      'PDF zoom': zoom,
      'Scale': scale
    })

    return { scaleX, scaleY }
  }

  const { scaleX, scaleY } = getScaleFactor()

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full p-8 bg-background-light dark:bg-background-dark">
        {/* Document skeleton */}
        <div className="relative w-full max-w-2xl aspect-[3/4] bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden">
          {/* Shimmer effect */}
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-[shimmer_2s_infinite] -translate-x-full" style={{ animation: 'shimmer 2s infinite' }} />

          {/* Skeleton content */}
          <div className="p-8 space-y-4">
            {/* Header skeleton */}
            <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-3/4 animate-pulse" />
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2 animate-pulse" />

            {/* Content skeleton lines */}
            <div className="space-y-3 mt-8">
              {[95, 80, 100, 75, 90, 85, 70, 95, 78, 88, 72, 83].map((w, i) => (
                <div
                  key={i}
                  className="h-3 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"
                  style={{ width: `${w}%`, animationDelay: `${i * 0.1}s` }}
                />
              ))}
            </div>
          </div>

          {/* Center loading indicator */}
          <div className="absolute inset-0 flex items-center justify-center bg-black/5 dark:bg-white/5">
            <div className="flex flex-col items-center gap-4 bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-primary/30 rounded-full" />
                <div className="absolute inset-0 w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                {/* Progress percentage in center */}
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-sm font-bold text-primary">{loadingProgress}%</span>
                </div>
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">PDF 로딩 중</p>
                <p className="text-xs text-text-secondary-light dark:text-text-secondary-dark mt-1">
                  {loadingProgress < 100 ? `다운로드 중... ${loadingProgress}%` : '문서 준비 중...'}
                </p>
              </div>
              {/* Progress bar */}
              <div className="w-48 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${loadingProgress}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const pageStyle = pageWidth && pageHeight ? { width: `${pageWidth}px`, height: `${pageHeight}px` } : undefined

  return (
    <div
      ref={containerRef}
      className="flex flex-col items-center justify-start w-full h-full overflow-auto p-8 bg-background-light dark:bg-background-dark"
    >
      <div
        className="relative shadow-lg"
        style={{
          width: pageWidth ? `${pageWidth}px` : 'auto',
          height: pageHeight ? `${pageHeight}px` : 'auto'
        }}
      >
        <canvas
          ref={canvasRef}
          className="rounded-none"
        />

        {/* Page loading overlay */}
        {pageLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/50 dark:bg-gray-900/50 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-2">
              <div className="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-text-secondary-light dark:text-text-secondary-dark">
                페이지 {currentPage} 로딩 중...
              </span>
            </div>
          </div>
        )}

        {/* OCR Overlay */}
        {currentPageOCR && (showTextLayer || showOCRComparison || showAccuracy) && (
          <div
            ref={overlayRef}
            className="absolute top-0 left-0 pointer-events-none"
            style={{
              width: `${pageWidth}px`,
              height: `${pageHeight}px`
            }}
          >
            {(() => {
              const totalLines = currentPageOCR.lines?.length || 0
              const validLines = currentPageOCR.lines?.filter(l => l.bbox && l.bbox.length === 4).length || 0
              console.log(`[PDFViewer] Rendering ${validLines}/${totalLines} OCR boxes (page ${currentPage})`)
              return null
            })()}
            {currentPageOCR.lines?.map((line, idx) => {
              if (!line.bbox || line.bbox.length !== 4) {
                console.warn(`[PDFViewer] Skipping line ${idx}: invalid bbox`, line)
                return null
              }
              const [x1, y1, x2, y2] = line.bbox
              const x = x1 * scaleX
              const y = y1 * scaleY
              const width = (x2 - x1) * scaleX
              const height = (y2 - y1) * scaleY

              // Debug: log first 3 and last 3 boxes
              const totalLines = currentPageOCR.lines?.length || 0
              if (idx < 3 || idx >= totalLines - 3) {
                console.log(`Box ${idx}/${totalLines}: OCR[${x1},${y1},${x2},${y2}] -> Canvas[${x.toFixed(1)},${y.toFixed(1)},${width.toFixed(1)}x${height.toFixed(1)}] pageH=${pageHeight.toFixed(1)}`)
              }

              // Check if box is outside page bounds
              if (y > pageHeight || y + height < 0) {
                console.warn(`Box ${idx} OUT OF BOUNDS: y=${y.toFixed(1)}, pageHeight=${pageHeight.toFixed(1)}`)
              }

              // Calculate opacity based on confidence for accuracy visualization
              const confidence = line.confidence || 0.9
              const opacity = showAccuracy ? confidence : 0.3
              const isHighlighted = idx === highlightedLineIndex

              // Column information
              const column = line.column || null
              const isLeftColumn = column === 'left'
              const isRightColumn = column === 'right'

              // Color based on column and confidence
              let borderColor = 'rgba(124, 58, 237, 0.6)' // primary color (default)

              // Column-based coloring
              if (isLeftColumn) {
                borderColor = 'rgba(59, 130, 246, 0.7)' // blue for left column
              } else if (isRightColumn) {
                borderColor = 'rgba(139, 92, 246, 0.7)' // purple for right column
              }

              // Override with confidence-based color if accuracy mode is on
              if (showAccuracy) {
                if (confidence > 0.9) {
                  borderColor = 'rgba(34, 197, 94, 0.8)' // green
                } else if (confidence > 0.7) {
                  borderColor = 'rgba(234, 179, 8, 0.8)' // yellow
                } else {
                  borderColor = 'rgba(239, 68, 68, 0.8)' // red
                }
              }

              // Highlight color for selected line
              if (isHighlighted) {
                borderColor = 'rgba(255, 193, 7, 1)' // bright yellow/orange
              }

              return (
                <div key={idx}>
                  {/* Text layer bounding box */}
                  {showTextLayer && (
                    <div
                      className={`absolute border pointer-events-auto transition-all duration-200 ${isHighlighted ? 'animate-pulse' : ''}`}
                      style={{
                        left: `${x}px`,
                        top: `${y}px`,
                        width: `${width}px`,
                        height: `${height}px`,
                        borderColor: borderColor,
                        borderWidth: isHighlighted ? '3px' : '1px',
                        backgroundColor: isHighlighted ? 'rgba(255, 193, 7, 0.3)' : `${borderColor.replace('0.8', '0.1')}`,
                        boxShadow: isHighlighted ? '0 0 10px rgba(255, 193, 7, 0.6)' : 'none',
                        zIndex: isHighlighted ? 100 : 1,
                      }}
                      title={`${line.text}${column ? ` [${column}]` : ''} (신뢰도: ${(confidence * 100).toFixed(1)}%)`}
                    >
                      {/* Reading order number badge */}
                      <div
                        className="absolute -top-3 -left-3 bg-black/80 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center shadow-lg"
                        style={{
                          fontSize: '10px',
                          zIndex: 10,
                        }}
                      >
                        {idx + 1}
                      </div>
                      {/* Column badge */}
                      {column && (
                        <div
                          className="absolute -top-3 -right-3 text-white text-xs font-bold rounded px-1.5 py-0.5 shadow-lg"
                          style={{
                            backgroundColor: isLeftColumn ? 'rgb(59, 130, 246)' : 'rgb(139, 92, 246)',
                            fontSize: '9px',
                            zIndex: 10,
                          }}
                        >
                          {column === 'left' ? 'L' : 'R'}
                        </div>
                      )}
                    </div>
                  )}

                  {/* OCR comparison - show text */}
                  {showOCRComparison && (
                    <div
                      className="absolute text-xs pointer-events-auto overflow-hidden"
                      style={{
                        left: `${x}px`,
                        top: `${y}px`,
                        width: `${width}px`,
                        height: `${height}px`,
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        color: 'black',
                        padding: '2px',
                        fontSize: `${Math.max(8, height * 0.6)}px`,
                        lineHeight: `${height}px`,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {line.text}
                    </div>
                  )}

                  {/* Accuracy visualization */}
                  {showAccuracy && (
                    <div
                      className="absolute border-2 pointer-events-auto"
                      style={{
                        left: `${x}px`,
                        top: `${y}px`,
                        width: `${width}px`,
                        height: `${height}px`,
                        borderColor: borderColor,
                        backgroundColor: `${borderColor.replace('0.8', String(0.1 + opacity * 0.2))}`,
                      }}
                      title={`신뢰도: ${(confidence * 100).toFixed(1)}%`}
                    >
                      <div className="text-[8px] font-bold text-white bg-black/50 px-1">
                        {(confidence * 100).toFixed(0)}%
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Masking Overlay — 원본 텍스트 위치에 마스킹 텍스트를 자연스럽게 덮어씌움 */}
        {showMasking && maskingData && maskingData.length > 0 && (
          <div
            className="absolute top-0 left-0 pointer-events-none"
            style={{ width: `${pageWidth}px`, height: `${pageHeight}px` }}
          >
            {maskingData
              .filter(box => box.page === currentPage && box.bbox && box.bbox.length === 4)
              .map((box, idx) => {
                const [x1, y1, x2, y2] = box.bbox!
                const boxW = (x2 - x1) * scaleX
                const boxH = (y2 - y1) * scaleY
                const displayText = box.masked_value || '***'
                // 박스 높이의 65%를 폰트 크기로, 박스 너비 초과 시 줄여서 맞춤
                const fontSize = Math.max(8, boxH * 0.65)
                // OCR bbox 오차로 첫 글자 노출 방지: 왼쪽으로 여유 확보
                const leftPad = Math.max(4, boxH * 0.5)
                return (
                  <div
                    key={idx}
                    className="absolute overflow-hidden"
                    style={{
                      left: `${Math.max(0, x1 * scaleX - leftPad)}px`,
                      top: `${y1 * scaleY}px`,
                      width: `${boxW + leftPad}px`,
                      height: `${boxH}px`,
                      // 흰 배경으로 원본 텍스트(스캔 이미지)를 가림 — 박스처럼 보이지 않도록 border 없음
                      backgroundColor: 'white',
                      zIndex: 50,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                    title={`[${box.type}] ${box.value}`}
                  >
                    <span
                      style={{
                        fontSize: `${fontSize}px`,
                        lineHeight: 1,
                        color: '#111827',
                        fontFamily: '"Malgun Gothic", "Apple SD Gothic Neo", sans-serif',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        letterSpacing: '0.02em',
                      }}
                    >
                      {displayText}
                    </span>
                  </div>
                )
              })}
          </div>
        )}

        {/* Custom overlay content (e.g., TextEditor) */}
        {children}
      </div>
    </div>
  )
}
