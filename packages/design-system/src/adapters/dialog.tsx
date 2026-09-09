import React, { useEffect, useId, useRef, ReactNode } from "react";

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

/**
 * A modal dialog on the design system's backdrop/dialog vocabulary.
 *
 * Uses a native <dialog> with showModal(), which supplies the modal semantics
 * and focus containment. The heading id is generated per instance: it was
 * previously the constant "dialog-title", so two dialogs mounted at once
 * produced duplicate ids and an ambiguous accessible name.
 */
export function Dialog({ isOpen, onClose, title, children }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <dialog ref={dialogRef} className="backdrop" aria-labelledby={titleId}>
      <div className="dialog">
        <header className="dialog-head">
          <div>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button
            className="icon-button is-bare"
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>
        <div className="dialog-body">{children}</div>
      </div>
    </dialog>
  );
}
