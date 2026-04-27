import { useEffect } from 'react';

function ConfirmDialog({
  open,
  title,
  message,
  confirmText = 'OK',
  cancelText = 'Hủy',
  tone = 'warning', // warning | danger | info
  onConfirm,
  onCancel,
}) {
  useEffect(() => {
    if (!open) return undefined;

    const handler = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel?.();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onCancel]);

  if (!open) return null;

  const toneClass =
    tone === 'danger' ? 'confirm-dialog--danger' :
    tone === 'info' ? 'confirm-dialog--info' :
    'confirm-dialog--warning';

  return (
    <div
      className="confirm-dialog__overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title || 'Xác nhận'}
      onMouseDown={(e) => {
        // Click outside closes
        if (e.target === e.currentTarget) onCancel?.();
      }}
    >
      <div className={`confirm-dialog__card ${toneClass}`}>
        <div className="confirm-dialog__header">
          <div className="confirm-dialog__badge" aria-hidden="true">
            {tone === 'danger' ? '!' : tone === 'info' ? 'i' : '?'}
          </div>
          <div className="confirm-dialog__titles">
            <h3 className="confirm-dialog__title">{title || 'Xác nhận nhanh'}</h3>
            {message ? <p className="confirm-dialog__message">{message}</p> : null}
          </div>
        </div>

        <div className="confirm-dialog__actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            {cancelText}
          </button>
          <button
            type="button"
            className={`btn ${tone === 'danger' ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
        <div className="confirm-dialog__hint">
          Mẹo: nhấn <strong>Esc</strong> để hủy.
        </div>
      </div>
    </div>
  );
}

export default ConfirmDialog;

