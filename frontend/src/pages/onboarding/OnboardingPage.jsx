import { ArrowDown, ArrowLeft, ArrowRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import NodeField from "./NodeField";

const SCENES = [
  {
    index: "01",
    short: "wikipulse",
    title: "wikipulse",
    subtitle: "Track. Cluster. Match.",
    body: "Issue-tracking intelligence for matching emerging events with relevant stocks",
  },
  {
    index: "02",
    short: "Track",
    title: "Track",
    body: "Detect unusual activity as it emerges",
    accent: "cyan",
  },
  {
    index: "03",
    short: "Cluster",
    title: "Cluster",
    body: "Turn related signals into emerging events",
    accent: "violet",
  },
  {
    index: "04",
    short: "Match",
    title: "Match",
    body: "Connect events with relevant stocks",
    accent: "gold",
  },
];

const LAST_SCENE_INDEX = SCENES.length - 1;
const WHEEL_STEP_THRESHOLD = 28;
const TOUCH_STEP_THRESHOLD = 48;

function WikiPulseLogo({ nameRef }) {
  return (
    <h1 className="hero-brand" aria-label="WikiPulse">
      <img className="hero-brand__icon" src="/wikipulse-icon.png" alt="" />
      <span ref={nameRef} className="hero-brand__name" aria-hidden="true">
        WIKI<span className="hero-brand__name-accent">PULSE</span>
      </span>
    </h1>
  );
}

function SceneOneSubtitle({ className = "scene-copy__subtitle" }) {
  return (
    <p className={className}>
      Track<span className="brand-dot brand-dot--cyan">.</span> Cluster
      <span className="brand-dot brand-dot--violet">.</span> Match
      <span className="brand-dot brand-dot--gold">.</span>
    </p>
  );
}

function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => window.matchMedia(query).matches,
  );

  useEffect(() => {
    const media = window.matchMedia(query);
    const update = () => setMatches(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [query]);

  return matches;
}

function canUseWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function StaticFallback() {
  return (
    <main className="fallback-experience">
      <header className="fallback-experience__header">
        <span>WIKIPULSE</span>
        <a className="onboarding-enter" href="#/pulse">
          탐색 시작하기 <ArrowRight size={16} />
        </a>
      </header>
      {SCENES.map((item) => (
        <section
          className="fallback-scene"
          data-accent={item.accent}
          key={item.index}
        >
          <span className="fallback-scene__index">{item.index} / 04</span>
          <div>
            {item.index === "01" ? <WikiPulseLogo /> : <h1>{item.title}</h1>}
            {item.subtitle &&
              (item.index === "01" ? (
                <SceneOneSubtitle className="fallback-scene__subtitle" />
              ) : (
                <p className="fallback-scene__subtitle">{item.subtitle}</p>
              ))}
            {item.status && <p className="scene-copy__status">{item.status}</p>}
            {item.body && (
              <p
                className={`fallback-scene__body${item.index === "01" ? " fallback-scene__body--brand" : ""}`}
              >
                {item.body}
              </p>
            )}
          </div>
        </section>
      ))}
      <a className="onboarding-fallback-cta" href="#/pulse">
        Pulse Map 시작하기 <ArrowRight size={18} />
      </a>
    </main>
  );
}

export default function App() {
  const [scene, setScene] = useState(0);
  const [webglAvailable, setWebglAvailable] = useState(canUseWebGL);
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const isMobile = useMediaQuery("(max-width: 720px)");
  const sceneRef = useRef(0);
  const stageRef = useRef(null);
  const heroWordmarkRef = useRef(null);
  const sceneLayerRefs = useRef([]);
  const progressBarRef = useRef(null);
  const scrollMotionRef = useRef({
    progress: 0,
    targetProgress: 0,
    velocity: 0,
    signedVelocity: 0,
    direction: 1,
  });
  const activeScene = SCENES[scene];

  const moveTo = useCallback(
    (target) => {
      const next = Math.min(LAST_SCENE_INDEX, Math.max(0, target));
      const maxScroll = Math.max(
        0,
        document.documentElement.scrollHeight - window.innerHeight,
      );
      window.scrollTo({
        top: maxScroll * (next / LAST_SCENE_INDEX),
        behavior: reducedMotion ? "auto" : "smooth",
      });
    },
    [reducedMotion],
  );

  const moveBy = useCallback(
    (direction) => moveTo(sceneRef.current + direction),
    [moveTo],
  );

  useEffect(() => {
    if (!webglAvailable) return undefined;

    document.documentElement.classList.add("scene-snap-enabled");
    return () =>
      document.documentElement.classList.remove("scene-snap-enabled");
  }, [webglAvailable]);

  useEffect(() => {
    if (!webglAvailable) return undefined;

    const stage = stageRef.current;
    const wordmark = heroWordmarkRef.current;
    if (!stage || !wordmark) return undefined;

    let cancelled = false;
    const syncWordmarkOrigin = () => {
      let offsetTop = 0;
      let element = wordmark;

      while (element && element !== stage) {
        offsetTop += element.offsetTop;
        element = element.offsetParent;
      }

      if (!cancelled && element === stage) {
        stage.style.setProperty("--scene-wordmark-top", `${offsetTop}px`);
      }
    };

    syncWordmarkOrigin();
    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(syncWordmarkOrigin);
    resizeObserver?.observe(stage);
    resizeObserver?.observe(wordmark);
    window.addEventListener("resize", syncWordmarkOrigin);
    document.fonts?.ready.then(syncWordmarkOrigin);

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      window.removeEventListener("resize", syncWordmarkOrigin);
    };
  }, [webglAvailable]);

  useEffect(() => {
    if (!webglAvailable) return undefined;

    let wheelDistance = 0;
    let wheelResetTimer = 0;
    let unlockTimer = 0;
    let unlockAfter = 0;
    let navigationLocked = false;
    let touchStartX = null;
    let touchStartY = null;
    let touchHandled = false;

    const scheduleUnlock = (quietPeriod = 120) => {
      window.clearTimeout(unlockTimer);
      const delay = Math.max(quietPeriod, unlockAfter - performance.now());
      unlockTimer = window.setTimeout(() => {
        navigationLocked = false;
        wheelDistance = 0;
      }, delay);
    };

    const navigateTo = (target) => {
      const next = Math.min(LAST_SCENE_INDEX, Math.max(0, target));
      if (navigationLocked || next === sceneRef.current) return;

      navigationLocked = true;
      wheelDistance = 0;
      unlockAfter = performance.now() + (reducedMotion ? 80 : 1900);
      moveTo(next);
      scheduleUnlock();
    };

    const handleWheel = (event) => {
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      event.preventDefault();

      if (navigationLocked) {
        scheduleUnlock(160);
        return;
      }

      const unitScale =
        event.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? 16
          : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
            ? window.innerHeight
            : 1;
      const delta = event.deltaY * unitScale;
      if (wheelDistance !== 0 && Math.sign(delta) !== Math.sign(wheelDistance))
        wheelDistance = 0;
      wheelDistance += delta;

      window.clearTimeout(wheelResetTimer);
      wheelResetTimer = window.setTimeout(() => {
        wheelDistance = 0;
      }, 180);

      if (Math.abs(wheelDistance) >= WHEEL_STEP_THRESHOLD) {
        navigateTo(sceneRef.current + Math.sign(wheelDistance));
      }
    };

    const handleTouchStart = (event) => {
      const target = event.target;
      if (
        event.touches.length !== 1 ||
        (target instanceof Element &&
          target.closest("button, a, input, textarea, select"))
      ) {
        touchStartX = null;
        touchStartY = null;
        return;
      }

      touchStartX = event.touches[0].clientX;
      touchStartY = event.touches[0].clientY;
      touchHandled = false;
    };

    const handleTouchMove = (event) => {
      if (
        touchStartX === null ||
        touchStartY === null ||
        event.touches.length !== 1
      )
        return;
      const horizontalDistance = touchStartX - event.touches[0].clientX;
      const verticalDistance = touchStartY - event.touches[0].clientY;
      if (Math.abs(verticalDistance) <= Math.abs(horizontalDistance)) return;

      event.preventDefault();
      if (!touchHandled && Math.abs(verticalDistance) >= TOUCH_STEP_THRESHOLD) {
        touchHandled = true;
        navigateTo(sceneRef.current + Math.sign(verticalDistance));
      }
    };

    const resetTouch = () => {
      touchStartX = null;
      touchStartY = null;
      touchHandled = false;
    };

    const handleKeyDown = (event) => {
      const target = event.target;
      if (
        event.repeat ||
        (target instanceof Element &&
          target.closest("input, textarea, select, [contenteditable='true']"))
      )
        return;

      let targetScene = null;
      if (
        event.key === "ArrowDown" ||
        event.key === "PageDown" ||
        (event.key === " " && !event.shiftKey)
      ) {
        targetScene = sceneRef.current + 1;
      } else if (
        event.key === "ArrowUp" ||
        event.key === "PageUp" ||
        (event.key === " " && event.shiftKey)
      ) {
        targetScene = sceneRef.current - 1;
      } else if (event.key === "Home") {
        targetScene = 0;
      } else if (event.key === "End") {
        targetScene = LAST_SCENE_INDEX;
      }

      if (targetScene === null) return;
      event.preventDefault();
      navigateTo(targetScene);
    };

    window.addEventListener("wheel", handleWheel, { passive: false });
    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: false });
    window.addEventListener("touchend", resetTouch, { passive: true });
    window.addEventListener("touchcancel", resetTouch, { passive: true });
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.clearTimeout(wheelResetTimer);
      window.clearTimeout(unlockTimer);
      window.removeEventListener("wheel", handleWheel);
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", resetTouch);
      window.removeEventListener("touchcancel", resetTouch);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [moveTo, reducedMotion, webglAvailable]);

  useEffect(() => {
    if (!webglAvailable) return undefined;
    let animationFrame = 0;
    let lastTime = performance.now();
    let lastScrollY = window.scrollY;
    let displayProgress = 0;
    let previousProgress = 0;
    let signedVelocity = 0;
    let initialized = false;

    const ambientSaturation = [1, 1.12, 1.16, 0.98];
    const ambientBrightness = [1, 0.82, 0.76, 0.68];
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const interpolateStops = (stops, progress) => {
      const from = Math.min(stops.length - 1, Math.floor(progress));
      const to = Math.min(stops.length - 1, from + 1);
      const amount = progress - from;
      return stops[from] + (stops[to] - stops[from]) * amount;
    };

    const renderFrame = (now) => {
      const deltaSeconds = clamp((now - lastTime) / 1000, 1 / 240, 0.05);
      const scrollY = window.scrollY;
      const maxScroll = Math.max(
        1,
        document.documentElement.scrollHeight - window.innerHeight,
      );
      const targetProgress = clamp(
        (scrollY / maxScroll) * LAST_SCENE_INDEX,
        0,
        LAST_SCENE_INDEX,
      );

      if (!initialized) {
        displayProgress = targetProgress;
        previousProgress = targetProgress;
        initialized = true;
      } else if (reducedMotion) {
        displayProgress = targetProgress;
      } else {
        const progressResponse = 1 - Math.exp(-2 * deltaSeconds);
        displayProgress +=
          (targetProgress - displayProgress) * progressResponse;
      }

      const scrollDelta = scrollY - lastScrollY;
      const instantVelocity = clamp(
        scrollDelta / (window.innerHeight * deltaSeconds * 1.35),
        -1,
        1,
      );
      const progressVelocity = clamp(
        (displayProgress - previousProgress) / (deltaSeconds * 2.2),
        -1,
        1,
      );
      const velocityTarget =
        Math.abs(instantVelocity) > 0.001 ? instantVelocity : progressVelocity;
      const velocityResponse =
        Math.abs(velocityTarget) > Math.abs(signedVelocity) ? 18 : 4.2;
      signedVelocity +=
        (velocityTarget - signedVelocity) *
        (1 - Math.exp(-velocityResponse * deltaSeconds));
      if (
        Math.abs(scrollDelta) < 0.1 &&
        Math.abs(targetProgress - displayProgress) < 0.001
      ) {
        signedVelocity *= Math.exp(-3.8 * deltaSeconds);
      }
      if (Math.abs(signedVelocity) < 0.001) signedVelocity = 0;

      const motion = scrollMotionRef.current;
      motion.progress = displayProgress;
      motion.targetProgress = targetProgress;
      motion.signedVelocity = reducedMotion ? 0 : signedVelocity;
      motion.velocity = reducedMotion ? 0 : Math.abs(signedVelocity);
      if (signedVelocity !== 0) motion.direction = Math.sign(signedVelocity);

      const nextScene = clamp(
        Math.round(displayProgress),
        0,
        SCENES.length - 1,
      );
      if (nextScene !== sceneRef.current) {
        sceneRef.current = nextScene;
        setScene(nextScene);
      }

      sceneLayerRefs.current.forEach((element, index) => {
        if (!element) return;
        const distance = index - displayProgress;
        const absoluteDistance = Math.abs(distance);
        const visibleAmount =
          absoluteDistance >= 1
            ? 0
            : Math.pow(Math.cos(absoluteDistance * Math.PI * 0.5), 1.18);
        const translateY = reducedMotion
          ? 0
          : distance * Math.min(window.innerHeight * 0.14, 126);
        const blur = reducedMotion ? 0 : Math.min(10, absoluteDistance * 8);
        const opacity = reducedMotion
          ? index === nextScene
            ? 1
            : 0
          : visibleAmount;
        element.style.opacity = opacity.toFixed(4);
        element.style.transform = `translate3d(0, ${translateY.toFixed(2)}px, 0)`;
        element.style.filter = `blur(${blur.toFixed(2)}px)`;
      });

      if (stageRef.current) {
        stageRef.current.style.setProperty(
          "--ambient-saturation",
          interpolateStops(ambientSaturation, displayProgress).toFixed(3),
        );
        stageRef.current.style.setProperty(
          "--ambient-brightness",
          interpolateStops(ambientBrightness, displayProgress).toFixed(3),
        );
      }
      if (progressBarRef.current) {
        progressBarRef.current.style.transform = `scaleX(${(displayProgress / (SCENES.length - 1)).toFixed(5)})`;
      }

      lastTime = now;
      lastScrollY = scrollY;
      previousProgress = displayProgress;
      animationFrame = requestAnimationFrame(renderFrame);
    };

    animationFrame = requestAnimationFrame(renderFrame);

    return () => {
      cancelAnimationFrame(animationFrame);
    };
  }, [reducedMotion, webglAvailable]);

  if (!webglAvailable) return <StaticFallback />;

  return (
    <main className="experience-scroll">
      <div className="scene-snap-track" aria-hidden="true">
        {SCENES.map((item) => (
          <div className="scene-snap-anchor" key={item.index} />
        ))}
      </div>
      <div
        ref={stageRef}
        className="experience"
        data-scene={scene + 1}
        data-reduced-motion={reducedMotion}
      >
        <div className="ambient-field" aria-hidden="true" />
        <div className="node-field" aria-hidden="true">
          <NodeField
            isMobile={isMobile}
            reducedMotion={reducedMotion}
            scrollMotionRef={scrollMotionRef}
            onUnavailable={(event) => {
              event?.preventDefault();
              setWebglAvailable(false);
            }}
          />
        </div>

        <header className="topline">
          <div className="wordmark" aria-label="WikiPulse">
            <span className="wordmark__name">WIKIPULSE</span>
            <span className="wordmark__descriptor">SIGNAL INTELLIGENCE</span>
          </div>
          <div
            className="scene-count"
            aria-label={`장면 ${scene + 1}, 총 ${SCENES.length}개`}
          >
            <span>{activeScene.index}</span>
            <span className="scene-count__divider" />
            <span>04</span>
          </div>
        </header>

        <nav className="scene-rail" aria-label="온보딩 장면">
          {SCENES.map((item, index) => (
            <button
              className="scene-rail__step"
              data-active={index === scene}
              key={item.index}
              type="button"
              onClick={() => moveTo(index)}
              aria-current={index === scene ? "step" : undefined}
              aria-label={`${item.index}. ${item.short}`}
            >
              <span>{item.index}</span>
            </button>
          ))}
        </nav>

        <div className="scene-copy-stack" aria-live="polite">
          {SCENES.map((item, index) => (
            <section
              ref={(element) => {
                sceneLayerRefs.current[index] = element;
              }}
              className={`scene-copy scene-copy-layer${index === 0 ? " scene-copy--hero" : ""}`}
              data-accent={item.accent}
              key={item.index}
              aria-hidden={index !== scene}
              style={index === 0 ? { opacity: 1 } : { opacity: 0 }}
            >
              {index === 0 ? (
                <div className="scene-copy__hero">
                  <WikiPulseLogo nameRef={heroWordmarkRef} />
                  <SceneOneSubtitle />
                  <p className="scene-copy__body scene-copy__body--brand">
                    {item.body}
                  </p>
                  <div className="scroll-cue" aria-hidden="true">
                    <ArrowDown size={15} strokeWidth={1.5} />
                    <span>SCROLL TO TRACE</span>
                  </div>
                </div>
              ) : (
                <>
                  <h1>{item.title}</h1>
                  {(item.status || item.body) && (
                    <div className="scene-copy__detail">
                      {item.status && (
                        <p className="scene-copy__status">{item.status}</p>
                      )}
                      {item.body && (
                        <p className="scene-copy__body">{item.body}</p>
                      )}
                    </div>
                  )}
                </>
              )}
            </section>
          ))}
        </div>

        <a
          className={`onboarding-enter onboarding-enter--fixed${scene === LAST_SCENE_INDEX ? " onboarding-enter--ready" : ""}`}
          href="#/pulse"
        >
          {scene === LAST_SCENE_INDEX ? "Pulse Map 시작하기" : "탐색 시작하기"}
          <ArrowRight size={17} />
        </a>

        <div className="mobile-controls" aria-label="장면 이동">
          <button
            type="button"
            onClick={() => moveBy(-1)}
            disabled={scene === 0}
            aria-label="이전 장면"
          >
            <ArrowLeft size={19} strokeWidth={1.5} />
          </button>
          <span>{activeScene.short}</span>
          <button
            type="button"
            onClick={() => moveBy(1)}
            disabled={scene === SCENES.length - 1}
            aria-label="다음 장면"
          >
            <ArrowRight size={19} strokeWidth={1.5} />
          </button>
        </div>

        <div className="progress-track" aria-hidden="true">
          <span ref={progressBarRef} />
        </div>
      </div>
    </main>
  );
}
