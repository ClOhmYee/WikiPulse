import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

const COLORS = {
  dim: new THREE.Color("#365d69"),
  teal: new THREE.Color("#86c9c4"),
  paper: new THREE.Color("#f3f7f7"),
  white: new THREE.Color("#ffffff"),
  gold: new THREE.Color("#dbb057"),
  shadow: new THREE.Color("#172d37"),
};

const MAX_EDGES = 4200;
const GLOW_PULSE_RADIANS_PER_SECOND = (Math.PI * 2) / 0.7;
const MATCH_PRICE_COLOR_START = 0.68;

const COSMIC_VERTEX_SHADER = `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const COSMIC_FRAGMENT_SHADER = `
  uniform float uTime;
  uniform float uIntensity;
  varying vec2 vUv;

  float hash(vec2 point) {
    return fract(sin(dot(point, vec2(127.1, 311.7))) * 43758.5453);
  }

  float noise(vec2 point) {
    vec2 cell = floor(point);
    vec2 local = fract(point);
    vec2 curve = local * local * (3.0 - 2.0 * local);
    return mix(
      mix(hash(cell), hash(cell + vec2(1.0, 0.0)), curve.x),
      mix(hash(cell + vec2(0.0, 1.0)), hash(cell + vec2(1.0, 1.0)), curve.x),
      curve.y
    );
  }

  float fbm(vec2 point) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int octave = 0; octave < 5; octave++) {
      value += amplitude * noise(point);
      point *= 2.03;
      amplitude *= 0.5;
    }
    return value;
  }

  void main() {
    vec2 uv = (vUv - 0.5) * vec2(2.05, 1.18);
    float time = uTime * 0.022;
    vec2 warpA = vec2(fbm(uv * 1.7 + vec2(0.0, time)), fbm(uv * 1.7 + vec2(4.8, -time * 0.82)));
    vec2 warpB = vec2(fbm(uv * 2.2 + warpA * 1.9 + vec2(1.6, 8.4)), fbm(uv * 2.0 + warpA * 1.6 + vec2(7.9, 2.4)));
    float cloud = smoothstep(0.28, 0.94, fbm(uv * 1.2 + warpB * 1.75));
    float goldTrace = smoothstep(0.76, 1.0, cloud);
    vec3 teal = vec3(0.10, 0.31, 0.38);
    vec3 gold = vec3(0.48, 0.32, 0.12);
    vec3 color = teal * cloud + gold * goldTrace * 0.42;
    gl_FragColor = vec4(color * uIntensity, cloud * 0.38);
  }
