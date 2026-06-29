#!/usr/bin/env python3
"""Rename downloaded PDFs to use the official smartedu title (from metadata).

Default: rename files in `~/Downloads/textbooks/{学科}/{年级}_{册次}.pdf`
to `{title}.pdf` using the title field from targets.json.

Usage:
  python3 rename_to_official_titles.py                  # use default paths
  python3 rename_to_official_titles.py /path/to/targets.json /output/dir
"""
import json
import os
import sys


def rename(targets_file, output_dir):
    if not os.path.exists(targets_file):
        sys.exit(f"❌ Targets file not found: {targets_file}")
    with open(targets_file) as f:
        targets = json.load(f)

    renamed = 0
    skipped = 0
    for t in targets:
        subject = t["subject"]
        grade = t["grade"]
        sem = t["semester"]
        title = t["title"]
        old = os.path.join(output_dir, subject, f"{grade}_{sem}.pdf")
        new = os.path.join(output_dir, subject, f"{title}.pdf")
        if not os.path.exists(old):
            print(f"  ⏭️  {subject} {grade} {sem}: source missing")
            skipped += 1
            continue
        if os.path.exists(new) and os.path.getsize(new) == os.path.getsize(old):
            print(f"  = {subject} {grade} {sem}: already named correctly")
            skipped += 1
            continue
        os.rename(old, new)
        print(f"  ✓ {os.path.basename(old)}  →  {os.path.basename(new)}")
        renamed += 1

    print(f"\nRenamed: {renamed}   Skipped: {skipped}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = sys.argv[1] if len(sys.argv) > 1 else os.path.join(script_dir, "targets.json")
    output = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Downloads/textbooks")
    rename(targets, output)