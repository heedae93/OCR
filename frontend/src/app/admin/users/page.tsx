'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from '@/components/Sidebar'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:6015'

interface User {
  user_id: string
  username: string
  name: string
  email: string
  type: string
  total_jobs: number
  created_at: string | null
  last_login: string | null
}

const emptyForm = { username: '', name: '', email: '', password: '', type: 'U' }

export default function UserManagementPage() {
  const router = useRouter()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalMode, setModalMode] = useState<'create' | 'edit' | null>(null)
  const [selectedUser, setSelectedUser] = useState<User | null>(null)
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null)
  const [deleting, setDeleting] = useState(false)

  // 관리자 체크
  useEffect(() => {
    if (typeof window === 'undefined') return
    const stored = localStorage.getItem('user')
    if (!stored) { router.push('/login'); return }
    try {
      const user = JSON.parse(stored)
      if (user.type !== 'A') { router.push('/'); return }
    } catch {
      router.push('/login'); return
    }
    fetchUsers()
  }, [])

  async function fetchUsers() {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/api/admin/users`)
      if (!res.ok) throw new Error('불러오기 실패')
      setUsers(await res.json())
    } catch (e: any) {
      setError(e.message || '오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  function openCreate() {
    setForm(emptyForm)
    setFormError('')
    setSelectedUser(null)
    setModalMode('create')
  }

  function openEdit(user: User) {
    setForm({ username: user.username, name: user.name, email: user.email, password: '', type: user.type })
    setFormError('')
    setSelectedUser(user)
    setModalMode('edit')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError('')

    if (!form.name.trim()) { setFormError('이름을 입력하세요.'); return }
    if (modalMode === 'create') {
      if (!form.username.trim()) { setFormError('아이디를 입력하세요.'); return }
      if (!form.password.trim()) { setFormError('비밀번호를 입력하세요.'); return }
    }

    setSaving(true)
    try {
      let res: Response
      if (modalMode === 'create') {
        res = await fetch(`${API_URL}/api/admin/users`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        })
      } else {
        const body: any = { name: form.name, email: form.email, type: form.type }
        if (form.password) body.password = form.password
        res = await fetch(`${API_URL}/api/admin/users/${selectedUser!.user_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
      }
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || '저장 실패')
      }
      setModalMode(null)
      fetchUsers()
    } catch (e: any) {
      setFormError(e.message || '저장 중 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const res = await fetch(`${API_URL}/api/admin/users/${deleteTarget.user_id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('삭제 실패')
      setDeleteTarget(null)
      fetchUsers()
    } catch (e: any) {
      alert(e.message || '삭제 중 오류가 발생했습니다.')
    } finally {
      setDeleting(false)
    }
  }

  function formatDate(s: string | null) {
    if (!s) return '-'
    return new Date(s).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="relative flex min-h-screen w-full bg-background-light dark:bg-background-dark">
      <Sidebar />
      <div className="flex flex-col gap-6 p-8 flex-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary-light dark:text-text-primary-dark">사용자관리</h1>
          <p className="text-sm text-text-secondary-light dark:text-text-secondary-dark mt-1">
            총 {users.length}명
          </p>
        </div>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl hover:bg-primary/90 transition-colors font-medium"
        >
          <span className="material-symbols-outlined text-lg">person_add</span>
          사용자 등록
        </button>
      </div>

      {/* Table */}
      <div className="bg-surface-light dark:bg-surface-dark rounded-xl border border-border-light dark:border-border-dark overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center p-16">
            <span className="material-symbols-outlined animate-spin text-primary text-4xl">progress_activity</span>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-500">{error}</div>
        ) : users.length === 0 ? (
          <div className="p-16 text-center text-text-secondary-light dark:text-text-secondary-dark">
            <span className="material-symbols-outlined text-4xl">group_off</span>
            <p className="mt-2">등록된 사용자가 없습니다.</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-background-light dark:bg-background-dark border-b border-border-light dark:border-border-dark">
              <tr>
                {['아이디', '이름', '이메일', '권한', '작업수', '최근 로그인', '가입일', ''].map((h) => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-text-secondary-light dark:text-text-secondary-dark uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-light dark:divide-border-dark">
              {users.map((u) => (
                <tr key={u.user_id} className="hover:bg-background-light dark:hover:bg-background-dark transition-colors">
                  <td className="px-4 py-3 font-medium text-text-primary-light dark:text-text-primary-dark">{u.username}</td>
                  <td className="px-4 py-3 text-text-primary-light dark:text-text-primary-dark">{u.name || '-'}</td>
                  <td className="px-4 py-3 text-text-secondary-light dark:text-text-secondary-dark">{u.email || '-'}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                      u.type === 'A'
                        ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300'
                        : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
                    }`}>
                      {u.type === 'A' ? '관리자' : '일반'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-text-secondary-light dark:text-text-secondary-dark">{u.total_jobs}</td>
                  <td className="px-4 py-3 text-text-secondary-light dark:text-text-secondary-dark">{formatDate(u.last_login)}</td>
                  <td className="px-4 py-3 text-text-secondary-light dark:text-text-secondary-dark">{formatDate(u.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEdit(u)}
                        className="p-1.5 rounded-lg hover:bg-primary/10 text-primary transition-colors"
                        title="수정"
                      >
                        <span className="material-symbols-outlined text-lg">edit</span>
                      </button>
                      <button
                        onClick={() => setDeleteTarget(u)}
                        className="p-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 text-red-500 transition-colors"
                        title="삭제"
                      >
                        <span className="material-symbols-outlined text-lg">delete</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create / Edit Modal */}
      {modalMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-light dark:bg-surface-dark rounded-2xl border border-border-light dark:border-border-dark shadow-2xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border-light dark:border-border-dark">
              <h2 className="text-lg font-bold text-text-primary-light dark:text-text-primary-dark">
                {modalMode === 'create' ? '사용자 등록' : '사용자 수정'}
              </h2>
              <button onClick={() => setModalMode(null)} className="p-1 rounded-lg hover:bg-black/5 dark:hover:bg-white/5">
                <span className="material-symbols-outlined text-text-secondary-light dark:text-text-secondary-dark">close</span>
              </button>
            </div>
            <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-4">
              {modalMode === 'create' && (
                <div className="flex flex-col gap-1">
                  <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">아이디 *</label>
                  <input
                    type="text"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="px-3 py-2 rounded-lg border border-border-light dark:border-border-dark bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
                    placeholder="영문, 숫자"
                  />
                </div>
              )}
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">이름 *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="px-3 py-2 rounded-lg border border-border-light dark:border-border-dark bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder="이름"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">이메일</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="px-3 py-2 rounded-lg border border-border-light dark:border-border-dark bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder="example@email.com"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">
                  비밀번호 {modalMode === 'edit' && <span className="text-text-secondary-light dark:text-text-secondary-dark font-normal">(변경 시에만 입력)</span>}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="px-3 py-2 rounded-lg border border-border-light dark:border-border-dark bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder={modalMode === 'edit' ? '변경하지 않으려면 비워두세요' : '비밀번호'}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-sm font-medium text-text-primary-light dark:text-text-primary-dark">권한</label>
                <select
                  value={form.type}
                  onChange={(e) => setForm({ ...form, type: e.target.value })}
                  className="px-3 py-2 rounded-lg border border-border-light dark:border-border-dark bg-background-light dark:bg-background-dark text-text-primary-light dark:text-text-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="U">일반 사용자</option>
                  <option value="A">관리자</option>
                </select>
              </div>
              {formError && (
                <p className="text-sm text-red-500 bg-red-50 dark:bg-red-500/10 px-3 py-2 rounded-lg">{formError}</p>
              )}
              <div className="flex gap-3 mt-2">
                <button
                  type="button"
                  onClick={() => setModalMode(null)}
                  className="flex-1 px-4 py-2 rounded-xl border border-border-light dark:border-border-dark text-text-primary-light dark:text-text-primary-dark hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 px-4 py-2 rounded-xl bg-primary text-white hover:bg-primary/90 transition-colors font-medium disabled:opacity-60"
                >
                  {saving ? '저장 중...' : (modalMode === 'create' ? '등록' : '저장')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-surface-light dark:bg-surface-dark rounded-2xl border border-border-light dark:border-border-dark shadow-2xl w-full max-w-sm mx-4 p-6">
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="w-12 h-12 rounded-full bg-red-100 dark:bg-red-500/20 flex items-center justify-center">
                <span className="material-symbols-outlined text-red-500 text-2xl">person_remove</span>
              </div>
              <h2 className="text-lg font-bold text-text-primary-light dark:text-text-primary-dark">사용자 삭제</h2>
              <p className="text-sm text-text-secondary-light dark:text-text-secondary-dark">
                <span className="font-semibold text-text-primary-light dark:text-text-primary-dark">{deleteTarget.name}({deleteTarget.username})</span> 사용자를 삭제하면<br/>
                해당 사용자의 모든 작업 내역도 함께 삭제됩니다.
              </p>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setDeleteTarget(null)}
                className="flex-1 px-4 py-2 rounded-xl border border-border-light dark:border-border-dark text-text-primary-light dark:text-text-primary-dark hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 px-4 py-2 rounded-xl bg-red-500 text-white hover:bg-red-600 transition-colors font-medium disabled:opacity-60"
              >
                {deleting ? '삭제 중...' : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  )
}
