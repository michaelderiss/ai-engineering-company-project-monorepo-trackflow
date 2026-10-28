"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main style={{ padding: "2rem" }}><h1>This page is temporarily unavailable</h1><p>Please try again or return to the homepage.</p><button type="button" onClick={reset}>Try again</button> <a href="/">Homepage</a></main>;
}