"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main><h1>This page could not be loaded</h1><p>Please try again or return to Operations Home.</p><div className="actions"><button type="button" onClick={reset}>Try again</button><a href="/" className="text-link">Operations Home</a></div></main>;
}