/**
 * Shared animation timing constants.  Keep these in sync with the corresponding
 * Tailwind keyframes in tailwind.config.cjs:
 *   - pop: 180ms ease-out
 *   - pop-out: 150ms ease-out
 */

/** pop-out animation duration (150ms) + 50ms safety margin.
 *  Bump this when the pop-out keyframe duration changes. */
export const POP_OUT_FALLBACK_MS = 200
