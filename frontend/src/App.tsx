import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { HomePage } from './pages/HomePage'
import { InsertPage } from './pages/InsertPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProgressPage } from './pages/ProgressPage'
import { QuizPage } from './pages/QuizPage'
import { RegisterPage } from './pages/RegisterPage'
import { BookDetailPage } from './pages/BookDetailPage'
import { ViewPage } from './pages/ViewPage'
import { WordDetailPage } from './pages/WordDetailPage'
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
