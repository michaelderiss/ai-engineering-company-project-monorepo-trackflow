"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const pageOptions = [
  {
    value: "/milestone-2-output",
    label: "Milestone 2 Output",
    description: "View generated warehouse, carrier, and delivery output from the testing-interface dataset.",
  },
  {
    value: "http://localhost:3001",
    label: "Talent Pipeline Tracker",
    description: "Open the separate tracker app (run uis/talent-pipeline-tracker locally first).",
  },
];

export default function Page() {
  const [selectedPage, setSelectedPage] = useState(pageOptions[0].value);
  const router = useRouter();

  const selectedOption = pageOptions.find((option) => option.value === selectedPage);

  const handleOpenPage = () => {
    if (selectedPage.startsWith("http")) {
      window.open(selectedPage, "_blank", "noopener,noreferrer");
      return;
    }

    router.push(selectedPage);
  };

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">TrackFlow Backoffice</p>
        <h1>Operations Home</h1>
        <p>
          Internal entry point for TrackFlow tools. Use the launcher below to open the operational view you want to
          run in this session.
        </p>
      </header>

      <section className="panel">
        <h2>Page Launcher</h2>
        <p className="lead">
          Select a page and open it. Milestone 2 Output opens inside this backoffice app. Talent Pipeline Tracker opens
          in a new browser tab.
        </p>

        <div className="launcher-grid">
          <label className="launcher-label" htmlFor="page-selector">
            Choose a page
          </label>
          <select
            id="page-selector"
            className="launcher-select"
            value={selectedPage}
            onChange={(event) => setSelectedPage(event.target.value)}
          >
            {pageOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <p className="launcher-description">{selectedOption?.description}</p>

          <button type="button" className="open-btn" onClick={handleOpenPage}>
            Open Selected Page
          </button>
        </div>
      </section>

      <section className="panel">
        <h2>Available Routes</h2>
        <ul>
          <li>Milestone 2 Output: /milestone-2-output</li>
          <li>Talent Pipeline Tracker: http://localhost:3001</li>
        </ul>
      </section>
    </main>
  );
}
