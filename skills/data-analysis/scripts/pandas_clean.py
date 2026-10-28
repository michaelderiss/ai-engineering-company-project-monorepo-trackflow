"""
Safe snippet for basic pandas cleaning. Copy and adapt for your dataset.
Run: python pandas_clean.py  (ensure pandas is installed)
"""
import sys


def main() -> int:
	try:
		import pandas as pd
	except ImportError:
		print("Pandas is required. Install pandas in your environment and try again.", file=sys.stderr)
		return 1
	try:
		data = pd.read_csv("data.csv")
	except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
		print("Could not read data.csv. Check the file, permissions, encoding, and CSV structure, then try again.", file=sys.stderr)
		return 1
	print("input_shape", data.shape)
	data = data.dropna(axis=1, how="all")
	data.columns = data.columns.str.strip().str.lower().str.replace(" ", "_")
	before = len(data)
	data = data.drop_duplicates()
	print("rows_dropped_duplicates", before - len(data))
	print("output_shape", data.shape)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
