import { request, tokenStore } from './client'

export async function login(email: string, password: string) {
  const { access_token } = await request<{ access_token: string }>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    { isAuthRequest: true },
  )
  tokenStore.set(access_token)
}

export async function register(email: string, password: string) {
  await request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) }, { isAuthRequest: true })
  await login(email, password)
}

export const me = () => request<{ id: number; email: string }>('/auth/me')
