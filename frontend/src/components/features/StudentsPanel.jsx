import { useState } from 'react';
import { apiFetch } from '../../api/apiClient';

function StudentsPanel({ students, attendance, onRefresh }) {
  const [deletingId, setDeletingId] = useState(null);
  const [editingStudent, setEditingStudent] = useState(null); // {id, name}
  const [newName, setNewName] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);

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
    const confirmDelete = window.confirm(
      `Bạn có chắc chắn muốn xóa sinh viên "${studentName}" (ID: ${studentId})?\n\n` +
      "Tất cả embedding và lịch sử điểm danh sẽ bị xóa vĩnh viễn."
    );

    if (!confirmDelete) return;

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

  return (
    <div className="panel-grid">
      {/* Danh sách sinh viên */}
      <section className="panel-card">
        <div className="panel-header">
          <h2>Danh sách sinh viên ({students.length})</h2>
          <button type="button" className="btn btn-secondary" onClick={onRefresh}>
            Tải lại
          </button>
        </div>

        <div className="list-box">
          {students.length === 0 ? (
            <p className="empty-message">Chưa có sinh viên nào được đăng ký.</p>
          ) : (
            <ul className="student-list">
              {students.map((student) => (
                <li key={student.id} className="student-item">
                  <div className="student-info">
                    <strong>ID: {student.id}</strong> — {student.name}
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
                  <div>
                    <strong>{new Date(record.timestamp).toLocaleString('vi-VN')}</strong>
                    <br />
                    {record.name} (ID: {record.student_id})
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