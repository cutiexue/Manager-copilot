import { Component, type ErrorInfo, type ReactNode } from 'react';

// Without a boundary, one render error (for example an unexpected response shape) blanks the whole
// app. This keeps the page and offers a reload instead.
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page error', error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page-error" role="alert">
        <h1>Page error</h1>
        <button
          className="btn btn-primary"
          onClick={() => {
            window.location.hash = '#/';
            window.location.reload();
          }}
        >
          Reload
        </button>
      </main>
    );
  }
}
