import { useEffect, useRef } from "react";

export default function PulseMapFrame({ expanded, onClose, children }) {
  const dialogRef = useRef(null);
  const returnFocus = useRef(null);
  useEffect(() => {
    if (!expanded) {
      if (!returnFocus.current) return;
      const frame = requestAnimationFrame(() => {
        document
          .querySelector('[aria-label="펄스맵 전체화면"]')
          ?.focus({ preventScroll: true });
        returnFocus.current = null;
      });
      return () => cancelAnimationFrame(frame);
    }
    returnFocus.current = document.activeElement;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    dialog.querySelector('[aria-label="전체화면 닫기"]')?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      dialog.close();
    };
  }, [expanded]);

  return expanded ? (
    <dialog
      ref={dialogRef}
      className="pulse-fullscreen"
      aria-label="펄스맵 전체화면"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      {children}
    </dialog>
  ) : (
    children
  );
}
