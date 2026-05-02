import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
  info: ErrorInfo | null;
}

/**
 * Catches render-time errors so the user sees a stack trace instead of a blank page.
 * Used at the route level for diagnostic visibility.
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
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    const { error, info } = this.state;
    if (error) {
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
