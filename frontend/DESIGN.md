---
name: WikiPulse Onboarding
description: A four-scene Living Knowledge Field that turns scattered Wikipedia changes into an explainable event-cluster story.
colors:
  slate: "#050a0f"
  slate-deep: "#020507"
  paper: "#f3f7f7"
  teal: "#86c9c4"
  gold: "#dbb057"
  brand-cyan: "#00e0d9"
  brand-blue: "#0161fd"
  brand-violet: "#9c26fb"
  brand-blue-soft: "#8eb6ff"
  muted: "#9cafb6"
  hairline: "rgb(243 247 247 / 18%)"
  node-dim: "#365d69"
  node-shadow: "#172d37"
  ambient-teal: "#0e526c"
  ambient-deep: "#0c232e"
typography:
  display:
    fontFamily: '"Noto Sans KR Variable", "Noto Sans KR", sans-serif'
    fontSize: "clamp(3.05rem, 6vw, 5.75rem)"
    fontWeight: 560
    lineHeight: 0.98
    letterSpacing: "-0.038em"
  body:
    fontFamily: '"Noto Sans KR Variable", "Noto Sans KR", sans-serif'
    fontSize: "clamp(0.92rem, 1.1vw, 1.03rem)"
    fontWeight: 420
    lineHeight: 1.8
    letterSpacing: "-0.018em"
  label:
    fontFamily: '"Barlow Condensed", sans-serif'
    fontWeight: 600
    letterSpacing: "0.12em"
rounded:
  circle: "50%"
spacing:
  mobile-gutter: "1.25rem"
  desktop-header-gutter: "2.75rem"
  desktop-copy-left: "6.7rem"
  desktop-copy-right: "3.6rem"
  scene-gap: "clamp(2rem, 6vw, 8rem)"
components:
  mobile-control:
    backgroundColor: "rgb(16 32 42 / 38%)"
    textColor: "{colors.paper}"
    rounded: "{rounded.circle}"
    height: "2.7rem"
    width: "2.7rem"
  progress-track:
    backgroundColor: "rgb(238 242 243 / 12%)"
    height: "3px"
  progress-indicator:
    backgroundColor: "{colors.gold}"
    height: "3px"
---

# Design System: WikiPulse Onboarding

The implemented post-onboarding workspace is documented separately in [docs/UI_GUIDE.md](./docs/UI_GUIDE.md), including its Operate/Read modes, visual tokens, components, responsive layouts, routes and local mock-data behavior. The onboarding design and motion instructions below remain the authority for the four-scene introduction.

## Overview

**Creative North Star: "The Living Knowledge Field"**

This surface is a four-step viewport-snapping narrative in which one fixed procedural node field performs the complete WikiPulse onboarding story. The field owns the visible screen while each wheel, trackpad, swipe, or navigation action advances to one exact composition; the smooth trip between those anchors still supplies the node system with a continuous `0..3` transition value. The interface is limited to a wordmark, scene count, four-step rail, bottom-aligned scene copy, navigation affordances, and a three-pixel progress line. It is a Persuade surface for a short evaluator presentation, not a dashboard, authenticated product view, or destination page.

The visual thesis is a near-black cosmic-slate atmosphere, paper-white copy, muted teal knowledge matter, rare gold signal accents, and a localized cyan-blue-violet brand spectrum in the scene-one identity block. The current public F+ first-screen point system is the direct visual and motion reference for the rebuilt point layers, while WikiPulse keeps its own cosmic background, navigation, and four-scene product narrative. A deep rotating star volume without trail effects, the interactive spherical document field, layered radial light, procedural cloud, vignette, and bottom veil establish depth. Choreography and identity continuity carry the explanation: a connected document sphere reveals an anomaly, the same nodes form an event cluster, and only after that cluster exists does a conceptual stock layer appear. Node positions, quantities, cluster form, and chart form are abstract explanatory compositions rather than edit records or market data.

**Key Characteristics:**

