"""Local admin console for the JEE Mock Test paper backend.

Browse, edit, validate, commit and publish question papers — all against
the working copy of this repo. Binds to 127.0.0.1 only; never expose it.

Run:
    python tools/admin/app.py          # opens http://127.0.0.1:8770

Smart behaviors:
    - Editing a question in an already-published paper auto-bumps that
      paper's manifest `version` (once per publish cycle), so user devices
      evict their cached copy. New/unpublished papers are never bumped.
    - Commit messages are auto-generated from what actually changed.
    - Publish = validate first, then push to every git remote; a failing
      validation blocks the push.
"""

import json
import os
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, abort, jsonify, request, send_from_directory

ADMIN_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(ADMIN_DIR))
MANIFEST_PATH = os.path.join(BACKEND_DIR, "manifest.json")
HOST, PORT = "127.0.0.1", 8770

app = Flask(__name__, static_folder=None)


# ---------- helpers ----------

def run(cmd, **kwargs):
    return subprocess.run(
        cmd, cwd=BACKEND_DIR, capture_output=True, text=True,
        encoding="utf-8", errors="replace", **kwargs)


def git(*args):
    return run(["git", *args])


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write("\n")


def load_manifest():
    return load_json(MANIFEST_PATH)


def manifest_entry(manifest, paper_id):
    for p in manifest.get("papers", []):
        if p.get("id") == paper_id:
            return p
    return None


def paper_path(entry):
    filename = entry.get("filename", "")
    path = os.path.normpath(os.path.join(BACKEND_DIR, filename))
    if not path.startswith(os.path.normpath(BACKEND_DIR)):
        abort(400, "Invalid paper path")
    return path


def head_manifest():
    """manifest.json as of the last commit, or None (e.g. brand-new repo)."""
    r = git("show", "HEAD:manifest.json")
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def iter_questions(paper):
    for section in paper.get("sections", []):
        for q in section.get("questions", []) or []:
            yield section, None, q
        for sub in section.get("subsections", []) or []:
            for q in sub.get("questions", []) or []:
                yield section, sub, q


def maybe_bump_version(paper_id):
    """Bump the paper's manifest version once per publish cycle.

    Only bumps when the paper exists in HEAD's manifest and the working
    version hasn't already been raised above the committed one — so multiple
    edits before one publish produce a single +1, and unpublished papers
    stay at their initial version.
    """
    head = head_manifest()
    if head is None:
        return None
    head_entry = manifest_entry(head, paper_id)
    if head_entry is None:
        return None
    manifest = load_manifest()
    entry = manifest_entry(manifest, paper_id)
    if entry is None:
        return None
    head_version = head_entry.get("version", 1)
    if entry.get("version", 1) <= head_version:
        entry["version"] = head_version + 1
        save_json(MANIFEST_PATH, manifest)
        return entry["version"]
    return None


# ---------- pages & files ----------

@app.get("/")
def index():
    return send_from_directory(ADMIN_DIR, "index.html")


@app.get("/files/<path:relpath>")
def files(relpath):
    """Serve repo files (question images) to the UI."""
    full = os.path.normpath(os.path.join(BACKEND_DIR, relpath))
    if not full.startswith(os.path.normpath(BACKEND_DIR)) or ".git" in relpath:
        abort(403)
    return send_from_directory(BACKEND_DIR, relpath)


# ---------- API: papers & questions ----------

@app.get("/api/papers")
def api_papers():
    manifest = load_manifest()
    head = head_manifest() or {"papers": []}
    out = []
    for entry in manifest.get("papers", []):
        info = dict(entry)
        info["questionCount"] = None
        info["loadError"] = None
        if entry.get("filename"):
            try:
                paper = load_json(paper_path(entry))
                info["questionCount"] = sum(1 for _ in iter_questions(paper))
            except Exception as e:
                info["loadError"] = str(e)
        head_entry = manifest_entry(head, entry.get("id"))
        info["published"] = head_entry is not None
        info["pendingBump"] = bool(
            head_entry and entry.get("version", 1) > head_entry.get("version", 1))
        out.append(info)
    return jsonify(out)


@app.get("/api/paper/<paper_id>")
def api_paper(paper_id):
    manifest = load_manifest()
    entry = manifest_entry(manifest, paper_id)
    if not entry or not entry.get("filename"):
        abort(404, "Unknown paper id")
    paper = load_json(paper_path(entry))
    folder = os.path.dirname(entry["filename"])
    return jsonify({"manifest": entry, "paper": paper, "folder": folder})


