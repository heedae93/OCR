'use client'

import Sidebar from '@/components/Sidebar'
import Dashboard from '@/components/Dashboard'
import ThemeToggle from '@/components/ThemeToggle'

export default function HomePage() {
  return (
    <div className="relative flex min-h-screen w-full bg-background-light dark:bg-background-dark">
      <Sidebar />

      <main className="flex-1 p-6 lg:p-10">
        <div className="w-full max-w-7xl mx-auto">
          <div className="flex flex-wrap justify-between items-start gap-4 mb-8">
            <div className="flex flex-col gap-2">
              <h1 className="text-text-primary-light dark:text-text-primary-dark text-3xl font-bold leading-tight tracking-tight">
                다시 오신 것을 환영합니다!
              </h1>
              <p className="text-text-secondary-light dark:text-text-secondary-dark text-base font-normal leading-normal">
                세션별로 PDF를 관리하고 빠르게 OCR 처리하세요.
              </p>
            </div>
            <ThemeToggle />
          </div>

          <Dashboard />
        </div>
      </main>
    </div>
  )
}
