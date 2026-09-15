#!/usr/bin/env python3
"""
Runs the ENTIRE reproducible pipeline in the correct order, from raw
data to every generated report. This is the single command a fresh
evaluator needs (besides running the test suite and starting the
dashboard separately - see README.md).

    python scripts/run_all.py
"""
import subprocess
import sys
from pathlib import Path

STEPS = [
    ("Cleaning pipeline (raw -> Parquet)", "scripts/run_pipeline.py"),
    ("Relationship quality report", "scripts/generate_relationship_quality.py"),
    ("Analytics validation + join coverage report", "scripts/generate_analytics_reports.py"),
    ("Data quality evidence report", "scripts/generate_data_quality_evidence.py"),
    ("Data dictionary", "scripts/generate_data_dictionary.py"),
]


def main():
    root = Path(__file__).resolve().parent.parent
    for label, script in STEPS:
        print(f"\n{'='*70}\n{label}\n{'='*70}")
        result = subprocess.run([sys.executable, str(root / script)], cwd=root)
        if result.returncode != 0:
            print(f"\nFAILED at step: {label} ({script}) - stopping.")
            sys.exit(result.returncode)
    print("\nAll pipeline steps completed successfully.")


if __name__ == "__main__":
    main()
