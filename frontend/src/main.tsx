import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/manrope";
import "./style.css";
import App from "./App";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="app-loading">
        <h1>Let’s reconnect.</h1>
        <p>The workspace could not render. Reload to try again.</p>
        <button className="primary" onClick={() => location.reload()}>
          Reload workspace
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
