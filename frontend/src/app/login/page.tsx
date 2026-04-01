'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { API_BASE_URL } from '@/lib/api'

export default function LoginPage() {
  const router = useRouter()
  const [form, setForm] = useState({ username: '', password: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setForm(prev => ({ ...prev, [name]: value }))
    setErrors(prev => ({ ...prev, [name]: '' }))
  }

  const validate = () => {
    const newErrors: Record<string, string> = {}
    if (!form.username.trim()) newErrors.username = '아이디를 입력해주세요.'
    if (!form.password) newErrors.password = '비밀번호를 입력해주세요.'
    return newErrors
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const newErrors = validate()
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: form.username, password: form.password }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || '로그인에 실패했습니다.')
      }
      const data = await res.json()
      localStorage.setItem('user', JSON.stringify(data))
      router.push('/dashboard')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '로그인에 실패했습니다.'
      setErrors({ submit: msg })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background-light dark:bg-background-dark px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="bg-gradient-to-br from-primary to-primary/70 rounded-2xl size-14 flex items-center justify-center shadow-lg shadow-primary/20 mb-4">
            <span className="material-symbols-outlined text-white !text-3xl">document_scanner</span>
          </div>
          <h1 className="text-text-primary-light dark:text-text-primary-dark text-2xl font-bold">Futurenuri PDFix</h1>
          <p className="text-text-secondary-light dark:text-text-secondary-dark text-sm mt-1">계정에 로그인하세요</p>
        </div>

        {/* Form Card */}
        <div className="bg-surface-light dark:bg-surface-dark rounded-2xl border border-border-light dark:border-border-dark p-8 shadow-sm">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">

            {/* 아이디 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">
                아이디
              </label>
              <input
                type="text"
                name="username"
                value={form.username}
                onChange={handleChange}
                placeholder="아이디 입력"
                autoFocus
                className={`px-4 py-2.5 rounded-xl border text-sm bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark placeholder:text-text-secondary-light dark:placeholder:text-text-secondary-dark outline-none transition-colors focus:border-primary ${
                  errors.username ? 'border-red-400' : 'border-border-light dark:border-border-dark'
                }`}
              />
              {errors.username && <p className="text-xs text-red-500">{errors.username}</p>}
            </div>

            {/* 비밀번호 */}
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">
                비밀번호
              </label>
              <input
                type="password"
                name="password"
                value={form.password}
                onChange={handleChange}
                placeholder="비밀번호 입력"
                className={`px-4 py-2.5 rounded-xl border text-sm bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark placeholder:text-text-secondary-light dark:placeholder:text-text-secondary-dark outline-none transition-colors focus:border-primary ${
                  errors.password ? 'border-red-400' : 'border-border-light dark:border-border-dark'
                }`}
              />
              {errors.password && <p className="text-xs text-red-500">{errors.password}</p>}
            </div>

            {/* 서버 에러 */}
            {errors.submit && (
              <p className="text-sm text-red-500 text-center">{errors.submit}</p>
            )}

            {/* 로그인 버튼 */}
            <button
              type="submit"
              disabled={loading}
              className="mt-1 w-full py-3 bg-primary text-white font-semibold rounded-xl hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="material-symbols-outlined text-lg animate-spin">progress_activity</span>
                  로그인 중...
                </span>
              ) : '로그인'}
            </button>
          </form>
        </div>

        {/* 회원가입 링크 */}
        <p className="text-center text-sm text-text-secondary-light dark:text-text-secondary-dark mt-6">
          계정이 없으신가요?{' '}
          <Link href="/join" className="text-primary font-semibold hover:underline">
            회원가입
          </Link>
        </p>
      </div>
    </div>
  )
}
