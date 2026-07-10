# JEE Mock Test Backend API

This repository serves as a static API backend for the **All JEE Mock Test** Flutter application. It hosts mock test papers and their associated resources (images, manifests) on GitHub Pages, ensuring highly efficient CDN delivery and reducing the application's bundle size.

## Repository Base URL

Once published to GitHub Pages, the backend is available at:
`https://ni18-in.github.io/backend-jee-mock-test/`

## API Endpoints

### 1. Get Manifest
* **URL**: `/manifest.json`
* **Method**: `GET`
* **Description**: Fetches the root list containing all available papers, metadata (year, id, title), status flags, and paths.

### 2. Get Paper Questions
* **URL**: `/{filename}` (e.g. `/2025_paper_1/2025_paper_1.json`)
* **Method**: `GET`
* **Description**: Fetches the complete question structure, duration, and metadata for a specific paper.

### 3. Get Question Images
* **URL**: `/{paper_folder}/img/{image_name}` (e.g. `/2023_paper_1/img/chem_q10.png`)
* **Method**: `GET`
* **Description**: Fetches standard images attached to questions.

---

## Adding New Mock Papers

To add a new paper to the API, follow these three steps:

### 1. Prepare Question Paper JSON & Images
Create a directory structure under the root matching your paper:
```
backend-jee-mock-test/
├── my_new_paper/
│   ├── my_new_paper.json       # Main paper JSON file
│   └── img/
│       ├── q1.png              # Question images (if any)
│       └── q2.png
```

### 2. Register in `manifest.json`
Open the root `manifest.json` file and append your paper configuration to the `papers` list:
```json
{
  "id": "my_new_paper_id",
  "title": "JEE Main 2026 - Mock 1",
  "year": 2026,
  "filename": "my_new_paper/my_new_paper.json",
  "description": "Mock test paper based on 2026 guidelines."
}
```

### 3. Commit and Push to GitHub
Deploy the updates to GitHub Pages by pushing to the main branch:
```bash
git add .
git commit -m "Add JEE Main 2026 Mock 1"
git push origin main
```
The dashboard at `https://ni18-in.github.io/backend-jee-mock-test/` will update automatically!

---

## Technical Details

* **Hosting**: GitHub Pages
* **Frontend Dashboard**: A custom HTML/CSS page at `/index.html` fetches the manifest dynamically and renders all endpoints and papers in a premium dark mode dashboard.
* **CORS**: GitHub Pages supports cross-origin resource sharing (CORS) out of the box, allowing the Flutter app to fetch JSON papers from anywhere.
