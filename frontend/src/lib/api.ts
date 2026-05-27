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

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: RequestBody
  token?: string | null
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
  return apiRequest<{ message: string }>('/logout', {
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
  return apiRequest<QuizResponse>(path, { token })
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
  return apiRequest<{ total: number; updated: number; failed: number }>('/word/prio/batch', {
    method: 'POST',
    token,
    body: { answers },
  })
}

export type ProgressResponse = Record<string, Record<string, number>>

export function getProgress(token: string) {
  return apiRequest<ProgressResponse>('/api/progress', { token })
}

export type ViewWordsResponse = {
  word_list: Array<Record<string, unknown>>
  page_count: number
  page: number
  args: Record<string, string | null>
}

export type ViewBooksResponse = {
  book_list: Array<Record<string, unknown>>
  page_count: number
  page: number
  args: Record<string, string | null>
}

export function getWords(
  token: string,
  params?: { jlpt_level?: string; star?: boolean; page?: number; limit?: number },
) {
  return apiRequest<ViewWordsResponse>(withQuery('/view/word', params), { token })
}

export function getBooks(
  token: string,
  params?: { star?: boolean; page?: number; limit?: number },
) {
  return apiRequest<ViewBooksResponse>(withQuery('/api/view/book', params), { token })
}

export function searchWords(token: string, word: string, limit = 20) {
  return apiRequest<{ results: Array<Record<string, unknown>> }>(
    withQuery('/api/view/search-word', { word, limit }),
    { token },
  )
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

  return fetch(getApiUrl('/insert/str/bg'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Idempotency-Key': idempotencyKey,
    },
    body: form,
  }).then(async (response) => {
    if (!response.ok) {
      const contentType = response.headers.get('content-type') ?? ''
      if (contentType.includes('application/json')) {
        const body = (await response.json()) as { detail?: string }
        throw new ApiError(response.status, body.detail ?? 'Insert failed')
      }
      throw new ApiError(response.status, await response.text())
    }
    return (await response.json()) as InsertStringJobResponse
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

  return fetch(getApiUrl('/insert/file/bg'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Idempotency-Key': idempotencyKey,
    },
    body: form,
  }).then(async (response) => {
    if (!response.ok) {
      const contentType = response.headers.get('content-type') ?? ''
      if (contentType.includes('application/json')) {
        const body = (await response.json()) as { detail?: string }
        throw new ApiError(response.status, body.detail ?? 'File upload failed')
      }
      throw new ApiError(response.status, await response.text())
    }
    return (await response.json()) as InsertFileJobResponse
  })
}

export function getInsertJob(token: string, jobId: string) {
  return apiRequest<Record<string, unknown>>(`/api/job/${jobId}`, { token })
}
