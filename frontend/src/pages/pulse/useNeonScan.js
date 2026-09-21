import { useEffect, useState } from "react";

// The wave and graph share world origin (0, 0) and the same camera transform.
// Distances stay in map coordinates, independent of pan, zoom and viewport.
export default function useNeonScan(svgRef, scene, enabled, view) {
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    const ring = svg.querySelector(".pulse-scan__wave");
    const echo = svg.querySelector(".pulse-scan__echo");
    const targets = [...svg.querySelectorAll("[data-scan-x]")].map(
      (element) => ({
        element,
        distance: Math.hypot(
          Number(element.dataset.scanX),
          Number(element.dataset.scanY),
        ),
        strength: 0,
        dynamic: element.dataset.scanDynamic === "true",
        overview: element.dataset.scanMode === "overview",
        clusterKey: element.closest(".document-cluster").dataset.issueKey,
      }),
    );
    const fixed = targets
      .filter((target) => !target.dynamic)
      .sort((a, b) => a.distance - b.distance);
    const titles = targets.filter((target) => target.dynamic);
    let lit = new Set();
    const lowerBound = (distance) => {
      let low = 0,
        high = fixed.length;
      while (low < high) {
        const middle = (low + high) >>> 1;
        if (fixed[middle].distance < distance) low = middle + 1;
        else high = middle;
      }
      return low;
    };
    let frame = null,
      visible = false,
      elapsed = 0,
      previous = null,
      lastPaint = 0;
    const maxRadius = Math.max(scene.width, scene.height) / 2;
    const clear = () => {
      ring.style.opacity = "0";
      echo.style.opacity = "0";
      for (const target of lit) {
        target.element.style.removeProperty("--scan-strength");
        target.strength = 0;
      }
      lit.clear();
    };
    const paint = (now) => {
      elapsed += previous === null ? 0 : now - previous;
      previous = now;
      if (now - lastPaint >= 32) {
        lastPaint = now;
        const phase = elapsed % 4000;
        const radius = (phase / 2500) * maxRadius;
        const alpha =
          phase < 2500 ? Math.min(1, phase / 220, (2500 - phase) / 650) : 0;
        ring.setAttribute("r", radius);
        ring.style.opacity = String(alpha * 0.78);
        echo.setAttribute("r", Math.max(0, radius - 24));
        echo.style.opacity = String(alpha * 0.16);
        const start = lowerBound(((phase - 600) / 2500) * maxRadius);
        const end = lowerBound(((phase + 45) / 2500) * maxRadius);
        const candidates = fixed.slice(start, end).concat(titles);
        const nextLit = new Set();
        for (const target of candidates) {
          if (
            target.overview !==
            (svg.parentElement.dataset.overview === "true")
          )
            continue;
          if (!view.current?.visibleKeys.has(target.clusterKey)) continue;
          // Title positions change with their damped zoom scale. Read the
          // updated world coordinates without restarting the scan cycle.
          if (target.dynamic) {
            target.distance = Math.hypot(
              Number(target.element.dataset.scanX),
              Number(target.element.dataset.scanY),
            );
          }
          // A narrow leading edge, followed by 600 ms of color afterglow.
          const age = phase - (target.distance / maxRadius) * 2500;
          const strength =
            age >= -45 && age < 600
              ? Math.max(0, age < 0 ? 1 + age / 45 : (1 - age / 600) ** 2)
              : 0;
          if (
            Math.abs(strength - target.strength) > 0.015 ||
            (!strength && target.strength)
          ) {
            target.element.style.setProperty(
              "--scan-strength",
              strength.toFixed(3),
            );
            target.strength = strength;
          }
          if (strength) nextLit.add(target);
        }
        for (const target of lit) {
          if (!nextLit.has(target)) {
            target.element.style.removeProperty("--scan-strength");
            target.strength = 0;
          }
        }
        lit = nextLit;
      }
      frame = requestAnimationFrame(paint);
    };
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = null;
      previous = null;
      const running = enabled && !reducedMotion && visible && !document.hidden;
      svg.dataset.scanState = reducedMotion
        ? "reduced"
        : running
          ? "running"
          : "paused";
      if (running) frame = requestAnimationFrame(paint);
      else clear();
    };
    const observer = new window.IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    });
    observer.observe(svg);
    document.addEventListener("visibilitychange", sync);
    sync();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", sync);
      clear();
    };
  }, [svgRef, scene, enabled, reducedMotion, view]);
  return reducedMotion;
}
