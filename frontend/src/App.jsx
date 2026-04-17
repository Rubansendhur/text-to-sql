import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext.jsx'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Students from './pages/Students.jsx'
import StudentDetail from './pages/StudentDetail.jsx'
import Faculty from './pages/Faculty.jsx'
import FacultyDetail from './pages/FacultyDetail.jsx'
import Arrears from './pages/Arrears.jsx'
import Timetable from './pages/Timetable.jsx'
import Upload from './pages/Upload.jsx'
import Chat from './pages/Chat.jsx'
import Subjects from './pages/Subjects.jsx'
import Login from './pages/Login.jsx'
import UserManagement from './pages/UserManagement.jsx'
import Stats from './pages/Stats.jsx'

function ProtectedRoute({ children, adminOnly = false, centralAdminOnly = false }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return null

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (centralAdminOnly && user.role !== 'central-admin') {
    return <Navigate to="/dashboard" replace />
  }

  if (adminOnly && user.role !== 'admin' && user.role !== 'central-admin') {
    return <Navigate to="/dashboard" replace />
  }

  return children
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />

            {/* Students */}
            <Route path="students" element={<Students />} />
            <Route path="students/:register_number" element={<StudentDetail />} />

            {/* Faculty */}
            <Route path="faculty" element={<Faculty />} />
            <Route path="faculty/:faculty_id" element={<FacultyDetail />} />

            <Route path="arrears" element={<Arrears />} />
            <Route path="timetable" element={<Timetable />} />
            <Route path="upload" element={<ProtectedRoute adminOnly={true}><Upload /></ProtectedRoute>} />
            <Route path="chat" element={<Chat />} />
            <Route path="subjects" element={<Subjects />} />
            <Route path="users" element={<ProtectedRoute centralAdminOnly={true}><UserManagement /></ProtectedRoute>} />
            <Route path="stats" element={<ProtectedRoute centralAdminOnly={true}><Stats /></ProtectedRoute>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}