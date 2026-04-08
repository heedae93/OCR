'use client'

import Sidebar from '@/components/Sidebar'

export default function StatisticsPage() {
  return (
    <div className="relative flex min-h-screen w-full bg-background-light dark:bg-background-dark">
      <Sidebar />
      <div className="flex flex-col gap-6 p-8 flex-1">
        <h1 className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">통계</h1>
        <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark p-8 text-center">
          <span className="material-symbols-outlined text-4xl text-text-secondary-light dark:text-text-secondary-dark">bar_chart</span>
          <p className="mt-4 text-text-secondary-light dark:text-text-secondary-dark">준비 중입니다.</p>
        </div>
      </div>
    </div>
  )
}
