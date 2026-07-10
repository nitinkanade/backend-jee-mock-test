# JEE Mock Test — Workspace Context

> Context file for AI coding assistants (Claude Code, Codex, Antigravity, Cursor, etc.) and for humans returning to this project. Keep this file updated when architecture or workflows change.

## What This Is

A JEE (Joint Entrance Examination, India) mock-test platform with two sibling projects in this workspace:

| Directory | What it is | Repo |
|---|---|---|
| `jee-mock-test-paper/` | **Flutter app** "All JEE Mock Test" — simulated CBT (computer-based test) exam player for JEE Mains & Advanced papers | Bitbucket: `kanade-nitin/jee-mock-test-paper` |
| `backend-jee-mock-test/` | **Static JSON backend** — question papers + images hosted on GitHub Pages, consumed by the app over HTTP | GitHub: `nitinkanade/backend-jee-mock-test` (origin), `ni18-in/backend-jee-mock-test` (upstream — this is what GitHub Pages serves) |

The workspace root itself is **not** a git repo; each subdirectory is its own repo.

## Architecture (High Level)

```
Flutter app (Android-first)
   │  HTTP GET (package: http)
   ▼
https://ni18-in.github.io/backend-jee-mock-test/
   ├── manifest.json                       ← list of all papers (id, title, year, filename, description, comingSoon)
   ├── <paper_folder>/<paper_folder>.json  ← full question paper (sections → questions)
   └── <paper_folder>/img/<image>.png      ← question diagram images
```

- **Data is remote-first with a device cache**: the app fetches `manifest.json` and paper JSONs from GitHub Pages at runtime (`ExamProvider.baseUrl` in `jee-mock-test-paper/lib/providers/exam_provider.dart`). Papers are NOT bundled as app assets. Every successful fetch is cached to a file on device via `JsonCache` (`lib/services/json_cache.dart`, uses `path_provider`): the manifest loads **cache-first** (instant home screen, background network refresh swaps in fresh data), paper JSONs load **network-first with cache fallback** (previously opened papers work offline). All cache failures are non-fatal; corrupted entries self-delete. Question images render through `QuestionImage` (`lib/widgets/question_image.dart`, backed by `cached_network_image`) and are prefetched to the on-device image cache when a paper loads, so exams work fully offline including diagrams (retention pinned to 365 days via `PaperImageCache`). Each manifest entry carries a `version` (int, default 1): bumping it in the backend evicts that paper's cached JSON and images on user devices at the next manifest refresh — **always bump `version` when correcting a published paper**.
- **User state is local**: attempt history, bookmarks, and in-progress exam sessions persist in `shared_preferences`. No accounts, no server-side state.
- Publishing a new paper = add folder + JSON + images to `backend-jee-mock-test/`, register it in `manifest.json`, push to the `main` branch of the **upstream** (`ni18-in`) repo → GitHub Pages redeploys automatically.

## Flutter App (`jee-mock-test-paper/`)

- **State management**: `provider` (single `ExamProvider` ChangeNotifier does everything: fetching, exam session, timer, scoring, persistence).
- **Structure** (`lib/`):
  - `main.dart` — entry point, Provider setup, Material 3 theme (google_fonts).
  - `models/models.dart` — all models: `PaperManifest`, `QuestionPaper`, `ExamSection`, `Question`, `Option`, `MatchingItem`, `UserResponse`, `SavedAttempt`, `BookmarkedQuestion`, `QuestionStatus` enum.
  - `providers/exam_provider.dart` — session manager: remote JSON loading, timers, question statuses, scoring, SharedPreferences persistence.
  - `screens/` — `home_screen.dart` (dashboard, history, resume banner, bookmarks tab), `instructions_screen.dart`, `exam_screen.dart` (CBT player with palette sidebar), `result_screen.dart` (scores, subject tables, solutions).
  - `widgets/math_text.dart` — `MathText` LaTeX renderer (see critical rules below).
  - `services/json_cache.dart` — best-effort file cache for backend JSON (manifest + papers).
  - `widgets/question_image.dart` — cached question/diagram image widget (disk cache via cached_network_image).
- **Key packages**: `provider`, `shared_preferences`, `http`, `flutter_math_fork`, `tex_markdown`, `google_fonts`, `url_launcher`, `path_provider`, `cached_network_image`/`flutter_cache_manager`.
- **Android config**: package `in.ni18.jeemocktest`; NDK `27.0.12077973` pinned in `android/app/build.gradle.kts`; Kotlin package keyword escaped as `` package `in`.ni18.jeemocktest `` in `MainActivity.kt`.
- **Per-project details**: see `jee-mock-test-paper/CLAUDE.md` for scoring rules, question statuses, session persistence, and LaTeX/chemMap rules.

### Build & run

