import { useEffect, useState } from 'react';
import { useAuth } from './context/AuthContext';
import { apiFetch } from './api/apiClient';

import RegisterPanel from './components/features/RegisterPanel';
import AttendancePanel from './components/features/AttendancePanel';
import StudentsPanel from './components/features/StudentsPanel';
import LoginPanel from './components/features/LoginPanel';

const tabs = [
  { id: 'register', label: 'Đăng ký' },
  { id: 'attendance', label: 'Điểm danh' },
  { id: 'students', label: 'Danh sách' },
];

function App() {
  const { token, isAuthenticated, logout, isLoading } = useAuth();
  
  const [activeTab, setActiveTab] = useState('register');
  const [students, setStudents] = useState([]);
  const [attendance, setAttendance] = useState([]);

  // Load dữ liệu khi chuyển sang tab Students và đã đăng nhập
  useEffect(() => {
    if (activeTab === 'students' && isAuthenticated) {
      loadStudents();
      loadAttendance();
    }
  }, [activeTab, isAuthenticated]);

  async function loadStudents() {
    try {
      const response = await apiFetch('/students');
      if (!response.ok) throw new Error('Không tải được danh sách sinh viên');
      const data = await response.json();
      setStudents(data.data || []);
    } catch (error) {
      console.error('Load students error:', error);
    }
  }

  async function loadAttendance() {
    try {
      const response = await apiFetch('/attendance');
      if (!response.ok) throw new Error('Không tải được lịch sử điểm danh');
      const data = await response.json();
      setAttendance(data.data || []);
    } catch (error) {
      console.error('Load attendance error:', error);
    }
  }

  const handleLogout = async () => {
    await logout();
    setActiveTab('register');
  };

  // Hiển thị loading khi AuthContext đang khởi tạo
  if (isLoading) {
    return <div className="loading-screen">Đang tải...</div>;
  }

  // Nếu chưa đăng nhập → hiển thị Login
  if (!isAuthenticated) {
    return <LoginPanel />;
  }

  // Đã đăng nhập → hiển thị giao diện chính
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-top">
          <div className="app-brand">
            <h1>Face Attendance</h1>
            <p>Hệ thống điểm danh khuôn mặt</p>
          </div>

          <div className="header-actions">
            <button className="btn btn-ghost" onClick={handleLogout}>
              Đăng xuất
            </button>
          </div>
        </div>

        <nav className="tab-bar">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={tab.id === activeTab ? 'tab-button active' : 'tab-button'}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="app-content">
        {activeTab === 'register' && <RegisterPanel onRegisterSuccess={loadStudents} />}
        {activeTab === 'attendance' && <AttendancePanel onSuccess={loadAttendance} />}
        {activeTab === 'students' && (
          <StudentsPanel
            students={students}
            attendance={attendance}
            onRefresh={() => {
              loadStudents();
              loadAttendance();
            }}
          />
        )}
      </main>
    </div>
  );
}

export default App;