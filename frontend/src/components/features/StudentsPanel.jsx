import { useState } from 'react';
import { apiFetch } from '../../api/apiClient';
import ConfirmDialog from '../common/ConfirmDialog';

function formatAttendanceTimestamp(timestamp) {
  if (!timestamp) return 'Khong ro thoi gian';

  // SQLite retorna formato naive "YYYY-MM-DD HH:MM:SS" em timezone Vietnamita
  // Não reinterpretamos com timezone do navegador, apenas exibimos como está
  const sqliteMatch = String(timestamp).match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/
  );

  if (sqliteMatch) {
    const [, year, month, day, hour, minute, second] = sqliteMatch;
    // Exibir no formato: HH:MM:SS DD/MM/YYYY (como armazenado em timezone Vietnamita)
    return `${hour}:${minute}:${second} ${day}/${month}/${year}`;
  }

  // Fallback para outros formatos
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return String(timestamp);
  }

  return parsed.toLocaleString('vi-VN', { hour12: false });
}

function StudentsPanel({ students, attendance, onRefresh }) {
  const [deletingId, setDeletingId] = useState(null);
  const [editingStudent, setEditingStudent] = useState(null); // {id, name}
  const [newName, setNewName] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState({
    open: false,
    studentId: null,
    studentName: '',
  });

  // Mở modal chỉnh sửa
  const handleEdit = (student) => {
    setEditingStudent(student);
    setNewName(student.name);
  };

  // Đóng modal
  const closeEditModal = () => {
    setEditingStudent(null);
    setNewName('');
  };

  // Xác nhận cập nhật tên
  async function handleUpdateName() {
    if (!newName.trim() || newName.trim() === editingStudent.name) {
      closeEditModal();
      return;
    }

    setIsUpdating(true);

    try {
      const res = await apiFetch(`/students/${editingStudent.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim() }),
      });

      if (!res.ok) {
        throw new Error('Cập nhật tên thất bại');
      }

      alert(`Đã cập nhật tên sinh viên thành: ${newName.trim()}`);
      closeEditModal();
      onRefresh(); // Refresh danh sách

    } catch (err) {
      console.error(err);
      alert('Có lỗi xảy ra khi cập nhật tên sinh viên');
    } finally {
      setIsUpdating(false);
    }
  }

  // Xóa sinh viên
  async function handleDelete(studentId, studentName) {
    setDeleteConfirm({ open: true, studentId, studentName });
  }

  async function confirmDeleteNow() {
    const studentId = deleteConfirm.studentId;
    const studentName = deleteConfirm.studentName;
    if (!studentId) {
      setDeleteConfirm({ open: false, studentId: null, studentName: '' });
      return;
    }
    setDeletingId(studentId);

    try {
      const res = await apiFetch(`/students/${studentId}`, { method: 'DELETE' });

      if (!res.ok) throw new Error('Xóa thất bại');

      alert(`Đã xóa sinh viên "${studentName}" thành công!`);
      onRefresh();
    } catch (err) {
      alert(`Xóa thất bại: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  }

  // Xuất Excel điểm danh từ database
  async function handleExportAttendance() {
    try {
      const response = await apiFetch('/attendance/export');
      if (!response.ok) {
        throw new Error('Export failed');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `DiemDanh_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Export error:', error);
      alert('Có lỗi khi xuất Excel điểm danh');
    }
  }

  return (
    <div className="panel-grid">
      <ConfirmDialog
        open={deleteConfirm.open}
        title="Bạn chắc chắn muốn xóa chứ?"
        message={`Xóa "${deleteConfirm.studentName}" (ID: ${deleteConfirm.studentId}) sẽ xóa luôn embedding và lịch sử điểm danh. Không thể hoàn tác.`}
        confirmText={deletingId ? 'Đang xóa...' : 'Xóa luôn'}
        cancelText="Thôi, để đó"
        tone="danger"
        onCancel={() => setDeleteConfirm({ open: false, studentId: null, studentName: '' })}
        onConfirm={async () => {
          await confirmDeleteNow();
          setDeleteConfirm({ open: false, studentId: null, studentName: '' });
        }}
      />
      {/* Danh sách sinh viên */}
      <section className="panel-card">
        <div className="panel-header">
          <h2>Danh sách sinh viên ({students.length})</h2>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button type="button" className="btn btn-secondary" onClick={onRefresh}>
              Tải lại
            </button>
            <button type="button" className="btn btn-success" onClick={handleExportAttendance}>
              📤 Xuất file Excel điểm danh
            </button>
          </div>
        </div>

        <div className="list-box">
          {students.length === 0 ? (
            <p className="empty-message">Chưa có sinh viên nào được đăng ký.</p>
          ) : (
            <ul className="student-list">
              {students.map((student) => (
                <li key={student.id} className="student-item">
                  <div className="student-info">
                    <div className="student-title-row">
                      <strong>ID: {student.id}</strong>
                      <span className="student-name">{student.name}</span>
                    </div>
                    {student.mssv ? (
                      <span className="student-mssv">MSSV: {student.mssv}</span>
                    ) : (
                      <span className="student-mssv empty">Chưa có MSSV</span>
                    )}
                  </div>
                  <div className="student-actions">
                    <button
                      className="btn btn-edit btn-small"
                      onClick={() => handleEdit(student)}
                    >
                      Sửa
                    </button>
                    <button
                      className="btn btn-danger btn-small"
                      onClick={() => handleDelete(student.id, student.name)}
                      disabled={deletingId === student.id}
                    >
                      {deletingId === student.id ? 'Đang xóa...' : 'Xóa'}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Lịch sử điểm danh */}
      <section className="panel-card">
        <div className="panel-header">
          <h2>Lịch sử điểm danh ({attendance.length})</h2>
          <button type="button" className="btn btn-secondary" onClick={onRefresh}>
            Tải lại
          </button>
        </div>

        <div className="list-box">
          {attendance.length === 0 ? (
            <p className="empty-message">Chưa có bản ghi điểm danh nào.</p>
          ) : (
            <ul className="attendance-list">
              {attendance.slice(0, 20).map((record) => (
                <li key={record.id} className="attendance-item">
                  <div className="attendance-content">
                    <strong>{formatAttendanceTimestamp(record.timestamp)}</strong>
                    <span>{record.name} (ID: {record.student_id})</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {attendance.length > 20 && (
            <p className="more-info">... và {attendance.length - 20} bản ghi khác</p>
          )}
        </div>
      </section>

      {/* Modal Chỉnh sửa tên */}
      {editingStudent && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h3>Chỉnh sửa tên sinh viên</h3>
            <p>ID: {editingStudent.id}</p>
            
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="modal-input"
              autoFocus
            />

            <div className="modal-actions">
              <button 
                className="btn btn-secondary" 
                onClick={closeEditModal}
                disabled={isUpdating}
              >
                Hủy
              </button>
              <button 
                className="btn btn-primary" 
                onClick={handleUpdateName}
                disabled={isUpdating || !newName.trim()}
              >
                {isUpdating ? 'Đang cập nhật...' : 'Lưu thay đổi'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default StudentsPanel;