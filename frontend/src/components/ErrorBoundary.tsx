import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /**
   * What to render in place of the crashed subtree. Defaults to the diagnostic
   * panel below.
   *
   * Pass `null` for decorative chrome. A progress toast that throws should
   * vanish, not replace itself with a stack trace across the corner of a
   * dashboard that is otherwise working perfectly.
   */
  fallback?: ReactNode;
  /** Names the boundary in the console line, so the log says which one caught. */
  label?: string;
}

interface State {
  error: Error | null;
  info: ErrorInfo | null;
}

/**
 * Catches render-time errors so a crash costs one subtree instead of the page.
 *
 * Without a boundary React treats a throw during render as unrecoverable and
 * unmounts the whole tree from the root — the screen goes white and the console
 * holds the only evidence. That is not theoretical here: a hook called after an
 * early return in the scan progress toast, a component that draws a bar in the
 * corner, blanked the entire dashboard twice (fixed in RunProgressToast; this
 * boundary is what keeps the next one from doing the same).
 *
 * Boundaries do NOT reset themselves. Once caught, this stays in the error
 * state until it is remounted, which is why the route-level usage in Layout
 * keys it by pathname: navigating away is the user's natural recovery.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ info });
    // Also log to browser console for power users
    // eslint-disable-next-line no-console
    console.error(`[ErrorBoundary${this.props.label ? ` ${this.props.label}` : ""}]`, error, info);
  }

  render() {
    const { error, info } = this.state;
    if (error) {
      // `undefined` means "not specified" and gets the panel; an explicit
      // `null` means "show nothing" and must be honoured.
      if (this.props.fallback !== undefined) return this.props.fallback;
      return (
        <div className="p-6 max-w-3xl mx-auto">
          <h2 className="text-lg font-semibold text-red-600 mb-2">Errore di rendering</h2>
          <div className="text-sm font-mono bg-red-50 dark:bg-red-950/30 p-3 rounded border border-red-200 dark:border-red-900 mb-3">
            {error.name}: {error.message}
          </div>
          {error.stack && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground">Stack trace</summary>
              <pre className="mt-2 p-3 bg-muted/50 rounded overflow-x-auto whitespace-pre-wrap">
                {error.stack}
              </pre>
            </details>
          )}
          {info?.componentStack && (
            <details className="text-xs mt-2">
              <summary className="cursor-pointer text-muted-foreground">Component stack</summary>
              <pre className="mt-2 p-3 bg-muted/50 rounded overflow-x-auto whitespace-pre-wrap">
                {info.componentStack}
              </pre>
            </details>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}
