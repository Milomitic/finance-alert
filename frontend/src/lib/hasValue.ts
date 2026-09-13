/* Estratto da `ui/no-value.tsx`: un file che esporta un componente E altro
 * rompe il Fast Refresh (`react-refresh/only-export-components`), e questa e'
 * una guardia di tipo, non un componente. */

/** True when a number is safe to display. Rejects null, undefined, NaN and
 *  Infinity — the last two arrive from divisions on absent upstream data and
 *  render as literal "NaN%" if nobody checks. */
export function hasValue(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v);
}