- One persistent procedural WebGL field with separate cloud, F+-referenced star-volume, semantic-point, and connection layers beneath the existing real DOM copy and controls.
- Four reversible full-screen compositions connected by smooth anchor-to-anchor interpolation with deterministic node identity.
- A lower-left English identity lockup on scene one, large bottom-aligned statements on later scenes, and minimal chrome; no cards or feature grid.
- Layered depth from radial light, procedural FBM cloud density, perspective-distributed sprite points, scroll-responsive star rotation without trails, node z-position, additive edges, vignette, bottom veil, and damped pointer-driven three-dimensional rotation.
- Explicit separation between the implemented event-cluster story and planned stock linkage.

## Colors

The palette is dark and cool, with a deliberately higher-chroma cyan-teal reserved for the upper-right ambient light while the remaining atmosphere stays restrained so that gold can identify evidence-bearing change without turning the field into a decorative light show. The frontmatter values are normative.

### Primary

- **Signal Gold:** Marks anomalous nodes, the hero `Match` terminal point, the scene-four title's terminal point, active rail ticks, focus outlines, text selection, and progress. Its rarity is part of the hierarchy.
- **Brand Cyan / Blue / Violet:** Reproduce the supplied node icon's three anchor hues. They appear in the scene-one logo, the two subtitle separators, the complete hero description, the scene-two cyan terminal point, the scene-three violet terminal point, and the favicon; they do not replace Signal Gold's semantic role. Scenes two through four reuse Brand Blue Soft for their process statements.
- **Brand Blue Soft:** Provides WCAG-safe colored body copy on Near-Black Slate; its measured contrast is `9.73:1`.

### Secondary

- **Knowledge Teal:** Represents ordinary connected knowledge matter and the preserved cluster.
- **Paper White:** Carries primary text, highlighted cluster points, and the three explicit cluster-to-chart links.

### Neutral

- **Near-Black Slate:** Owns the page background and browser theme color.
- **Deep Cosmic Black:** Supports the darkest atmosphere and selection text.
- **Muted Copy:** Separates descriptors and secondary text from the primary statement.
- **Dim Node / Shadow Node:** Recede unselected or out-of-focus nodes without removing field continuity.
- **Hairline:** Supplies only quiet dividers and fallback section boundaries.

**The Gold Means Signal Rule.** Gold is reserved for anomaly, active progress, focus, and the explicitly conceptual linkage layer; it is not a general decoration color.

## Typography

**Display and body font:** Noto Sans KR Variable, with Noto Sans KR and generic sans-serif fallbacks.

**Label font:** Barlow Condensed at the shipped 500, 600, and 700 weights.

Noto Sans KR gives the Korean narrative a stable, contemporary editorial voice. Barlow Condensed compresses English metadata, numbering, and status language into a technical but quiet instrument panel around the field.

### Hierarchy

- **Scene-one identity:** The lower-left lockup contains the supplied transparent node icon followed by a CSS `WIKIPULSE` wordmark. The supporting column—`Track. Cluster. Match.`, `Issue-tracking intelligence for matching emerging events with relevant stocks`, and `SCROLL TO TRACE`—begins directly beneath the wordmark's `W` using the same responsive icon-plus-gap offset that positions later scene titles; no parallel right-side detail column is rendered. The icon is unmodified and displayed at `clamp(4.6rem, 7vw, 6.2rem)`. The wordmark uses Noto Sans KR at `clamp(3.55rem, 5.6vw, 4.9rem)` with only `PULSE` receiving a violet-blue accent. The subtitle periods after `Track`, `Cluster`, and `Match` receive brand cyan, violet, and signal gold respectively; the complete explanation uses Brand Blue Soft, remains on one line above 720px, and returns to safe wrapping on mobile. The mobile wordmark becomes `clamp(2.1rem, 10.5vw, 3.75rem)` to keep the full lockup inside the 320px minimum viewport.
- **Display:** The frontmatter display token is used for the scene statement, capped at `13ch` on desktop. Mobile changes to `clamp(2.55rem, 11.2vw, 4.25rem)` with `1.02` line height and a `12ch` maximum.
- **Body:** Scene one keeps its supplied explanation at `clamp(0.9rem, 1.05vw, 1rem)`. All four descriptions begin with an initial capital. Scenes two through four pair each initial-capital, paper-white title with one confirmed process statement directly beneath it: `Track` — `Detect unusual activity as it emerges`, `Cluster` — `Turn related signals into emerging events`, and `Match` — `Connect events with relevant stocks`. A cyan, violet, then gold terminal point follows those titles, extending the scene-one punctuation system without recoloring the title words. All three process statements use Brand Blue Soft and a deliberate middle scale between the original body size and the scene-one subtitle: `clamp(1.15rem, 1.75vw, 1.6rem)` with `1.46` line height on desktop, then `clamp(1.05rem, 4.5vw, 1.3rem)` with the same line height on mobile.
- **Wordmark:** Barlow Condensed at `1.08rem`, weight `700`, with `0.12em` tracking.
- **Metadata:** Barlow Condensed uses compact sizes from `0.64rem` to `0.79rem`, medium-to-semibold weight, uppercase English where supplied, and tracking from `0.1em` to `0.17em`.

