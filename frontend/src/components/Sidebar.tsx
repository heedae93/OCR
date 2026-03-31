'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

interface NavItem {
  href: string
  icon: string
  label: string
  badge?: string | number
}

const navItems: NavItem[] = [
  { href: '/', icon: 'dashboard', label: '대시보드' },
  { href: '/ocr-work', icon: 'document_scanner', label: 'OCR 작업하기' },
  { href: '/jobs', icon: 'history', label: '작업 내역' },
  // { href: '/drive', icon: 'folder', label: '내 드라이브' },
  { href: '/settings', icon: 'settings', label: '설정' },
  { href: '/help', icon: 'help', label: '도움말' },
]

export default function Sidebar() {
  const pathname = usePathname()

  const isActive = (path: string) => pathname === path

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border-light dark:border-border-dark bg-surface-light dark:bg-surface-dark sticky top-0">
      <div className="flex flex-col gap-4 p-4 h-full">
        {/* Logo */}
        <Link href="/" className="flex gap-3 items-center px-2 py-3 rounded-xl hover:bg-black/5 dark:hover:bg-white/5 transition-all duration-200 group">
          <div className="bg-gradient-to-br from-primary to-primary/70 rounded-xl size-10 flex items-center justify-center shadow-lg shadow-primary/20 group-hover:shadow-primary/30 transition-shadow duration-200">
            <span className="material-symbols-outlined text-white !text-xl">document_scanner</span>
          </div>
          <div className="flex flex-col">
            <h1 className="text-text-primary-light dark:text-text-primary-dark text-base font-bold leading-tight tracking-tight">
              Futurenuri
            </h1>
            <p className="text-primary text-xs font-semibold tracking-wider uppercase">
              PDFix
            </p>
          </div>
        </Link>

        {/* Divider */}
        <div className="h-px bg-gradient-to-r from-transparent via-border-light dark:via-border-dark to-transparent mx-2" />

        {/* Navigation */}
        <nav className="flex flex-col gap-1 mt-2 flex-grow">
          {navItems.map((item) => {
            const active = isActive(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 group relative overflow-hidden ${
                  active
                    ? 'bg-primary/10 dark:bg-primary/15 text-primary'
                    : 'hover:bg-black/5 dark:hover:bg-white/5 text-text-secondary-light dark:text-text-secondary-dark hover:text-text-primary-light dark:hover:text-text-primary-dark'
                }`}
              >
                {/* Active indicator */}
                {active && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-primary rounded-r-full" />
                )}
                <span className={`material-symbols-outlined text-xl transition-all duration-200 ${
                  active ? 'text-primary' : 'group-hover:scale-110'
                } ${active ? 'fill' : ''}`}>
                  {item.icon}
                </span>
                <span className={`text-sm transition-all duration-200 ${
                  active ? 'font-semibold' : 'font-medium'
                }`}>
                  {item.label}
                </span>
                {item.badge && (
                  <span className="ml-auto px-2 py-0.5 text-xs font-semibold bg-primary/20 text-primary rounded-full">
                    {item.badge}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        {/* Quick Stats Card */}
        <div className="mx-1 p-3 rounded-xl bg-gradient-to-br from-primary/5 to-primary/10 border border-primary/10">
          <div className="flex items-center gap-2 mb-2">
            <span className="material-symbols-outlined text-primary !text-lg">insights</span>
            <span className="text-xs font-semibold text-primary">오늘의 처리량</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">0</span>
            <span className="text-xs text-text-secondary-light dark:text-text-secondary-dark">파일</span>
          </div>
        </div>

        {/* User Info */}
        <div className="flex flex-col gap-1 border-t border-border-light dark:border-border-dark pt-4">
          <div className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-black/5 dark:hover:bg-white/5 transition-all duration-200 cursor-pointer">
            <div className="relative">
              <div className="bg-gradient-to-br from-primary to-primary/70 rounded-full size-9 flex items-center justify-center text-white font-semibold text-sm shadow-md">
                U
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-green-500 rounded-full border-2 border-surface-light dark:border-surface-dark" />
            </div>
            <div className="flex flex-col flex-1 min-w-0">
              <p className="text-text-primary-light dark:text-text-primary-dark text-sm font-semibold leading-tight truncate">
                사용자
              </p>
              <p className="text-text-secondary-light dark:text-text-secondary-dark text-xs truncate">
                user@email.com
              </p>
            </div>
            <span className="material-symbols-outlined text-text-secondary-light dark:text-text-secondary-dark text-lg">
              expand_more
            </span>
          </div>
        </div>
      </div>
    </aside>
  )
}
