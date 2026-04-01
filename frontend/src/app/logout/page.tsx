'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function LogoutPage() {
  const router = useRouter()

  useEffect(() => {
    localStorage.removeItem('user')
    setTimeout(() => {
      router.replace('/login')
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
