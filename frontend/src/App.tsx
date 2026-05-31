import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell.tsx'
import { HomePage } from './pages/HomePage.tsx'
import { InsertPage } from './pages/InsertPage.tsx'
import { LoginPage } from './pages/LoginPage.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { ProgressPage } from './pages/ProgressPage.tsx'
import { QuizPage } from './pages/QuizPage.tsx'
import { RegisterPage } from './pages/RegisterPage.tsx'
import { BookDetailPage } from './pages/BookDetailPage.tsx'
import { JobDetailPage } from './pages/JobDetailPage.tsx'
import { JobPage } from './pages/JobPage.tsx'
import { ViewPage } from './pages/ViewPage.tsx'
import { WordDetailPage } from './pages/WordDetailPage.tsx'
import './App.css'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/home" replace />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/insert" element={<InsertPage />} />
        <Route path="/view" element={<ViewPage />} />
        <Route path="/view/word/:wordId" element={<WordDetailPage />} />
        <Route path="/view/book/:bookId" element={<BookDetailPage />} />
        <Route path="/jobs" element={<JobPage />} />
        <Route path="/jobs/:jobType/:jobId" element={<JobDetailPage />} />
        <Route path="/quiz" element={<QuizPage />} />
        <Route path="/progress" element={<ProgressPage />} />
      </Route>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
