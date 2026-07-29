import type { ReactNode } from "react";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card card" onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <button className="btn" onClick={onClose}>
            Cerrar
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