**The Copy Is Interface Rule.** Scene meaning must remain selectable, screen-reader-visible DOM text; it is never painted into WebGL or supplied as a raster.

## Layout

The document contains four exact `100dvh` snap anchors with a minimum width of 320px. The experience is fixed to the viewport and remains `100dvh` tall; the canvas fills that stage at layer zero. Narrative and navigation occupy layers three through five so the field remains uninterrupted while wheel, trackpad, touch, keyboard, rail, and mobile-control input moves to one neighboring anchor at a time. CSS scroll snapping also settles direct scrollbar movement onto the nearest full-screen composition.

On desktop, the topline uses the desktop header gutter. The scene rail is vertically centered on the base left axis. Scene one remains 5rem above the bottom in a lower-left identity block no wider than 40rem; only the icon-and-wordmark row uses the base gutter, while its subtitle, explanation, and scroll cue share the `W` axis. Scenes two through four begin at that wordmark's exact x/y origin: x is calculated from the base gutter plus the responsive icon width and brand gap, while y is measured from the rendered `W` line box and synchronized through `--scene-wordmark-top`. Their confirmed process statement sits directly beneath the title in the same column. Font loading, viewport resizing, and the short-height breakpoint all trigger or participate in the same origin calculation rather than relying on separate vertical estimates.

At 720px and below, all four scenes remain. Horizontal gutters become the mobile gutter; scene one sits 6.8rem above the bottom, while scenes two through four inherit the measured mobile `W` origin on both axes. The desktop scene rail and scroll cue are hidden, while visible previous/next controls appear 1.3rem above the bottom. The descriptor beside the wordmark is also hidden. The bottom progress track remains three pixels tall in every layout.

### Field counts and ownership

| Class | Desktop | Mobile | Stable indices |
|---|---:|---:|---|
| All semantic points | 350 | 350 | `0..349` |
| Event-cluster points | 150 | 150 | `0..149` |
| Anomaly points, also owned by the cluster | 38 | 38 | `0..37` |
| Non-cluster points | 200 | 200 | `150..349` |
| Scene-four price-contour points | 140 | 140 | `150..289` |
| Scene-four volume-field points | 60 | 60 | `290..349` |

Counts are deterministic outputs of the implementation: cluster ownership is `floor(count × 0.43)`, anomaly ownership is `max(8, floor(count × 0.11))`, and the price contour receives `max(12, floor(non-cluster count × 0.7))`. The semantic field remains 350 points on every device; compact viewports transform the same ownership model rather than generating a smaller one. Decorative star-volume points do not participate in semantic ownership. The star volume contains 950 points at widths of 700px and above, or 560 points below 700px.

## Elevation & Depth

The system uses no box shadows and no elevated cards. Spatial depth comes from point z-position, a perspective camera fixed at `[0, 0, 5.9]` with a 42-degree field of view and near/far planes of `0.1`/`100`, additive line blending, three radial CSS gradients, a procedural five-octave FBM cloud plane, the F+-referenced star volume, a full-frame radial vignette, and a dark bottom veil. Rendering uses antialiasing, a device pixel ratio range up to 2, ACES filmic tone mapping, and exposure `1.15`. Scene-specific saturation and brightness shifts darken the atmosphere as the narrative resolves.

