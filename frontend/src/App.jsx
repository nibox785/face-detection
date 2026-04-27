import { useEffect, useState } from 'react';
import { useAuth } from './context/AuthContext';
import { apiFetch } from './api/apiClient';

import RegisterPanel from './components/features/RegisterPanel';
import AttendancePanel from './components/features/AttendancePanel';
import StudentsPanel from './components/features/StudentsPanel';
import LoginPanel from './components/features/LoginPanel';
import ConfirmDialog from './components/common/ConfirmDialog';

const tabs = [
  { id: 'register', label: 'Đăng ký' },
  { id: 'attendance', label: 'Điểm danh' },
  { id: 'students', label: 'Danh sách' },
];

const ACTIVE_TAB_KEY = 'fa_active_tab';
const ATTENDANCE_SESSION_RUNNING_KEY = 'fa_attendance_session_running';

function getInitialTab() {
  const savedTab = sessionStorage.getItem(ACTIVE_TAB_KEY);
  const isValidTab = tabs.some((tab) => tab.id === savedTab);
  return isValidTab ? savedTab : 'register';
}

function App() {
  const { token, isAuthenticated, logout, isLoading } = useAuth();
  
  const [activeTab, setActiveTab] = useState(getInitialTab);
  const [students, setStudents] = useState([]);
  const [attendance, setAttendance] = useState([]);
  const [confirmState, setConfirmState] = useState({
    open: false,
    title: '',
    message: '',
    confirmText: 'OK',
    cancelText: 'Hủy',
    tone: 'warning',
    onConfirm: null,
  });

  const closeConfirm = () => setConfirmState((prev) => ({ ...prev, open: false, onConfirm: null }));

  useEffect(() => {
    sessionStorage.setItem(ACTIVE_TAB_KEY, activeTab);
  }, [activeTab]);

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
    const running = (() => {
      try {
        return sessionStorage.getItem(ATTENDANCE_SESSION_RUNNING_KEY) === '1';
      } catch (_) {
        return false;
      }
    })();

    const doLogout = async () => {
      await logout();
      try {
        sessionStorage.removeItem(ACTIVE_TAB_KEY);
      } catch (_) {
        // ignore
      }
      setActiveTab('register');
    };

    if (!running) {
      await doLogout();
      return;
    }

    setConfirmState({
      open: true,
      title: 'Ơ kìa… bạn sắp rời khỏi phiên điểm danh',
      message: 'Bạn có muốn đóng phiên điểm danh không? Nếu chưa xuất Excel thì nhớ xuất trước nhé.',
      confirmText: 'Đóng phiên & đăng xuất',
      cancelText: 'Ở lại',
      tone: 'warning',
      onConfirm: async () => {
        try {
          sessionStorage.setItem(ATTENDANCE_SESSION_RUNNING_KEY, '0');
        } catch (_) {
          // ignore
        }
        closeConfirm();
        await doLogout();
      },
    });
  };

  const handleTabChange = (nextTabId) => {
    if (nextTabId === activeTab) return;
    const running = (() => {
      try {
        return sessionStorage.getItem(ATTENDANCE_SESSION_RUNNING_KEY) === '1';
      } catch (_) {
        return false;
      }
    })();

    if (!(running && activeTab === 'attendance')) {
      setActiveTab(nextTabId);
      return;
    }

    const nextLabel = tabs.find((t) => t.id === nextTabId)?.label || 'màn hình khác';
    setConfirmState({
      open: true,
      title: 'Đợi xíu… phiên điểm danh đang chạy',
      message: `Bạn đang chuyển sang "${nextLabel}". Bạn có muốn đóng phiên điểm danh không?`,
      confirmText: 'Đóng phiên & chuyển tab',
      cancelText: 'Ở lại Điểm danh',
      tone: 'info',
      onConfirm: () => {
        try {
          sessionStorage.setItem(ATTENDANCE_SESSION_RUNNING_KEY, '0');
        } catch (_) {
          // ignore
        }
        closeConfirm();
        setActiveTab(nextTabId);
      },
    });
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
      <ConfirmDialog
        open={confirmState.open}
        title={confirmState.title}
        message={confirmState.message}
        confirmText={confirmState.confirmText}
        cancelText={confirmState.cancelText}
        tone={confirmState.tone}
        onCancel={closeConfirm}
        onConfirm={confirmState.onConfirm || closeConfirm}
      />
      <header className="app-header">
        <div className="app-header-top">
          <div className="app-brand">
            <h1>Face Attendance</h1>
            <p>Hệ thống điểm danh khuôn mặt</p>
          </div>

          <div className="header-actions">
            <button className="btn btn-ghost btn-ghost--inverse" onClick={handleLogout}>
              Đăng xuất
            </button>
          </div>
        </div>

        <nav className="tab-bar">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={tab.id === activeTab ? 'tab-button active' : 'tab-button'}
              onClick={() => handleTabChange(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="app-content">
        {activeTab === 'register' && <RegisterPanel onRegisterSuccess={loadStudents} />}
        {activeTab === 'attendance' && <AttendancePanel />}
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