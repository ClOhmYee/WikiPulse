import { useCallback, useEffect, useRef, useState } from "react";

export const MIN_ZOOM = 0.12;
export const OVERVIEW_ZOOM = 0.45;
export const MAX_ZOOM = 4 / 1.4 ** 3;
export const DEFAULT_ZOOM = 1 / 1.2;
export const MAP_SCALE = 0.85;
export const clampZoom = (zoom) => Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
export function mapPoint(svg, clientX, clientY) {
  const point = new DOMPoint(clientX, clientY).matrixTransform(
    svg.getScreenCTM().inverse(),
  );
  return {
    x: (point.x - svg.clientWidth / 2) / MAP_SCALE,
    y: (point.y - svg.clientHeight / 2) / MAP_SCALE,
  };
}

export default function useMapCamera(svgRef) {
  const [camera, setCamera] = useState({ zoom: DEFAULT_ZOOM, x: 0, y: 0 });
  const current = useRef(camera);
  const target = useRef(camera);
  const frame = useRef(null);
  const listeners = useRef(new Set());
  const subscribe = useCallback((listener) => {
    listeners.current.add(listener);
    return () => listeners.current.delete(listener);
  }, []);
  const paint = useCallback((next) => {
    current.current = next;
    for (const listener of listeners.current) listener(next);
  }, []);

  const stop = useCallback(() => {
    cancelAnimationFrame(frame.current);
    frame.current = null;
    target.current = current.current;
    return current.current;
  }, []);

  const move = useCallback(
    (next, settled = true) => {
      cancelAnimationFrame(frame.current);
      frame.current = null;
      target.current = next;
      paint(next);
      if (settled) setCamera(next);
    },
    [paint],
  );

  const zoomBy = useCallback(
    (factor, anchor) => {
      const old = target.current;
      const zoom = clampZoom(old.zoom * factor);
      const ratio = zoom / old.zoom;
      target.current = {
        zoom,
        x: anchor.x - (anchor.x - old.x) * ratio,
        y: anchor.y - (anchor.y - old.y) * ratio,
      };
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        move(target.current);
        return;
      }
      if (frame.current !== null) return;
      let previous = null;
      const tick = (now) => {
        // Start on the RAF clock: its first timestamp may precede the input
        // handler's performance.now(), which would extrapolate past the zoom.
        const elapsed = previous === null ? 0 : Math.max(0, now - previous);
        const amount = 1 - Math.exp(-elapsed / 65);
        previous = now;
        const from = current.current,
          to = target.current;
        const settled =
          Math.abs(to.zoom - from.zoom) < 0.0001 &&
          Math.hypot(to.x - from.x, to.y - from.y) < 0.05;
        const next = settled
          ? to
          : {
              zoom: from.zoom + (to.zoom - from.zoom) * amount,
              x: from.x + (to.x - from.x) * amount,
              y: from.y + (to.y - from.y) * amount,
            };
        paint(next);
        // React owns the settled view; animation only updates the camera layer.
        if (settled) setCamera(next);
        frame.current = settled ? null : requestAnimationFrame(tick);
      };
      frame.current = requestAnimationFrame(tick);
    },
    [move, paint],
  );

  useEffect(() => {
    const svg = svgRef.current;
    const wheel = (event) => {
      if (!event.deltaY) return;
      event.preventDefault();
      const anchor = mapPoint(svg, event.clientX, event.clientY);
      const unit =
        event.deltaMode === 1
          ? 16
          : event.deltaMode === 2
            ? svg.clientHeight
            : 1;
      const delta = Math.max(-240, Math.min(240, event.deltaY * unit));
      zoomBy(Math.exp(-delta * 0.0018), anchor);
    };
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => {
      svg.removeEventListener("wheel", wheel);
      stop();
    };
  }, [svgRef, zoomBy, stop]);

  return { camera, current, subscribe, move, stop, zoomBy };
}
