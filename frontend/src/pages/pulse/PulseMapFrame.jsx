import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Minimize } from "lucide-react";

export default function PulseMapFrame({
  expanded,
  onClose,
  timeline,
  hasMap,
  returnScroll,
  children,
}) {
  const dialogRef = useRef(null);
  const returnFocus = useRef(null);
  const timelineRef = useRef(null);
  const hideTimer = useRef(null);
  const hovering = useRef(false);
  const keyboardFocus = useRef(false);
  const interacting = useRef(false);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const timelineId = useId();
  function showTimeline() {
    window.clearTimeout(hideTimer.current);
    setTimelineOpen(true);
  }
  const hideTimelineLater = useCallback(() => {
    window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => {
      if (
        hovering.current ||
        interacting.current ||
        (keyboardFocus.current &&
          timelineRef.current?.contains(document.activeElement))
      )
        return;
      if (timelineRef.current?.contains(document.activeElement))
        document.activeElement.blur();
      setTimelineOpen(false);
    }, 900);
  }, []);
  useEffect(() => {
    setTimelineOpen(false);
    hovering.current = false;
    keyboardFocus.current = false;
    interacting.current = false;
    const finishInteraction = () => {
      if (!interacting.current) return;
      interacting.current = false;
      if (!hovering.current) hideTimelineLater();
    };
    window.addEventListener("pointerup", finishInteraction);
    window.addEventListener("pointercancel", finishInteraction);
    return () => {
      window.clearTimeout(hideTimer.current);
      window.removeEventListener("pointerup", finishInteraction);
      window.removeEventListener("pointercancel", finishInteraction);
    };
  }, [expanded, hideTimelineLater]);
  useLayoutEffect(() => {
    if (!expanded) {
      if (!returnFocus.current) return;
      const restoreScroll = () => {
        if (returnScroll.current) {
          window.scrollTo({ ...returnScroll.current, behavior: "instant" });
        }
      };
      restoreScroll();
      const frame = requestAnimationFrame(() => {
        const trigger = document.querySelector(
          '[aria-label="펄스맵 전체화면"]',
        );
        (
          trigger || document.querySelector('[aria-label="스냅샷 시각"]')
        )?.focus({ preventScroll: true });
        restoreScroll();
        returnFocus.current = null;
      });
      return () => cancelAnimationFrame(frame);
    }
    returnFocus.current = document.activeElement;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    dialog
      .querySelector('[aria-label="전체화면 닫기"]')
      ?.focus({ preventScroll: true });
    return () => {
      document.body.style.overflow = previousOverflow;
      dialog.close();
    };
  }, [expanded, returnScroll]);

  return expanded ? (
    <dialog
      ref={dialogRef}
      className="pulse-fullscreen"
      aria-label="펄스맵 전체화면"
      onPointerDown={(event) => {
        if (!timelineRef.current?.contains(event.target)) {
          keyboardFocus.current = false;
          hideTimelineLater();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div
        ref={timelineRef}
        className="pulse-fullscreen__time-controls"
        data-open={timelineOpen}
        onPointerEnter={(event) => {
          if (event.pointerType === "touch") return;
          hovering.current = true;
          showTimeline();
        }}
        onPointerLeave={() => {
          hovering.current = false;
          hideTimelineLater();
        }}
        onPointerDown={() => {
          keyboardFocus.current = false;
          interacting.current = true;
        }}
        onFocusCapture={(event) => {
          keyboardFocus.current = event.target.matches(":focus-visible");
          showTimeline();
        }}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget)) {
            keyboardFocus.current = false;
            hideTimelineLater();
          }
        }}
        onKeyDown={() => {
          keyboardFocus.current = true;
        }}
      >
        <button
          className="pulse-fullscreen__time-trigger"
          aria-label="시간축 표시"
          aria-expanded={timelineOpen}
          aria-controls={timelineId}
          onClick={showTimeline}
        >
          <span className="pulse-fullscreen__time-handle" aria-hidden="true" />
        </button>
        <div
          id={timelineId}
          className="pulse-fullscreen__time-drawer"
          inert={!timelineOpen}
        >
          {timeline}
        </div>
      </div>
      <div className="pulse-fullscreen__content">{children}</div>
      {!hasMap && (
        <button
          className="wp-icon-button pulse-fullscreen__exit"
          aria-label="전체화면 닫기"
          onClick={onClose}
        >
          <Minimize size={18} />
        </button>
      )}
    </dialog>
  ) : (
    children
  );
}
