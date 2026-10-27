from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.incidents_analysis import (  # noqa: E402
    analyze_incidents_file,
    build_export_rows,
    format_console_report,
)


def export_results_csv(output_path: Path, rows: list[dict[str, object]]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["section", "metric", "value", "percentage"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python analyze.py <path-to-csv-file>", file=sys.stderr)
        return 1

    csv_path = Path(argv[1]).resolve()
    if not csv_path.exists() or not csv_path.is_file():
        print("CSV file not found. Check the supplied path and try again.", file=sys.stderr)
        return 1

    try:
        result = analyze_incidents_file(csv_path)
    except (OSError, UnicodeError, ValueError, csv.Error):
        print("Could not analyze the CSV. Check file access, UTF-8 encoding, and required columns, then try again.", file=sys.stderr)
        return 1

    report = format_console_report(result, source_file=csv_path.name)
    print(report)

    try:
        answer = input("Export results to CSV? [y / n]: ").strip().lower()
    except EOFError:
        print("No export response supplied; export skipped.", file=sys.stderr)
        return 0
    except KeyboardInterrupt:
        print("Export cancelled.", file=sys.stderr)
        return 130
    if answer == "y":
        output_path = Path.cwd() / "results.csv"
        export_rows = build_export_rows(result)
        try:
            export_results_csv(output_path, export_rows)
        except (OSError, csv.Error):
            print("Could not save results.csv. Check directory permissions or choose a writable working directory and try again.", file=sys.stderr)
            return 1
        print("Results exported to results.csv")
    else:
        print("Export skipped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
