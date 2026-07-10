"""Register a prepared paper folder in manifest.json and validate everything.

The paper folder must already exist in the backend repo root and contain
<folder>/<folder>.json (plus <folder>/img/ if any question has images).

Usage:
    python tools/add_paper.py <paper_folder> --id ID --title "TITLE" \
        --year YYYY [--description "..."] [--version N]

Behavior:
    - Adds (or updates, if --id already exists) the manifest entry.
    - Runs validate_papers.py over the whole backend.
    - If validation fails, the manifest change is rolled back and the
      script exits non-zero, so a half-registered paper can never linger.
"""

import argparse
import json
import os
import subprocess
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BACKEND_DIR, "manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="Paper folder name inside the backend repo")
    parser.add_argument("--id", required=True, help="Unique paper id, e.g. 2026_mains_jan_24_s1")
    parser.add_argument("--title", required=True, help='Display title, e.g. "JEE Mains 2026 - 24 Jan Shift 1"')
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--description", default=None)
    parser.add_argument("--version", type=int, default=1)
    args = parser.parse_args()

    folder = args.folder.strip("/\\")
    paper_json = os.path.join(BACKEND_DIR, folder, f"{folder}.json")
    if not os.path.exists(paper_json):
        sys.exit(f"Paper JSON not found: {paper_json}\n"
                 f"Expected layout: {folder}/{folder}.json inside the backend repo.")

    with open(MANIFEST_PATH, encoding="utf-8") as f:
        original = f.read()
    manifest = json.loads(original)
    papers = manifest.setdefault("papers", [])

    entry = {
        "id": args.id,
        "title": args.title,
        "year": args.year,
        "filename": f"{folder}/{folder}.json",
        "description": args.description or f"{args.title}.",
        "version": args.version,
    }

    existing = next((p for p in papers if p.get("id") == args.id), None)
    if existing:
        print(f"Paper id '{args.id}' already in manifest — updating entry "
              f"(old version {existing.get('version', 1)} -> {args.version}).")
        existing.update(entry)
    else:
        # Newest papers first, matching the manifest's rough ordering.
        papers.insert(0, entry)

    def write_manifest(content):
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            f.write(content)

    write_manifest(json.dumps(manifest, indent=4, ensure_ascii=False) + "\n")

    print("Running validation ...")
    result = subprocess.run(
        [sys.executable, os.path.join(BACKEND_DIR, "validate_papers.py")],
        cwd=BACKEND_DIR,
    )
    if result.returncode != 0:
        write_manifest(original)
        sys.exit("\nValidation FAILED — manifest change rolled back. "
                 "Fix the paper JSON and re-run.")

    print(f"\nDone. '{args.id}' registered in manifest.json (version {args.version}).")
    print("Next: review the answer key, then commit and push to the "
          "ni18-in upstream to deploy.")


if __name__ == "__main__":
    main()
