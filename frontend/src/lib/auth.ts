import type { AuthTokens } from './api'

const AUTH_STORAGE_KEY = 'jpapp2.auth.tokens'
const AUTH_EVENT_NAME = 'jpapp2-auth-changed'

export function getStoredTokens(): AuthTokens | null {
  const raw = localStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<AuthTokens>
    if (!parsed.access_token || !parsed.refresh_token || !parsed.token_type) {
      return null
    }

    return {
      access_token: parsed.access_token,
      refresh_token: parsed.refresh_token,
      token_type: parsed.token_type,
    }
  } catch {
    return null
  }
}

export function getAccessToken(): string | null {
  return getStoredTokens()?.access_token ?? null
}

export function setStoredTokens(tokens: AuthTokens) {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(tokens))
  window.dispatchEvent(new Event(AUTH_EVENT_NAME))
}

export function clearStoredTokens() {
  localStorage.removeItem(AUTH_STORAGE_KEY)
  window.dispatchEvent(new Event(AUTH_EVENT_NAME))
}

export function subscribeAuthChange(listener: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === AUTH_STORAGE_KEY) {
      listener()
    }
  }

  window.addEventListener(AUTH_EVENT_NAME, listener)
  window.addEventListener('storage', onStorage)

  return () => {
    window.removeEventListener(AUTH_EVENT_NAME, listener)
    window.removeEventListener('storage', onStorage)
  }
}
