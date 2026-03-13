'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function LogoutPage() {
  const router = useRouter()

  useEffect(() => {
    // 로그아웃 로직 (현재는 단순히 홈으로 리다이렉트)
    setTimeout(() => {
      router.push('/')
    }, 1000)
  }, [router])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background-light dark:bg-background-dark">
      <div className="text-center">
        <span className="material-symbols-outlined text-6xl text-primary mb-4 inline-block">
          logout
        </span>
        <p className="text-text-primary-light dark:text-text-primary-dark text-xl">
          로그아웃 중...
        </p>
      </div>
    </div>
  )
}
