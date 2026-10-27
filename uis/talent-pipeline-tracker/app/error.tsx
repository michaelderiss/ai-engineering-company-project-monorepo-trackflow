"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="mx-auto max-w-4xl p-8"><h1 className="text-xl font-semibold">This page could not be loaded</h1><p className="my-4">Please try again or return to the candidate list.</p><button className="mr-4 underline" type="button" onClick={reset}>Try again</button><a className="underline" href="/">Candidate list</a></main>;
}