Across scenes one and two, pointer movement rotates the complete three-dimensional document sphere through damped x/y targets; pointer velocity is capped at `0.85`, decays by `0.96` per frame, and amplifies the field's spatial drift. Completed scenes one and two apply no local pointer repulsion, so the sphere rotates without individual nodes fleeing the cursor; repulsion begins only as the field transitions toward scene three. The scene-one-to-two transition has no horizontal offset. Following the F+-referenced motion structure, scroll phase combines four materials instead of a uniform scale: seeded radial displacement, alternating tangential swirl, depth oscillation, and a persistent `0.62`-radian y-axis arrival orbit. A transient 10–15% group zoom and up to 45% velocity amplification add momentum at the transition midpoint, then all displacement collapses back into the scene-two sphere. The sphere retains its depth until the scene-two-to-three transition begins, where the hero influence eases out over `0.92` narrative units. The points remain narrative objects and are not hover targets or clickable controls.

**The Field Owns Depth Rule.** New surface elements must not introduce card shadows or floating panels over the narrative; depth belongs to the field and its atmospheric layers.

## Shapes

The signature semantic primitive is a soft radial sprite generated from one shared 64px canvas texture. The foreground semantic field renders white, additive, `6px` screen-space sprites with size attenuation disabled; scene two adds a separate soft-falloff `25px` white halo draw for 38 evenly interleaved nodes from the 150-node continuation set. The star volume renders the base texture as perspective-attenuated points at world size `0.06` for the farther, left-traveling subset and `0.054` for the remaining points, all at opacity `0.85`. Background stars remain clean circular sprites: there is no comet shader, duplicated afterimage draw, or head glow. Connections are thin additive line segments whose perceived weight comes from scene-specific opacity rather than unsupported platform-dependent WebGL line widths. Decorative star-volume particles must never be treated as event nodes. The field deliberately avoids literal illustrations, chart axes, data cards, or rounded containers.

The only rounded interactive shapes are the 2.7rem circular mobile previous/next controls. Desktop rail steps are transparent rectangular hit areas with a one-pixel gold tick extending from the active step. The progress indicator is a straight three-pixel band anchored to the bottom edge.

## Components

### Persistent Cosmic and Node Field

The semantic field is generated once from the fixed seed `0xc4885e62`. Four position, color, and edge states are precomputed for the same 350-point index set. Each frame reads the smooth position between the active and destination snap anchors, chooses the adjacent state pair, smoothsteps the local segment fraction, and interpolates every point's position and color directly between those states; points are never replaced and their ownership never changes. Adjacent edge sets crossfade inside one dynamic line buffer using per-vertex alpha while their white, teal, or gold RGB values remain unchanged, preventing near-zero transition edges from darkening over the cyan atmosphere. Points follow a curved three-axis transition arc and retain small three-dimensional drift. The camera remains fixed.

Behind the semantic field, a full-canvas plane renders a slowly evolving five-octave FBM cosmic cloud whose intensity follows continuous scene progress. The F+-referenced star volume uses 950 desktop or 560 compact points. Each star's depth is `5.2 - pow(random, 1.3) * 21`; its x/y spread is `3 + (5.2 - z) * 0.5`, producing the same perspective expansion toward deep layers. Colors are distributed approximately equally among gold `#dbb057`, teal `#8acbc1`, and white. All stars share the 64px radial sprite texture and opacity `0.85`; stars initialized behind the rotation center (`z < 0`) travel left at rest and use world size `0.05`, while the remaining points keep `0.045`. The base y-rotation is `0.04` radians per second on desktop or `0.02` on compact screens; signed normalized scroll velocity adds up to `0.68` or `0.48` radians per second and may reverse the rotation. Only the main star draw is rendered—no ghost copies or comet shader—so scroll speed changes motion without creating tails. Reduced-motion mode freezes the rotation.

The four implemented compositions are:

1. **Scattered changes:** all 350 points occupy an actual three-dimensional spherical document cluster with seeded radii from `0.6` to `2.3`, rendered white. Every pair closer than `0.51` world units is connected; the current seeded composition produces 953 edges at line opacity `0.145`, almost exactly half of the preceding 1,917-edge field. Desktop places the group at x `1.7` and scale `1`; below 700px it uses x `0` and scale `0.55`. Pointer position drives damped x/y rotation and pointer velocity amplifies the cluster's three-dimensional drift. Scenes one and two have no local pointer repulsion.
2. **Track:** all 350 nodes return to a rotated version of the scene-one three-dimensional sphere after the radial, tangential, and depth spread transition instead of flattening into a plane or shifting right. Pointer movement continues to rotate the whole sphere without pushing nearby nodes away. Connection edges disappear, while 38 evenly interleaved nodes from scene three's 150-node cluster set receive a pronounced soft white halo. Those selected nodes pulse in sync on the same `0.7s` cycle, making continuation legible without recoloring the base nodes. The other 112 nodes lose only their glow and retain the same cluster ownership, indices, positions, and scene-three transition; reduced-motion mode skips the spread and orbit and uses the static sphere with a steady low-opacity halo.
3. **Event cluster:** the first 43% of indices gather into one organic cluster with teal nearest-neighbor edges. The anomaly subset remains gold and intermittent nodes become paper white. Non-cluster nodes stay visible as a sparse, dim three-dimensional peripheral field around the completed cluster instead of being pushed outside the composition.
4. **Match:** the exact scene-three cluster indices remain a substantial three-dimensional cluster on the left of the scene-four composition without being rebuilt. On desktop, the complete scene-four pair owns the right two-thirds of the viewport: the cluster occupies roughly 40% of that region, a restrained bridge gap 10%, and the abstract stock field 50%. The peripheral non-cluster indices move immediately and directly into a `4.15`-world-unit gold price contour and teal volume field on the right, leaving only a small drift-safe outer margin. The two groups have comparable visual height instead of being flattened to satisfy a narrow width. Five paper-white links sample origins across the cluster-facing 40% of nodes and spread destinations from 8% to 82% of the price contour; both sets are ordered on the perpendicular axis before pairing to control crossings. Price-contour edges reveal after transition progress `0.58`, the price-node color change is independently delayed until progress `0.68` and completes at arrival, and the five bridge lines reveal after `0.78`; node movement still begins immediately, and volume-node color timing remains unchanged. On mobile, the same ownership switches to an upper cluster and lower `3.3`-world-unit chart to preserve readable scale. Its confirmed explanatory copy remains conceptual and must not imply implemented stock mapping or market performance.

**The Ownership Never Changes Rule.** Index identity is semantic. The anomaly set is a subset of the event cluster; scene four preserves that cluster; only non-cluster nodes may become the chart.

### Viewport Snap Navigation

Four `100dvh` anchors map linearly to narrative progress `0..3`. A vertical wheel or trackpad gesture accumulates to a short threshold and advances exactly one anchor; momentum events remain locked until the transition and gesture tail settle. A vertical touch gesture uses a 48px threshold and also advances one scene. Normal mode smoothly scrolls to the target and damps displayed progress with an exponential response of `2`, giving each composition a long, deliberate decelerating arrival; reduced motion jumps to the anchor and uses the target immediately. Stable point indices and adjacent-state interpolation keep every forward and reverse transition deterministic.

| Input | Implemented behavior |
|---|---|
| Wheel / trackpad | One vertical gesture advances one neighboring scene; accumulated momentum cannot skip scenes. |
| Touch | One vertical swipe past 48px advances one neighboring scene. |
| Keyboard / scrollbar | Arrow, Page, Space, Home, and End keys navigate exact anchors; direct scrollbar movement settles to the nearest anchor. |
| Scene rail | A numbered button smoothly scrolls to its exact composition. |
| Mobile controls | Visible previous/next buttons smoothly scroll to exact adjacent compositions and disable at sequence boundaries. |

Vertical wheel and touch input are deliberately captured by this single-purpose full-screen experience so intermediate document positions cannot become resting states. Horizontal gestures remain untouched. All scripted scroll commands honor reduced motion, ignore form controls, and preserve direct rail and mobile-button navigation.

### Motion Contract

- Node position, color, edge intensity, scale, ambient treatment, and bottom progress derive from the smooth anchor-to-anchor scroll position rather than separate timed scene tweens.
- All four DOM copy layers remain mounted. Adjacent layers move vertically by up to 14% of viewport height, blur by up to `8px` per scene of distance, and crossfade with a cosine falloff; no content is re-keyed during scroll.
- The active rail color changes over 240ms and its gold tick over 280ms. The first-scene scroll cue fades in over 700ms after 650ms and its arrow bobs on a 1.8-second loop.
- Scroll velocity is normalized against viewport height and frame time, attacks at response `18`, releases at `4.2`, and receives an additional `3.8` exponential decay once scroll and progress settle. This shared signed value drives star rotation speed and direction; its absolute value adds only a restrained increase in semantic drift. No trail opacity or length is computed.
- Under `prefers-reduced-motion: reduce`, scene navigation jumps directly to each snap anchor and copy and semantic nodes select the nearest static composition without spatial interpolation. Star rotation, spherical drift, pointer rotation and response, transition arcs, and CSS ambient orbit are frozen; other CSS animations and transitions collapse to 0.01ms.