@app.put("/api/paper/<paper_id>/question/<question_id>")
def api_update_question(paper_id, question_id):
    new_q = request.get_json(force=True)
    if not isinstance(new_q, dict) or new_q.get("id") != question_id:
        abort(400, "Body must be the question object with a matching id")

    manifest = load_manifest()
    entry = manifest_entry(manifest, paper_id)
    if not entry:
        abort(404, "Unknown paper id")
    path = paper_path(entry)
    paper = load_json(path)

    for _, _, q in iter_questions(paper):
        if q.get("id") == question_id:
            q.clear()
            q.update(new_q)
            save_json(path, paper)
            bumped = maybe_bump_version(paper_id)
            return jsonify({"ok": True, "bumpedVersion": bumped})
    abort(404, "Question not found in paper")


@app.put("/api/paper/<paper_id>/meta")
def api_update_meta(paper_id):
    """Update manifest fields (title, year, description, version, comingSoon)."""
    body = request.get_json(force=True)
    manifest = load_manifest()
    entry = manifest_entry(manifest, paper_id)
    if not entry:
        abort(404, "Unknown paper id")
    for field in ("title", "year", "description", "version", "comingSoon"):
        if field in body:
            entry[field] = body[field]
    save_json(MANIFEST_PATH, manifest)
    return jsonify({"ok": True, "entry": entry})


# ---------- API: validate / git ----------

@app.post("/api/validate")
def api_validate():
    r = run([sys.executable, os.path.join(BACKEND_DIR, "validate_papers.py")])
    return jsonify({"ok": r.returncode == 0,
                    "output": (r.stdout or "") + (r.stderr or "")})


@app.get("/api/git/status")
def api_git_status():
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    status = git("status", "--porcelain").stdout.splitlines()
    remotes = [l.split()[0] for l in git("remote").stdout.splitlines() if l.strip()]
    ahead = {}
    for remote in remotes:
        r = git("rev-list", "--count", f"{remote}/{branch}..HEAD")
        ahead[remote] = int(r.stdout.strip()) if r.returncode == 0 else None
    return jsonify({"branch": branch, "changes": status,
                    "remotes": remotes, "ahead": ahead})


def auto_commit_message(status_lines):
    ids = set()
    manifest_touched = False
    for line in status_lines:
        path = line[3:].strip().strip('"')
        if path == "manifest.json":
            manifest_touched = True
        elif "/" in path.replace("\\", "/"):
            ids.add(path.replace("\\", "/").split("/")[0])
    parts = []
    if ids:
        parts.append("update " + ", ".join(sorted(ids)))
    if manifest_touched:
        parts.append("manifest")
    return "content: " + ("; ".join(parts) if parts else "update papers")


@app.post("/api/git/commit")
def api_git_commit():
    body = request.get_json(silent=True) or {}
    status_lines = git("status", "--porcelain").stdout.splitlines()
    if not status_lines:
        return jsonify({"ok": False, "output": "Nothing to commit."})
    message = (body.get("message") or "").strip() or auto_commit_message(status_lines)
    git("add", "-A")
    r = git("commit", "-m", message)
    return jsonify({"ok": r.returncode == 0, "message": message,
                    "output": r.stdout + r.stderr})


@app.post("/api/git/publish")
def api_git_publish():
    """Validate, then push the current branch to every remote."""
    v = run([sys.executable, os.path.join(BACKEND_DIR, "validate_papers.py")])
    if v.returncode != 0:
        return jsonify({"ok": False,
                        "output": "Validation failed — publish blocked.\n\n"
                                  + v.stdout + v.stderr})
    if git("status", "--porcelain").stdout.strip():
        return jsonify({"ok": False,
                        "output": "Uncommitted changes present — commit first."})
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    remotes = [l.strip() for l in git("remote").stdout.splitlines() if l.strip()]
    log, ok = [], True
    for remote in remotes:
        r = git("push", remote, branch)
        log.append(f"$ git push {remote} {branch}\n{r.stdout}{r.stderr}")
        ok = ok and r.returncode == 0
    return jsonify({"ok": ok, "output": "\n".join(log)})


if __name__ == "__main__":
    url = f"http://{HOST}:{PORT}/"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"JEE paper admin running at {url}  (local only — Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, debug=False)
