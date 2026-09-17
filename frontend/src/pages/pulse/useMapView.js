import { useCallback, useLayoutEffect, useRef } from "react";
import { DEFAULT_ZOOM, MAP_SCALE } from "./useMapCamera.js";

const OVERSCAN = 140;

// Camera frames only touch transforms and the visible decoration layer.
// React retains the full scene and publishes text layout at settled zooms.
export default function useMapView(svgRef, scene, current, subscribe) {
  const view = useRef(null);
  const paint = useCallback((camera) => {
    const model = view.current;
    if (!model) return;
    const { svg, world, width, height, clusters } = model;
    const scale = camera.zoom * MAP_SCALE;
    const titleUnit = (camera.zoom / DEFAULT_ZOOM) ** 0.35 / camera.zoom;
    const labelSize = model.labelBase / camera.zoom ** 0.8;
    const zoomChanged = model.zoom !== camera.zoom;
    model.zoom = camera.zoom;
    model.titleUnit = titleUnit;
    world.style.transform = `translate(50%, 50%) translate(${camera.x * MAP_SCALE}px, ${camera.y * MAP_SCALE}px) scale(${scale})`;
    svg.parentElement.dataset.zoom = String(camera.zoom);
    const left = (-width / 2 - camera.x * MAP_SCALE) / scale;
    const right = (width / 2 - camera.x * MAP_SCALE) / scale;
    const top = (-height / 2 - camera.y * MAP_SCALE) / scale;
    const bottom = (height / 2 - camera.y * MAP_SCALE) / scale;
    const margin = OVERSCAN / scale;
    const visibleKeys = new Set();
    for (const item of clusters) {
      const { cluster, element, heading } = item;
      const halfWidth = Math.max(
        cluster.radius,
        (item.titleWidth * titleUnit) / 2,
      );
      const titleTop =
        cluster.y - cluster.radius - (item.titleHeight + 24) * titleUnit;
      const visible =
        cluster.x + halfWidth >= left - margin &&
        cluster.x - halfWidth <= right + margin &&
        cluster.y + cluster.radius + 32 >= top - margin &&
        titleTop <= bottom + margin;
      if (visible) visibleKeys.add(cluster.issueKey);
      const entered = visible && !item.visible;
      if (visible !== item.visible) {
        element.style.display = visible ? "" : "none";
        element.dataset.rendered = String(visible);
        item.visible = visible;
      }
      if (!visible) continue;
      if (zoomChanged || entered) {
        heading.setAttribute(
          "transform",
          `translate(0 ${-cluster.radius}) scale(${titleUnit})`,
        );
        heading.dataset.scanY = String(
          cluster.y - cluster.radius - item.titleOffset * titleUnit,
        );
        for (const label of item.labels) {
          const ratio = Math.min(labelSize, label.cap) / label.base;
          const transform =
            Math.abs(ratio - 1) < 0.00001 ? "" : `scale(${ratio})`;
          if (label.element.style.transform !== transform)
            label.element.style.transform = transform;
        }
      }
      if (item.callout) {
        const {
          element: callout,
          x,
          y,
          radius,
          base,
          boxWidth,
          boxHeight,
        } = item.callout;
        const ratio = labelSize / base;
        const inset = 8 / scale;
        const cx = Math.max(
          left - cluster.x + inset + (boxWidth * ratio) / 2,
          Math.min(x, right - cluster.x - inset - (boxWidth * ratio) / 2),
        );
        const cy = Math.max(
          top - cluster.y + inset + (boxHeight - 4) * ratio,
          Math.min(y - radius - 16, bottom - cluster.y - inset - 4 * ratio),
        );
        callout.setAttribute(
          "transform",
          `translate(${cx} ${cy}) scale(${ratio})`,
        );
      }
    }
    model.visibleKeys = visibleKeys;
    svg.dataset.renderedClusters = String(visibleKeys.size);
  }, []);

  useLayoutEffect(() => subscribe(paint), [subscribe, paint]);
  useLayoutEffect(() => {
    const svg = svgRef.current;
    const elements = new Map(
      [...svg.querySelectorAll(".document-cluster")].map((element) => [
        element.dataset.issueKey,
        element,
      ]),
    );
    view.current = {
      svg,
      world: svg.querySelector(":scope > g"),
      width: svg.clientWidth,
      height: svg.clientHeight,
      labelBase: window.matchMedia("(max-width: 720px)").matches ? 14 : 13,
      visibleKeys: new Set(),
      clusters: scene.clusters.map((cluster) => {
        const element = elements.get(cluster.issueKey);
        const heading = element.querySelector(".document-cluster__heading");
        const callout = element.querySelector(".document-label-callout");
        return {
          cluster,
          element,
          heading,
          visible:
            element.dataset.rendered === undefined
              ? null
              : element.dataset.rendered === "true",
          titleWidth: Number(heading.dataset.titleWidth),
          titleHeight: Number(heading.dataset.titleHeight),
          titleOffset: Number(heading.dataset.titleOffset),
          labels: [
            ...element.querySelectorAll(".document-node-label__text"),
          ].map((label) => ({
            element: label,
            cap: Number(label.dataset.fontCap),
            base: Number(label.dataset.fontSize),
          })),
          callout: callout && {
            element: callout,
            x: Number(callout.dataset.nodeX),
            y: Number(callout.dataset.nodeY),
            radius: Number(callout.dataset.nodeRadius),
            base: Number(callout.dataset.fontSize),
            boxWidth: Number(callout.dataset.boxWidth),
            boxHeight: Number(callout.dataset.boxHeight),
          },
        };
      }),
    };
    paint(current.current);
  });
  return view;
}