### Navigation and Progress

The upper-left wordmark and upper-right nearest-scene count are persistent. Desktop uses the four-button vertical scene rail, while the first-scene-only `SCROLL TO TRACE` cue is the final row inside the lower-left identity block. Mobile replaces those affordances with labeled circular previous/next controls. The bottom progress transform moves from one quarter-step to the next during each scene transition.

### Accessibility and Fallback

- The document language is Korean and the browser theme color matches Near-Black Slate.
- Scene copy is a real heading and paragraph inside an `aria-live="polite"` region.
- Rail buttons expose descriptive labels and `aria-current="step"`; mobile controls have labels and disabled boundary states.
- Keyboard, wheel, touch, scrollbar, rail click, and mobile buttons all resolve to the same four snap anchors and shared transition-progress source.
- Focus-visible controls receive a two-pixel Signal Gold outline with a five-pixel offset.
- The decorative ambient and node layers are hidden from assistive technology.
- If WebGL/WebGL2 is unavailable, or if the WebGL context is lost, the application switches to a readable naturally scrollable four-section DOM fallback without snapping.

### Performance Architecture

The implementation uses one React Three Fiber canvas containing one procedural cloud plane and shader material, two memoized star-volume geometries split by initial depth so their point sizes can differ, one 350-point semantic geometry, and one dynamic line-segment geometry sized to crossfade two adjacent sets of up to 4,200 edges each. The background and semantic systems share one generated radial sprite texture style. Scroll motion lives in a mutable ref, so per-frame progress and velocity do not trigger React renders; only the nearest scene label changes React state. Semantic scene arrays, point colors, and line buffers are memoized typed arrays and updated in place with dynamic draw usage. There is no React component per point.

Every viewport uses antialiasing and a device pixel ratio range of 1 to 2, and requests a high-performance WebGL context. ACES filmic tone mapping runs at exposure `1.15`. The only shipping raster is `public/wikipulse-icon.png`, copied byte-for-byte from the user-supplied transparent `파비콘.png` and reused for the scene-one identity lockup and browser favicon. All remaining visuals are procedural WebGL, generated canvas textures, DOM/CSS, local font files, and Lucide vector icons.

## Do's and Don'ts

### Do

- **Do** preserve the sequence `scattered changes → anomaly signal → event cluster → planned stock linkage` and the same node identities through all four scenes.
- **Do** keep the completed event cluster present before and during the conceptual stock layer.
- **Do** keep scene-four stock language explicitly conceptual and visually downstream from cluster formation.
- **Do** keep copy in the DOM, maintain all input paths, retain the reduced-motion crossfade, and preserve the readable WebGL fallback.
- **Do** extend the field through instanced geometry and shared buffers rather than per-node React components.
- **Do** preserve the supplied `public/wikipulse-icon.png` byte-for-byte and record provenance for any future raster assets.

### Don't

- **Don't** let stock information select, recolor, or form the event cluster.
- **Don't** turn any cluster-owned index into a chart point in scene four.
- **Don't** add tickers, prices, returns, accuracy claims, or visual language that implies implemented stock mapping.
- **Don't** convert this onboarding surface into a dashboard, card stack, feature list, authentication flow, or CTA destination.
- **Don't** make nodes individually clickable or reintroduce input locks, wheel thresholds, fixed-duration scene jumps, comet shaders, or duplicated afterimage layers.
- **Don't** claim the abstract nodes, cluster, contour, or volume field are actual edit or market records.

### Verification Status

**Finish-review verdict: RECAPTURE REQUIRED.** Independent source review passed, the production build passed, and the running application returned HTTP 200. Desktop and mobile visual recapture remains the only open verification item because the browser capture backend was unavailable. The Impeccable detector returned `[]` in degraded regex mode. The supplied transparent icon is the only shipping raster and its copied SHA-256 matches the source.
