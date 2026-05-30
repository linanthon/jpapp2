import { clearStoredTokens, getStoredTokens, setStoredTokens } from './auth'

type JsonBody = Record<string, unknown> | Array<unknown> | null
type RequestBody = JsonBody | FormData

const rawApiOrigin = (import.meta.env.VITE_API_ORIGIN as string | undefined)?.trim() || ''
const API_ORIGIN = (rawApiOrigin || (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000')).replace(
  /\/$/,
  '',
)
const API_PREFIX = '/v1'

function getApiUrl(path: string) {
  if (!API_ORIGIN) {
    return `${API_PREFIX}${path}`
  }
  return `${API_ORIGIN}${API_PREFIX}${path}`
}

export function getApiAssetUrl(path: string) {
  return getApiUrl(path)
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: RequestBody
  token?: string | null
  headers?: Record<string, string>
  signal?: AbortSignal
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function withQuery(path: string, params?: Record<string, string | number | boolean | null | undefined>) {
  if (!params) {
    return path
  }

  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    query.set(key, String(value))
  })

  const text = query.toString()
  return text ? `${path}?${text}` : path
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers ?? {}),
  }

  const isFormData = options.body instanceof FormData

  if (options.body !== undefined && !isFormData) {
    headers['Content-Type'] = 'application/json'
  }

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`
  }

  let requestBody: BodyInit | undefined
  if (options.body !== undefined) {
    requestBody = isFormData
      ? (options.body as FormData)
      : JSON.stringify(options.body as JsonBody)
  }

  const response = await fetch(getApiUrl(path), {
    method: options.method ?? 'GET',
    headers,
    body: requestBody,
    signal: options.signal,
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`

    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('application/json')) {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) {
        message = body.detail
      }
    } else {
      const text = await response.text()
      if (text) {
        message = text
      }
    }

    throw new ApiError(response.status, message)
  }

  return (await response.json()) as T
}

let refreshInFlight: Promise<AuthTokens> | null = null

async function refreshTokensWithLock(refreshToken: string): Promise<AuthTokens> {
  if (!refreshInFlight) {
    refreshInFlight = apiRequest<AuthTokens>('/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }).finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

async function apiRequestWithAutoRefresh<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  try {
    return await apiRequest<T>(path, options)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || !options.token) {
      throw error
    }

    const tokens = getStoredTokens()
    if (!tokens?.refresh_token) {
      clearStoredTokens()
      throw error
    }

    try {
      const nextTokens = await refreshTokensWithLock(tokens.refresh_token)
      setStoredTokens(nextTokens)
      return await apiRequest<T>(path, { ...options, token: nextTokens.access_token })
    } catch {
      clearStoredTokens()
      throw error
    }
  }
}

export type QuizHomeResponse = {
  all_books: Array<{ id: number; name: string }>
  args: Record<string, string | null>
}

export function getQuizHome(signal?: AbortSignal) {
  return apiRequest<QuizHomeResponse>('/quiz', { signal })
}

export type AuthTokens = {
  access_token: string
  refresh_token: string
  token_type: string
}

export type UserResponse = {
  id: number
  username: string
  email: string
  is_admin: boolean
}

export function getCurrentUser(token: string) {
  return apiRequestWithAutoRefresh<UserResponse>('/me', { token })
}

export function registerUser(payload: {
  username: string
  email: string
  password: string
  is_admin?: boolean
}) {
  return apiRequest<UserResponse>('/register', {
    method: 'POST',
    body: payload,
  })
}

export function loginUser(payload: { username: string; password: string }) {
  return apiRequest<AuthTokens>('/login', {
    method: 'POST',
    body: payload,
  })
}

export function logoutUser(token: string) {
  return apiRequestWithAutoRefresh<{ message: string }>('/logout', {
    method: 'POST',
    token,
  })
}

export type QuizMode = 'jp' | 'en' | 'known'

export type QuizQuestion = {
  question: string
  spelling: string
  audio_mapping: string[]
  correct: string
  choices: string[]
  quized: number
  occurrence: number
  star: boolean
}

export type QuizResponse = {
  quizes: Record<string, QuizQuestion>
  mode: QuizMode
  args: Record<string, string | null>
}

export function getQuizByMode(
  mode: QuizMode,
  token: string,
  params?: {
    limit?: number
    jlpt_level?: string
    star?: boolean
    book_id?: string
    use_priority?: boolean
    get_distractors_from_db?: boolean
  },
) {
  const path = withQuery(`/quiz/${mode}`, params)
  return apiRequestWithAutoRefresh<QuizResponse>(path, { token })
}

export function submitWordPriorityBatch(
  token: string,
  answers: Array<{
    word_id: number
    is_correct: boolean
    quized?: number
    occurrence?: number
  }>,
) {
  return apiRequestWithAutoRefresh<{ total: number; updated: number; failed: number }>('/word/prio/batch', {
    method: 'POST',
    token,
    body: { answers },
  })
}

export type ProgressResponse = Record<string, Record<string, number>>

export function getProgress(token: string) {
  return apiRequestWithAutoRefresh<ProgressResponse>('/api/progress', { token })
}

export type ViewWordsResponse = {
  word_list: WordListItem[]
  page_count: number
  page: number
  args: Record<string, string | null>
}

export type ViewBooksResponse = {
  book_list: BookListItem[]
  page_count: number
  page: number
  args: Record<string, string | null>
}

export type WordListItem = {
  word_id: number
  word: string
  senses: string
  spelling: string
  jlpt_level: string
  audio_mapping: string[]
  occurrence: number
  star: boolean
  quized: number
  priority: number
}

export type BookListItem = {
  book_id: number
  created_at: string
  name: string
  star: boolean
  content?: string
  object_name?: string
  download_url?: string
  download_name?: string
}

export type SearchWordsResponse = {
  results: WordListItem[]
  bpPrefix?: string
}

export function getWords(
  token: string,
  params?: { jlpt_level?: string; star?: boolean; page?: number; limit?: number },
) {
  return apiRequestWithAutoRefresh<ViewWordsResponse>(withQuery('/view/word', params), { token })
}

export function getBooks(
  token: string,
  params?: { star?: boolean; page?: number; limit?: number },
) {
  return apiRequestWithAutoRefresh<ViewBooksResponse>(withQuery('/api/view/book', params), { token })
}

export function searchWords(token: string, word: string, limit = 20) {
  return apiRequestWithAutoRefresh<SearchWordsResponse>(
    withQuery('/api/view/search-word', { word, limit }),
    { token },
  )
}

export function toggleStar(
  token: string,
  payload: { id: number; objType: 'word' | 'book'; star: boolean },
) {
  return apiRequestWithAutoRefresh<{ success: boolean }>('/toggle-star', {
    method: 'POST',
    token,
    body: payload,
  })
}

export type ViewSpecificWordResponse = {
  word_details: WordListItem & {
    forms?: string
    meanings?: string[]
  }
  sen_ex: string[]
}

export function getWordDetails(token: string, wordId: number, sentenceLimit?: number) {
  return apiRequestWithAutoRefresh<ViewSpecificWordResponse>(
    withQuery(`/view/word/${wordId}`, { sen_limit: sentenceLimit }),
    { token },
  )
}

export type ViewSpecificBookResponse = {
  book_details: BookListItem
}

export function getBookDetails(token: string, bookId: number) {
  return apiRequestWithAutoRefresh<ViewSpecificBookResponse>(`/view/book/${bookId}`, { token })
}

export function toggleWordKnown(
  token: string,
  payload: {
    word_id: number
    update_to_known: boolean
    quized?: number
    occurrence?: number
  },
) {
  return apiRequestWithAutoRefresh<{ success: boolean }>('/word/known', {
    method: 'POST',
    token,
    body: payload,
  })
}

export function deleteBookInBackground(token: string, bookId: number, idempotencyKey: string) {
  return apiRequestWithAutoRefresh<{
    job_id: string
    batch_id: string
    book_id: number
    status: string
    message: string
  }>(`/del/book/bg/${bookId}`, {
    method: 'POST',
    token,
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  })
}

export async function checkAdminAccess(token: string): Promise<boolean> {
  try {
    const user = await getCurrentUser(token)
    return Boolean(user.is_admin)
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return false
    }
    return false
  }
}