`;

function createRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let result = value;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

function createPointTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const context = canvas.getContext("2d");
  const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.55, "rgba(255,255,255,1)");
  gradient.addColorStop(0.78, "rgba(255,255,255,0.55)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 64, 64);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function createGlowTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const context = canvas.getContext("2d");
  const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.16, "rgba(255,255,255,0.88)");
  gradient.addColorStop(0.42, "rgba(255,255,255,0.34)");
  gradient.addColorStop(0.72, "rgba(255,255,255,0.08)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 64, 64);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function writePosition(array, index, x, y, z) {
  const offset = index * 3;
  array[offset] = x;
  array[offset + 1] = y;
  array[offset + 2] = z;
}

function paint(array, index, color) {
  const offset = index * 3;
  array[offset] = color.r;
  array[offset + 1] = color.g;
  array[offset + 2] = color.b;
}

function distanceSquared(positions, a, b) {
  const aOffset = a * 3;
  const bOffset = b * 3;
  const dx = positions[aOffset] - positions[bOffset];
  const dy = positions[aOffset + 1] - positions[bOffset + 1];
  const dz = positions[aOffset + 2] - positions[bOffset + 2];
  return dx * dx + dy * dy + dz * dz;
}

function connectNearest(positions, indices, limit, maxDistance, color) {
  const edges = [];
  const used = new Set();
  const threshold = maxDistance * maxDistance;

  for (
    let cursor = 0;
    cursor < indices.length && edges.length < limit;
    cursor += 1
  ) {
    const source = indices[cursor];
    let nearest = -1;
    let nearestDistance = Number.POSITIVE_INFINITY;

    for (
      let targetCursor = 0;
      targetCursor < indices.length;
      targetCursor += 1
    ) {
      const target = indices[targetCursor];
      if (target === source) continue;
      const distance = distanceSquared(positions, source, target);
      if (distance < nearestDistance) {
        nearest = target;
        nearestDistance = distance;
      }
    }

    const key =
      source < nearest ? `${source}:${nearest}` : `${nearest}:${source}`;
    if (nearest >= 0 && nearestDistance < threshold && !used.has(key)) {
      used.add(key);
      edges.push({ a: source, b: nearest, color });
    }
  }

  return edges;
}

function connectWithinDistance(positions, count, maxDistance, color) {
  const edges = [];
  const threshold = maxDistance * maxDistance;

  for (let source = 0; source < count; source += 1) {
    for (let target = source + 1; target < count; target += 1) {
      if (distanceSquared(positions, source, target) < threshold) {
        edges.push({ a: source, b: target, color });
      }
    }
  }

  return edges;
}

function createFieldData(count, isMobile) {
  const random = createRandom(0xc4885e62);
  const positions = Array.from(
    { length: 4 },
    () => new Float32Array(count * 3),
  );
  const colors = Array.from({ length: 4 }, () => new Float32Array(count * 3));
  const scales = Array.from({ length: 4 }, () => new Float32Array(count));
  const clusterCount = Math.floor(count * 0.43);
  const anomalyCount = Math.max(8, Math.floor(count * 0.11));
  const remainingCount = count - clusterCount;

  for (let index = 0; index < count; index += 1) {
    const radius = 0.6 + random() * 1.7;
    const azimuth = random() * Math.PI * 2;
    const polar = Math.acos(2 * random() - 1);
    const x = radius * Math.sin(polar) * Math.cos(azimuth);
    const y = radius * Math.sin(polar) * Math.sin(azimuth);
    const z = radius * Math.cos(polar);

    writePosition(positions[0], index, x, y, z);
    writePosition(positions[1], index, x, y, z);
    scales[0][index] = 1;
    scales[1][index] = 1;
    paint(colors[0], index, COLORS.white);
    paint(colors[1], index, COLORS.white);
  }

  for (let index = 0; index < anomalyCount; index += 1) {
    const positionOffset = index * 3;
    positions[1][positionOffset + 2] += (random() * 2 - 1) * 0.08;
    scales[1][index] = 1.15 + random() * 0.46;
  }

  for (let index = 0; index < count; index += 1) {
    if (index < clusterCount) {
      const progress = index / clusterCount;
      const angle = index * 2.399963 + Math.sin(index * 0.73) * 0.14;
      const radius = 0.2 + Math.sqrt(progress) * (isMobile ? 1.7 : 2.25);
      const centerX = isMobile ? 0.35 : 1.25;
      const x = centerX + Math.cos(angle) * radius * (0.9 + random() * 0.12);
      const y = 0.62 + Math.sin(angle) * radius * (0.66 + random() * 0.12);
      const z = (random() * 2 - 1) * 0.65 * (1 - progress * 0.4);
      writePosition(positions[2], index, x, y, z);
      scales[2][index] = 0.82 + random() * 0.8;
      paint(
        colors[2],
        index,
        index < anomalyCount
          ? COLORS.gold
          : index % 5 === 0
            ? COLORS.paper
            : COLORS.teal,
      );

      const clusterTargetX = 0;
      const clusterTargetY = isMobile ? 1.55 : 0.25;
      const clusterScale = isMobile ? 0.55 : 0.72;
      writePosition(
        positions[3],
        index,
        clusterTargetX + (x - centerX) * clusterScale,
        clusterTargetY + (y - 0.62) * clusterScale,
        z * 0.72,
      );
      scales[3][index] = scales[2][index] * 0.86;
      paint(colors[3], index, index < anomalyCount ? COLORS.gold : COLORS.teal);
    } else {
      const peripheralIndex = index - clusterCount;
      const angle = peripheralIndex * 2.399963 + (random() * 2 - 1) * 0.22;
      const radius =
        (isMobile ? 2.08 : 3.15) + random() * (isMobile ? 1.08 : 1.72);
      const centerX = isMobile ? 0.35 : 1.25;
      const x = centerX + Math.cos(angle) * radius * (isMobile ? 0.78 : 1.04);
      const y = 0.62 + Math.sin(angle) * radius * (isMobile ? 0.88 : 0.72);
      const z = (random() * 2 - 1) * (0.86 + random() * 0.92);
      writePosition(positions[2], index, x, y, z);
      scales[2][index] = 0.58 + random() * 0.48;
      paint(colors[2], index, COLORS.dim);
    }
  }

  const priceCount = Math.max(12, Math.floor(remainingCount * 0.7));
  const chartStart = isMobile ? -1.65 : 2.4;
  const chartWidth = isMobile ? 3.3 : 4.15;
  const chartBaselineY = isMobile ? -0.95 : -0.38;
  const volumeBaselineY = isMobile ? -2.4 : -1.7;
  const priceRise = isMobile ? 1.1 : 1.25;
  const primaryWave = isMobile ? 0.32 : 0.4;
  const secondaryWave = isMobile ? 0.09 : 0.11;
  const volumeScale = isMobile ? 0.42 : 0.5;

  for (let offset = 0; offset < remainingCount; offset += 1) {
    const index = clusterCount + offset;
    if (offset < priceCount) {
      const progress = offset / Math.max(1, priceCount - 1);
      const x = chartStart + progress * chartWidth;
      const y =
        chartBaselineY +
        progress * priceRise +
        Math.sin(progress * 10.6) * primaryWave +
        Math.sin(progress * 25.2) * secondaryWave;
      writePosition(positions[3], index, x, y, (random() - 0.5) * 0.14);
      scales[3][index] = offset % 7 === 0 ? 1.04 : 0.72;
      paint(colors[3], index, offset % 7 === 0 ? COLORS.paper : COLORS.gold);
    } else {
      const volumeIndex = offset - priceCount;
      const volumeCount = remainingCount - priceCount;
      const progress = volumeIndex / Math.max(1, volumeCount - 1);
      const height = 0.24 + random() * 1.03;
      writePosition(
        positions[3],
        index,
        chartStart + progress * chartWidth,
        volumeBaselineY + height * volumeScale,
        -0.18,
      );
      scales[3][index] = 0.48 + height * 0.28;
      paint(colors[3], index, COLORS.teal);
    }
  }

  const sceneOffsets = isMobile ? [0, 0, 0.32, 0] : [0, 0, 1, 0];
  positions.forEach((scenePositions, sceneIndex) => {
    for (let index = 0; index < count; index += 1) {
      scenePositions[index * 3] += sceneOffsets[sceneIndex];
    }
  });

  const allIndices = Array.from({ length: count }, (_, index) => index);
  const clusterIndices = allIndices.slice(0, clusterCount);
  const sceneZeroEdges = connectWithinDistance(
    positions[0],
    count,
    0.51,
    COLORS.white,
  );
  const sceneOneEdges = [];
  const clusterEdges = connectNearest(
    positions[2],
    clusterIndices,
    Math.floor(clusterCount * 1.4),
    0.86,
    COLORS.teal,
  );
  const sceneThreeEdges = connectNearest(
    positions[3],
    clusterIndices,
    Math.floor(clusterCount * 1.3),
    0.76,
    COLORS.teal,
  );

  for (let offset = 0; offset < priceCount - 1; offset += 1) {
    sceneThreeEdges.push({
      a: clusterCount + offset,
      b: clusterCount + offset + 1,
      color: COLORS.gold,
      revealStart: 0.58,
    });
  }

  const bridgeAxis = isMobile ? 1 : 0;
  const orderingAxis = isMobile ? 0 : 1;
  const bridgeCount = 5;
  const clusterBoundary = [...clusterIndices]
    .sort((a, b) => {
      const aValue = positions[3][a * 3 + bridgeAxis];
      const bValue = positions[3][b * 3 + bridgeAxis];
      return isMobile ? aValue - bValue : bValue - aValue;
    })
    .slice(0, Math.ceil(clusterCount * 0.4))
    .sort(
      (a, b) =>
        positions[3][a * 3 + orderingAxis] - positions[3][b * 3 + orderingAxis],
    );
  const chartBoundary = [0.08, 0.26, 0.44, 0.62, 0.82]
    .map((progress) => clusterCount + Math.round((priceCount - 1) * progress))
    .sort(
      (a, b) =>
        positions[3][a * 3 + orderingAxis] - positions[3][b * 3 + orderingAxis],
    );
  const sampleBoundary = (indices, index) =>
    indices[
      Math.round((indices.length - 1) * ((index + 1) / (bridgeCount + 1)))
    ];

  for (let index = 0; index < bridgeCount; index += 1) {
    sceneThreeEdges.push({
      a: sampleBoundary(clusterBoundary, index),
      b: chartBoundary[index],
      color: COLORS.paper,
      revealStart: 0.78,
    });
  }

  const motion = new Float32Array(count * 4);
  for (let index = 0; index < count; index += 1) {
    const offset = index * 4;
    motion[offset] = random() * Math.PI * 2;
    motion[offset + 1] = 0.16 + random() * 0.24;
    motion[offset + 2] = 0.025 + random() * 0.055;
    motion[offset + 3] = 0.035 + random() * 0.08;
  }

  return {
    positions,
    colors,
    scales,
    edges: [sceneZeroEdges, sceneOneEdges, clusterEdges, sceneThreeEdges],
    clusterCount,
    anomalyCount,
    priceCount,
    motion,
  };
}

function CosmicBackdrop({ scrollMotionRef, reducedMotion }) {
  const materialRef = useRef(null);
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uIntensity: { value: 0.74 },
    }),
    [],
  );

  useFrame((_, delta) => {
    if (!materialRef.current) return;
    if (!reducedMotion) materialRef.current.uniforms.uTime.value += delta;
    const progress = THREE.MathUtils.clamp(
      scrollMotionRef.current.progress,
      0,
      3,
    );
    const fromScene = Math.min(3, Math.floor(progress));
    const toScene = Math.min(3, fromScene + 1);
    const amount = progress - fromScene;
    const intensityStops = [0.7, 0.78, 0.88, 0.96];
    const targetIntensity = THREE.MathUtils.lerp(
      intensityStops[fromScene],
      intensityStops[toScene],
      amount,
    );
    materialRef.current.uniforms.uIntensity.value = reducedMotion
      ? targetIntensity
      : THREE.MathUtils.damp(
          materialRef.current.uniforms.uIntensity.value,
          targetIntensity,
          2.2,
          delta,
        );
  });

  return (
    <mesh position={[0, 0, -7]} renderOrder={-10} frustumCulled={false}>
      <planeGeometry args={[32, 20]} />
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={COSMIC_VERTEX_SHADER}
        fragmentShader={COSMIC_FRAGMENT_SHADER}
        transparent
        depthTest={false}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}

function FPlusStarField({ scrollMotionRef, reducedMotion }) {
  const isCompact = useThree((state) => state.size.width < 700);
  const count = isCompact ? 560 : 950;
  const mainRef = useRef(null);
  const rotationRef = useRef(0);
  const pointTexture = useMemo(() => createPointTexture(), []);
  const geometries = useMemo(() => {
    const random = createRandom(0xf10a57a2 + count);
    const leftwardPositions = [];
    const leftwardColors = [];
    const remainingPositions = [];
    const remainingColors = [];

    for (let index = 0; index < count; index += 1) {
      const z = 5.2 - Math.pow(random(), 1.3) * 21;
      const spread = 3 + (5.2 - z) * 0.5;
      const x = (random() - 0.5) * 2 * spread;
      const y = (random() - 0.5) * 2 * spread;
      const colorRoll = random();
      const color =
        colorRoll < 0.33
          ? COLORS.gold
          : colorRoll < 0.665
            ? COLORS.teal
            : COLORS.white;
      const positions = z < 0 ? leftwardPositions : remainingPositions;
      const colors = z < 0 ? leftwardColors : remainingColors;
      positions.push(x, y, z);
      colors.push(color.r, color.g, color.b);
    }

    const createGeometry = (positions, colors) => {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(positions, 3),
      );
      geometry.setAttribute(
        "color",
        new THREE.Float32BufferAttribute(colors, 3),
      );
      return geometry;
    };

    return {
      leftward: createGeometry(leftwardPositions, leftwardColors),
      remaining: createGeometry(remainingPositions, remainingColors),
    };
  }, [count]);

  useEffect(
    () => () => {
      geometries.leftward.dispose();
      geometries.remaining.dispose();
      pointTexture.dispose();
    },
    [geometries, pointTexture],
  );

  useFrame((_, delta) => {
    if (!mainRef.current) return;
    const signedScrollVelocity = reducedMotion
      ? 0
      : scrollMotionRef.current.signedVelocity;
    const baseAngularVelocity = isCompact ? 0.02 : 0.04;
    const angularVelocity = reducedMotion
      ? 0
      : baseAngularVelocity + signedScrollVelocity * (isCompact ? 0.48 : 0.68);
    rotationRef.current += angularVelocity * delta;
    mainRef.current.rotation.y = rotationRef.current;
  });

  const pointMaterial = (size) => (
    <pointsMaterial
      size={size}
      sizeAttenuation
      map={pointTexture}
      vertexColors
      transparent
      opacity={0.85}
      depthWrite={false}
      blending={THREE.NormalBlending}
    />
  );

  return (
    <group renderOrder={-5}>
      <group ref={mainRef}>
        <points
          geometry={geometries.leftward}
          renderOrder={-5}
          frustumCulled={false}
        >
          {pointMaterial(0.06)}
        </points>
        <points
          geometry={geometries.remaining}
          renderOrder={-5}
          frustumCulled={false}
        >
          {pointMaterial(0.054)}
        </points>
      </group>
    </group>
  );
}

function Field({ scrollMotionRef, isMobile, reducedMotion }) {
  const isFPlusCompact = useThree((state) => state.size.width < 700);
  const count = 350;
  const data = useMemo(
    () => createFieldData(count, isMobile),
    [count, isMobile],
  );
  const groupRef = useRef(null);
  const pointsRef = useRef(null);
  const glowRef = useRef(null);
  const lineRef = useRef(null);
  const previousPointer = useRef({ x: 0, y: 0 });
  const pointerVelocity = useRef(0);
  const renderedPositions = useRef(data.positions[0].slice());
  const currentColors = useRef(data.colors[0].slice());
  const glowCount = Math.ceil(data.clusterCount / 4);
  const glowPositions = useMemo(
    () => new Float32Array(glowCount * 3),
    [glowCount],
  );
  const glowColors = useMemo(
    () => new Float32Array(glowCount * 3),
    [glowCount],
  );
  const linePositions = useMemo(() => new Float32Array(MAX_EDGES * 12), []);
  const lineColors = useMemo(() => new Float32Array(MAX_EDGES * 8), []);
  const pointTexture = useMemo(() => createPointTexture(), []);
  const glowTexture = useMemo(() => createGlowTexture(), []);
  const coarsePointer = useMemo(
    () => window.matchMedia("(pointer: coarse)").matches,
    [],
  );

  useEffect(() => {
    const positionAttribute = lineRef.current?.geometry.attributes.position;
    const colorAttribute = lineRef.current?.geometry.attributes.color;
    const pointPositionAttribute =
      pointsRef.current?.geometry.attributes.position;
    const pointColorAttribute = pointsRef.current?.geometry.attributes.color;
    const glowPositionAttribute = glowRef.current?.geometry.attributes.position;
    const glowColorAttribute = glowRef.current?.geometry.attributes.color;
    positionAttribute?.setUsage(THREE.DynamicDrawUsage);
    colorAttribute?.setUsage(THREE.DynamicDrawUsage);
    pointPositionAttribute?.setUsage(THREE.DynamicDrawUsage);
    pointColorAttribute?.setUsage(THREE.DynamicDrawUsage);
    glowPositionAttribute?.setUsage(THREE.DynamicDrawUsage);
    glowColorAttribute?.setUsage(THREE.DynamicDrawUsage);
    if (groupRef.current) {
      groupRef.current.position.x = isFPlusCompact ? 0 : 1.7;
      groupRef.current.scale.setScalar(isFPlusCompact ? 0.55 : 1);
    }
  }, [isFPlusCompact]);

  useEffect(
    () => () => {
      pointTexture.dispose();
      glowTexture.dispose();
    },
    [glowTexture, pointTexture],
  );

  useFrame((state, delta) => {
    const points = pointsRef.current;
    const glow = glowRef.current;
    const lines = lineRef.current;
    if (!points || !glow || !lines) return;

    const rawProgress = THREE.MathUtils.clamp(
      scrollMotionRef.current.progress,
      0,
      3,
    );
    const discreteScene = Math.round(rawProgress);
    const fromScene = reducedMotion
      ? discreteScene
      : Math.min(3, Math.floor(rawProgress));
    const toScene = reducedMotion ? discreteScene : Math.min(3, fromScene + 1);
    const rawSegmentProgress = reducedMotion ? 0 : rawProgress - fromScene;
    const segmentProgress =
      rawSegmentProgress * rawSegmentProgress * (3 - 2 * rawSegmentProgress);
    const fromPositions = data.positions[fromScene];
    const toPositions = data.positions[toScene];
    const fromColors = data.colors[fromScene];
    const toColors = data.colors[toScene];
    const elapsed = state.clock.getElapsedTime();
    const pointerX = state.pointer.x * state.viewport.width * 0.5;
    const pointerY = state.pointer.y * state.viewport.height * 0.5;
    const interactionRadius = isMobile ? 1.45 : 2.75;
    const interpolateSceneValue = (values) =>
      THREE.MathUtils.lerp(values[fromScene], values[toScene], segmentProgress);
    const interactionStrength = reducedMotion
      ? 0
      : interpolateSceneValue([0, 0, 0.38, 0.3]);
    const driftStrength = interpolateSceneValue([0, 0.62, 0.26, 0.2]);
    const depthStrength = interpolateSceneValue([0, 0.7, 0.28, 0.22]);
    const heroExit = THREE.MathUtils.clamp((rawProgress - 1) / 0.92, 0, 1);
    const heroInfluence = reducedMotion
      ? discreteScene <= 1
        ? 1
        : 0
      : 1 - heroExit * heroExit * (3 - 2 * heroExit);
    const isTrackTransition = fromScene === 0 && toScene === 1;
    const isMatchTransition = fromScene === 2 && toScene === 3;
    const trackBurst =
      reducedMotion || !isTrackTransition
        ? 0
        : Math.sin(segmentProgress * Math.PI);
    const rawTrackArrival = reducedMotion
      ? 0
      : THREE.MathUtils.clamp(rawProgress, 0, 1);
    const trackArrival =
      rawTrackArrival * rawTrackArrival * (3 - 2 * rawTrackArrival);
    const pointerDelta =
      Math.hypot(
        state.pointer.x - previousPointer.current.x,
        state.pointer.y - previousPointer.current.y,
      ) * 0.5;

    pointerVelocity.current *= 0.96;
    if (!coarsePointer && pointerDelta > 0) {
      pointerVelocity.current = Math.min(
        0.85,
        pointerVelocity.current + pointerDelta * 3.5,
      );
    }
    previousPointer.current.x = state.pointer.x;
    previousPointer.current.y = state.pointer.y;

    const scrollEnergy = reducedMotion ? 0 : scrollMotionRef.current.velocity;
    const rawMatchPriceColorProgress = THREE.MathUtils.clamp(
      (rawSegmentProgress - MATCH_PRICE_COLOR_START) /
        (1 - MATCH_PRICE_COLOR_START),
      0,
      1,
    );
    const matchPriceColorProgress =
      rawMatchPriceColorProgress *
      rawMatchPriceColorProgress *
      (3 - 2 * rawMatchPriceColorProgress);
    for (let index = 0; index < count; index += 1) {
      const positionOffset = index * 3;
      const isChartNode = index >= data.clusterCount;
      const isPriceNode =
        isChartNode && index < data.clusterCount + data.priceCount;
      const chartStreamProgress =
        isMatchTransition && isChartNode
          ? 1 - (1 - rawSegmentProgress) * (1 - rawSegmentProgress)
          : segmentProgress;
      const colorProgress =
        isMatchTransition && isPriceNode
          ? matchPriceColorProgress
          : chartStreamProgress;
      const x = THREE.MathUtils.lerp(
        fromPositions[positionOffset],
        toPositions[positionOffset],
        chartStreamProgress,
      );
      const y = THREE.MathUtils.lerp(
        fromPositions[positionOffset + 1],
        toPositions[positionOffset + 1],
        chartStreamProgress,
      );
      const z = THREE.MathUtils.lerp(
        fromPositions[positionOffset + 2],
        toPositions[positionOffset + 2],
        chartStreamProgress,
      );
      const motionOffset = index * 4;
      const phase = data.motion[motionOffset];
      const speed = data.motion[motionOffset + 1];
      const fplusDrift =
        0.13 + pointerVelocity.current * 0.3 + scrollEnergy * 0.08;
      const fplusVelocityDrift =
        pointerVelocity.current * 0.06 + scrollEnergy * 0.025;
      const driftAmplitude = data.motion[motionOffset + 2] * driftStrength;
      const depthAmplitude = data.motion[motionOffset + 3] * depthStrength;
      const heroDriftX =
        Math.sin(elapsed * 0.5 + phase) * fplusDrift +
        Math.sin(elapsed * 1.4 + phase * 2.1) * fplusVelocityDrift;
      const heroDriftY =
        Math.cos(elapsed * 0.4 + phase) * fplusDrift +
        Math.cos(elapsed * 1.2 + phase * 1.7) * fplusVelocityDrift;
      const heroDriftZ =
        Math.sin(elapsed * 0.45 + phase * 1.3) * fplusDrift +
        Math.sin(elapsed * 1.6 + phase) * fplusVelocityDrift;
      const ambientDriftX = Math.sin(elapsed * speed + phase) * driftAmplitude;
      const ambientDriftY =
        Math.cos(elapsed * speed * 0.82 + phase * 1.31) * driftAmplitude * 0.72;
      const ambientDriftZ =
        Math.sin(elapsed * speed * 0.64 + phase * 0.73) * depthAmplitude;
      const driftX = reducedMotion
        ? 0
        : THREE.MathUtils.lerp(ambientDriftX, heroDriftX, heroInfluence);
      const driftY = reducedMotion
        ? 0
        : THREE.MathUtils.lerp(ambientDriftY, heroDriftY, heroInfluence);
      const driftZ = reducedMotion
        ? 0
        : THREE.MathUtils.lerp(ambientDriftZ, heroDriftZ, heroInfluence);
      const transitionArc =
        reducedMotion || isTrackTransition || (isMatchTransition && isChartNode)
          ? 0
          : Math.sin(segmentProgress * Math.PI);
      const arcX = Math.cos(phase) * transitionArc * 0.22;
      const arcY = Math.sin(phase) * transitionArc * 0.16;
      const arcZ = Math.sin(phase * 0.61) * transitionArc * 0.42;
      let renderedX = x + driftX + arcX;
      let renderedY = y + driftY + arcY;
      let renderedZ = z + driftZ + arcZ;
      if (trackBurst > 0) {
        const radialLength = Math.max(0.001, Math.hypot(x, y, z));
        const planarLength = Math.max(0.001, Math.hypot(x, y));
        const burstEnergy = 1 + scrollEnergy * 0.45;
        const burstVariation =
          0.78 + (0.5 + 0.5 * Math.sin(phase * 1.73)) * 0.55;
        const burstDistance = trackBurst * burstVariation * burstEnergy;
        const swirlDirection = Math.sin(phase * 2.41) >= 0 ? 1 : -1;
        const swirlDistance =
          trackBurst *
          (0.24 + (0.5 + 0.5 * Math.cos(phase * 1.19)) * 0.34) *
          burstEnergy *
          swirlDirection;
        renderedX += (x / radialLength) * burstDistance;
        renderedY += (y / radialLength) * burstDistance;
        renderedZ += (z / radialLength) * burstDistance;
        renderedX += (-y / planarLength) * swirlDistance;
        renderedY += (x / planarLength) * swirlDistance;
        renderedZ +=
          Math.sin(phase * 1.37 + segmentProgress * Math.PI * 1.4) *
          trackBurst *
          0.36 *
          burstEnergy;
      }
      const pointerDeltaX = renderedX - pointerX;
      const pointerDeltaY = renderedY - pointerY;
      const pointerDistance = Math.hypot(pointerDeltaX, pointerDeltaY);

      if (interactionStrength > 0 && pointerDistance < interactionRadius) {
        const safeDistance = Math.max(pointerDistance, 0.001);
        const proximity = 1 - pointerDistance / interactionRadius;
        const force = proximity * proximity * interactionStrength;
        renderedX += (pointerDeltaX / safeDistance) * force * 0.72;
        renderedY += (pointerDeltaY / safeDistance) * force * 0.72;
        renderedZ += force * 0.74;
      }

      renderedPositions.current[positionOffset] = renderedX;
      renderedPositions.current[positionOffset + 1] = renderedY;
      renderedPositions.current[positionOffset + 2] = renderedZ;
      currentColors.current[positionOffset] = THREE.MathUtils.lerp(
        fromColors[positionOffset],
        toColors[positionOffset],
        colorProgress,
      );
      currentColors.current[positionOffset + 1] = THREE.MathUtils.lerp(
        fromColors[positionOffset + 1],
        toColors[positionOffset + 1],
        colorProgress,
      );
      currentColors.current[positionOffset + 2] = THREE.MathUtils.lerp(
        fromColors[positionOffset + 2],
        toColors[positionOffset + 2],
        colorProgress,
      );
    }

    points.geometry.attributes.position.needsUpdate = true;
    points.geometry.attributes.color.needsUpdate = true;

    const rawGlowWeight = THREE.MathUtils.clamp(
      1 - Math.abs(rawProgress - 1) / 0.85,
      0,
      1,
    );
    const glowWeight = rawGlowWeight * rawGlowWeight * (3 - 2 * rawGlowWeight);
    for (let glowIndex = 0; glowIndex < glowCount; glowIndex += 1) {
      const sourceIndex = glowIndex * 4;
      const sourceOffset = sourceIndex * 3;
      const glowOffset = glowIndex * 3;
      const pulse = reducedMotion
        ? 0.58
        : Math.pow(
            0.5 + 0.5 * Math.sin(elapsed * GLOW_PULSE_RADIANS_PER_SECOND),
            2.2,
          );
      const glowEnergy = 0.12 + pulse * 0.88;

      glowPositions[glowOffset] = renderedPositions.current[sourceOffset];
      glowPositions[glowOffset + 1] =
        renderedPositions.current[sourceOffset + 1];
      glowPositions[glowOffset + 2] =
        renderedPositions.current[sourceOffset + 2];
      glowColors[glowOffset] = glowEnergy;
      glowColors[glowOffset + 1] = glowEnergy;
      glowColors[glowOffset + 2] = glowEnergy;
    }
    glow.visible = glowWeight > 0.002;
    glow.material.opacity = glowWeight * (reducedMotion ? 0.42 : 0.92);
    glow.geometry.attributes.position.needsUpdate = true;
    glow.geometry.attributes.color.needsUpdate = true;

    const edgeOpacity = [0.145, 0, 0.42, 0.46];
    let edgeCursor = 0;
    const writeEdges = (edges, intensity, revealProgress = 1) => {
      const edgeCount = Math.min(MAX_EDGES, edges.length);
      for (let edgeIndex = 0; edgeIndex < edgeCount; edgeIndex += 1) {
        const edge = edges[edgeIndex];
        const rawReveal =
          edge.revealStart == null
            ? 1
            : THREE.MathUtils.clamp(
                (revealProgress - edge.revealStart) /
                  Math.max(0.001, 1 - edge.revealStart),
                0,
                1,
              );
        const revealWeight = rawReveal * rawReveal * (3 - 2 * rawReveal);
        const edgeIntensity = intensity * revealWeight;
        if (edgeIntensity <= 0.0001) continue;
        const lineOffset = edgeCursor * 6;
        const colorOffset = edgeCursor * 8;
        const sourceOffset = edge.a * 3;
        const targetOffset = edge.b * 3;
        linePositions[lineOffset] = renderedPositions.current[sourceOffset];
        linePositions[lineOffset + 1] =
          renderedPositions.current[sourceOffset + 1];
        linePositions[lineOffset + 2] =
          renderedPositions.current[sourceOffset + 2];
        linePositions[lineOffset + 3] = renderedPositions.current[targetOffset];
        linePositions[lineOffset + 4] =
          renderedPositions.current[targetOffset + 1];
        linePositions[lineOffset + 5] =
          renderedPositions.current[targetOffset + 2];
        lineColors[colorOffset] = edge.color.r;
        lineColors[colorOffset + 1] = edge.color.g;
        lineColors[colorOffset + 2] = edge.color.b;
        lineColors[colorOffset + 3] = edgeIntensity;
        lineColors[colorOffset + 4] = edge.color.r;
        lineColors[colorOffset + 5] = edge.color.g;
        lineColors[colorOffset + 6] = edge.color.b;
        lineColors[colorOffset + 7] = edgeIntensity;
        edgeCursor += 1;
      }
    };

    if (fromScene === toScene) {
      writeEdges(data.edges[fromScene], edgeOpacity[fromScene]);
    } else {
      writeEdges(
        data.edges[fromScene],
        edgeOpacity[fromScene] * (1 - segmentProgress),
      );
      writeEdges(
        data.edges[toScene],
        edgeOpacity[toScene] * segmentProgress,
        toScene === 3 ? rawSegmentProgress : 1,
      );
    }

    lines.geometry.setDrawRange(0, edgeCursor * 2);
    lines.geometry.attributes.position.needsUpdate = true;
    lines.geometry.attributes.color.needsUpdate = true;

    if (groupRef.current) {
      const pointerEnergy =
        reducedMotion || coarsePointer ? 0 : pointerVelocity.current;
      const trackOrbitY = trackArrival * 0.62 + trackBurst * 0.18;
      const trackOrbitX = trackBurst * -0.16;
      const targetRotationY = reducedMotion
        ? 0
        : heroInfluence *
          (state.pointer.x * 0.5 * (1.15 + pointerEnergy * 0.8) +
            0.028 +
            trackOrbitY);
      const targetRotationX = reducedMotion
        ? 0
        : heroInfluence *
          (-state.pointer.y * 0.5 * (0.85 + pointerEnergy * 0.6) + trackOrbitX);
      const targetRotationZ = reducedMotion
        ? 0
        : heroInfluence * trackBurst * 0.08;
      const heroPositionX = isFPlusCompact ? 0 : 1.7;
      const targetPositionX = heroPositionX * heroInfluence;
      const targetPositionY = reducedMotion
        ? 0
        : heroInfluence * Math.sin(elapsed * 0.8) * 0.07;
      const heroScale = isFPlusCompact ? 0.55 : 1;
      const transitionScale = reducedMotion
        ? 1
        : 1 + trackBurst * (0.1 + scrollEnergy * 0.05);
      const settledScale = isMobile ? 0.46 : 0.54;
      const targetScale = THREE.MathUtils.lerp(
        settledScale,
        heroScale * transitionScale,
        heroInfluence,
      );

      if (reducedMotion) {
        groupRef.current.rotation.set(0, 0, 0);
        groupRef.current.position.set(targetPositionX, 0, 0);
        groupRef.current.scale.setScalar(targetScale);
      } else {
        groupRef.current.rotation.y = THREE.MathUtils.damp(
          groupRef.current.rotation.y,
          targetRotationY,
          3.08,
          delta,
        );
        groupRef.current.rotation.x = THREE.MathUtils.damp(
          groupRef.current.rotation.x,
          targetRotationX,
          3.08,
          delta,
        );
        groupRef.current.rotation.z = THREE.MathUtils.damp(
          groupRef.current.rotation.z,
          targetRotationZ,
          3.08,
          delta,
        );
        groupRef.current.position.x = THREE.MathUtils.damp(
          groupRef.current.position.x,
          targetPositionX,
          3.7,
          delta,
        );
        groupRef.current.position.y = THREE.MathUtils.damp(
          groupRef.current.position.y,
          targetPositionY,
          3.7,
          delta,
        );
        const nextScale = THREE.MathUtils.damp(
          groupRef.current.scale.x,
          targetScale,
          3.7,
          delta,
        );
        groupRef.current.scale.setScalar(nextScale);
      }
    }
  });

  return (
    <group ref={groupRef}>
      <lineSegments ref={lineRef} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[linePositions, 3]}
          />
          <bufferAttribute attach="attributes-color" args={[lineColors, 4]} />
        </bufferGeometry>
        <lineBasicMaterial
          transparent
          opacity={1}
          vertexColors
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </lineSegments>
      <points ref={pointsRef} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[renderedPositions.current, 3]}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[currentColors.current, 3]}
          />
        </bufferGeometry>
        <pointsMaterial
          size={6}
          sizeAttenuation={false}
          map={pointTexture}
          vertexColors
          transparent
          opacity={1}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      <points ref={glowRef} frustumCulled={false} renderOrder={2}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[glowPositions, 3]}
          />
          <bufferAttribute attach="attributes-color" args={[glowColors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={25}
          sizeAttenuation={false}
          map={glowTexture}
          vertexColors
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </points>
    </group>
  );
}

export default function NodeField({
  scrollMotionRef,
  isMobile,
  reducedMotion,
  onUnavailable,
}) {
  return (
    <Canvas
      className="node-field__canvas"
      camera={{ position: [0, 0, 5.9], fov: 42, near: 0.1, far: 100 }}
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
      onCreated={({ gl }) => {
        gl.setClearColor(0x000000, 0);
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 1.15;
        gl.outputColorSpace = THREE.SRGBColorSpace;
        gl.domElement.addEventListener("webglcontextlost", onUnavailable, {
          once: true,
        });
      }}
    >
      <CosmicBackdrop
        scrollMotionRef={scrollMotionRef}
        reducedMotion={reducedMotion}
      />
      <FPlusStarField
        scrollMotionRef={scrollMotionRef}
        reducedMotion={reducedMotion}
      />
      <Field
        key={isMobile ? "mobile" : "desktop"}
        scrollMotionRef={scrollMotionRef}
        isMobile={isMobile}
        reducedMotion={reducedMotion}
      />
    </Canvas>
  );
}