```bash
cd jee-mock-test-paper
flutter pub get
flutter analyze
flutter run                      # dev
flutter build apk --release     # release APK
```

### Critical rules (do not break)

1. **LaTeX rendering**: always render question/option text through `MathText` (`lib/widgets/math_text.dart`) — it handles `$...$` / `$$...$$` and prevents RenderLine overflow crashes. Never add short/ambiguous entries (e.g. `'eg'`) to its `chemMap` — they corrupt LaTeX commands and English words. Existing `$...$` blocks are placeholder-protected before chemMap substitution; preserve that mechanism.
2. **Question palette statuses & colors**: `unvisited` (grey), `notAnswered` (red), `answered` (green), `markedForReview` (purple), `answeredAndMarkedForReview` (purple + green dot). Preserve exactly — this mimics the real NTA CBT interface.
3. **Scoring** (in `ExamProvider`):
   - Mains: +4 correct / −1 incorrect.
   - Advanced single-correct: +3 / −1.
   - Advanced multi-correct: +4 full; partial credit (= number of correct picks) only if zero wrong picks; −2 if any wrong pick.
   - Matching: +4 / −1.
   - Numerical: parsed as double, compared with ~0.01 tolerance.
4. **Session persistence**: active exam autosaves to SharedPreferences every 10 s and on navigation/answer changes; cleared on submit or discard; restored via the home-screen Resume Banner.
5. **No server-side user data** — only paper content comes over the network; everything user-specific stays in SharedPreferences.

## Backend (`backend-jee-mock-test/`)

Pure static hosting — no server code. Contents:

- `manifest.json` — registry of all papers. Each entry: `{ id, title, year, filename, description }` (optional `comingSoon: true`).
- One folder per paper: `<paper_folder>/<paper_folder>.json` + `<paper_folder>/img/*.png`.
- `index.html` — dark-mode dashboard that renders the manifest (public landing page).
- `robots.txt` + noindex meta — deliberately excluded from search engines.

Currently hosts ~8 papers: JEE Mains 2024/2025 shifts, JEE Advanced 2023/2024/2025 Paper 1, IIT JEE 2007 Paper 2.

### Adding a new paper (standard workflow)

1. Convert the source PDF/scan to app JSON. Use the **`pdf-to-json-converter` skill** at `jee-mock-test-paper/.agents/skills/pdf-to-json-converter/SKILL.md` — it documents the full QuestionPaper JSON schema (paper → sections → questions, question types `single_correct` / `multi_correct` / `numerical` / `matching`, per-question marks/negativeMarks, LaTeX conventions).
2. Create `backend-jee-mock-test/<paper_folder>/` with the JSON and an `img/` folder for any diagrams; set `hasImage`/`imageName` on questions that reference images.
3. Append an entry to `manifest.json` with `"version": 1` (bump it on any later correction to invalidate device caches).
4. Validate the questions using the Python validation script inside `backend-jee-mock-test/`:
   ```bash
   python validate_papers.py
   ```
   If any issues like missing `negativeMarks` are detected, you can auto-fix them by running:
   ```bash
   python fix_papers.py
   ```
5. Commit and push to `main` on the `ni18-in` (upstream) repo — a GitHub Action (`.github/workflows/validate.yml`) runs `validate_papers.py` on every push; a red X means broken content is live, fix immediately — GitHub Pages serves from there. The app picks it up on next launch with no app release needed.

## Paper JSON Schema (summary)

`manifest.json` → `{ "papers": [ { id, title, year, filename, description, version?, comingSoon? } ] }`

Paper JSON (full schema in the pdf-to-json-converter skill): exam title/duration + `sections[]`, each section has subsections/questions; each `Question` has `id`, `type` (`single_correct` | `multi_correct` | `numerical` | `matching`), `questionText` (LaTeX allowed), `options[]` (`{id, text, isCorrect}`), matching lists for matching type, numerical answer for numerical type, `marks`/`negativeMarks`, `hasImage`/`imageName`, and solution/explanation text.

## Conventions & Gotchas

- **Windows dev machine** (PowerShell). Flutter SDK ^3.8.1 (Dart).
- Image URLs in the app are built as `ExamProvider.baseUrl + <paper_folder>/ + img/<name>` (see `exam_screen.dart` `_resolveImageUrl` logic) — image paths in JSON are relative to the paper folder.
- Two backend remotes: push to `origin` (nitinkanade fork) for backup, but **deployment only happens from `upstream` (ni18-in) main** — keep them in sync.
- The Flutter repo has only an initial commit; commit meaningful checkpoints going forward.
- All content (questions, LaTeX, chemistry notation) must survive `MathText` rendering — test papers in the app after adding them.

## Roadmap / Open Items

- (Add ongoing tasks here as they arise so returning sessions have a to-do trail.)
