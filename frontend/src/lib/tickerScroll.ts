/* Aritmetica dello scorrimento del nastro. Pura e testabile senza motore di
 * layout — ed e' proprio per questo che era esportata dal componente */

/* A frame longer than this means the tab was backgrounded or the main thread
 * stalled — rAF simply stops delivering. Uncapped, the first frame back
 * carries the whole gap and teleports the tape. */
export const MAX_FRAME_S = 0.5;

/** Next scroll offset, wrapping at `half` (one rail width). Pure, so the
 *  wrap and the dt cap are testable without a layout engine. */
export function advanceScroll(
  current: number,
  half: number,
  pxPerSecond: number,
  dtSeconds: number,
): number {
  // Before layout `scrollWidth` is 0. Wrapping on that would pin the tape at
  // the origin forever, which reads as "the ticker is broken".
  if (!(half > 0)) return current;
  const next = current + pxPerSecond * Math.min(dtSeconds, MAX_FRAME_S);
  return next >= half ? next - half : next;
}
