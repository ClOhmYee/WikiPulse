# Clear Blue theme verification

Issue: WP-220. Branch: `feature/WP-220-clear-blue-theme`.

## Evidence boundary

These checks use the local mock data provider and intercepted account sessions, not deployed API or production data. The white UI is the default; previously saved dark preferences remain respected. Onboarding, data contracts, graph layout and navigation structure are retained.

## Checks

- ESLint and Vite production build passed.
- Data tests: 51 passed.
- Playwright: 26 passed across theme, workspace, issue-view, auth and pulse-cluster-banner specs. Covered storage/defaults, keyboard switching, onboarding isolation, mounted map identity, camera/selection/snapshot preservation, fullscreen theme inheritance, mobile search/filter persistence and modal input persistence.
- Axe WCAG 2 A/AA and 2.1 AA: 28 checks (seven surfaces × two themes × desktop/mobile), zero reported violations. Surfaces: issue list, issue report, stock directory, account, saved, selected PulseMap, login modal. No horizontal page overflow found on the six main surfaces at 1440 and 390px.
- Before the sticky-header follow-up, baseline from the pre-change HEAD, rendered with the same fonts/mock data: dark issue-list and report main regions are pixel-identical at 1440px and 390px (zero differing pixels). Header intentionally gains a theme toggle. Animated graph screenshots are for visual inspection, not a pixel-equality claim.
- Browser review: bright canvas, category fills, dark graph labels, readable report and login form, mobile navigation and theme toggle inspected. Existing runtime warning about `THREE.Clock` deprecation is unrelated to this change.

## Existing failures reproduced on the baseline

After the final palette adjustments, the four theme tests passed again. The additional three tests in `pulse-neon.spec.js` failed on both this branch and the pre-change HEAD with identical assertions: the scan/node coincidence predicate at line 66 timed out; the node-label containment assertion at line 171 failed at both 1536px and 390px. These are recorded as pre-existing failures rather than delivered validation. Baseline and current traces are retained separately under `output/clear-blue/baseline-test-results` and `output/clear-blue/test-results`.

## Local review artifacts

The run writes a screenshot gallery to `output/clear-blue/index.html` at the repository root. It includes desktop/mobile dark and white captures, plus original baseline captures. Raw evidence is in `audit.json` and `dark-comparison.json` beside it. These generated files are local review artifacts, not frontend assets or committed fixtures.

Jira status remains unchanged. This work is delivered through a develop-targeted merge request; deployment is outside this verification.

## Follow-up: full-height background and original pastel node layers

Fixed the root HTML canvas remaining dark below the 100%-height body. White mode now paints both the root and full-height workspace. Removed simplified map fills and hidden-effect overrides; SVG gradients, halos, field, title lighting, orbits and selection effects keep the original design with pastel category colors on white.

Validation: lint/build passed; all six theme tests passed, including desktop/mobile bottom-of-page backgrounds and original gradient/halo/title-layer preservation. Selected-map Axe check reported zero WCAG A/AA violations. New screenshots: `output/clear-blue/scroll-fixed.png` and `output/clear-blue/pastel-map.png`.

## Final defaults and fixed navigation

White is now the first-visit/invalid-storage/unavailable-storage default; saved dark choices remain respected. Both startup bootstrap and React initialization use that rule. The workspace header is sticky at top: 0 on desktop/mobile. Theme tests check its viewport position after scrolling to the end in both colors.