export type AudioRequestResult =
  | { type: 'blob'; blob: Blob }
  | { type: 'statica'; audio_mapping: string[] }

export async function requestWordAudio(word: string, useModel: boolean): Promise<AudioRequestResult> {
  const response = await fetch(getApiUrl(`/tts?use_model=${useModel ? 'true' : 'false'}`), {
    method: 'POST',
    headers: {
      Accept: 'application/json, audio/wav',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text: word, lang: 'jp' }),
  })

  if (!response.ok) {
    const contentType = response.headers.get('content-type') ?? ''
    if (contentType.includes('application/json')) {
      const body = (await response.json()) as { detail?: string }
      throw new ApiError(response.status, body.detail ?? 'Audio request failed')
    }
    throw new ApiError(response.status, await response.text())
  }

  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('audio/wav')) {
    return { type: 'blob', blob: await response.blob() }
  }

  const payload = (await response.json()) as { audio_mapping?: string[] }
  return { type: 'statica', audio_mapping: payload.audio_mapping ?? [] }
}

export type InsertStringJobResponse = {
  job_id: string
  batch_id: string
  book_id: number
  status: string
  message: string
}

export function queueInsertString(
  token: string,
  payload: { stringName: string; stringBody: string },
  idempotencyKey: string,
) {
  const form = new FormData()
  form.set('stringName', payload.stringName)
  form.set('stringBody', payload.stringBody)

  return apiRequestWithAutoRefresh<InsertStringJobResponse>('/insert/str/bg', {
    method: 'POST',
    token,
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
    body: form,
  })
}

export type InsertFileJobResponse = {
  job_id: string
  batch_id: string
  book_id: number
  status: string
  message: string
}

export function queueInsertFile(token: string, file: File, idempotencyKey: string) {
  const form = new FormData()
  form.set('submittedFile', file)

  return apiRequestWithAutoRefresh<InsertFileJobResponse>('/insert/file/bg', {
    method: 'POST',
    token,
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
    body: form,
  })
}

export function getInsertJob(token: string, jobId: string) {
  return apiRequestWithAutoRefresh<Record<string, unknown>>(`/api/job/${jobId}`, { token })
}
