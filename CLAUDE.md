# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Spendly** — a Flask-based expense tracker web app. Tagline: "Track every rupee. Own your finances." Targets Indian users (currency: ₹). This is a learning/assignment project with a step-by-step build-out progression.

## Commands

```bash
# Run dev server (port 5001, debug mode)
python app.py

# Run tests
pytest

# Activate virtual environment (Windows)
myvenv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates, SQLite database, and vanilla CSS/JS — no build step required.

### Layers

- **Routes** — defined in `app.py`. Implemented: `/`, `/login`, `/register`, `/terms`, `/privacy`. Stubbed for future implementation: `/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`.
- **Database** — `database/db.py` (currently a stub). Will use SQLite. Should implement `get_db()`, `init_db()`, and `seed_db()`.
- **Templates** — Jinja2 in `templates/`. `base.html` provides the shared navbar and footer layout; all pages extend it.
- **Static assets** — `static/css/style.css` (679 lines, all styles) and `static/js/main.js` (placeholder).

### Design system (in `style.css`)

- Colors: green accent `#1a472a`, orange accent `#c17f24`, danger red `#c0392b`
- Fonts: DM Serif Display (headings), DM Sans (body)
- Max width: 1200px
- Border radius tokens: sm 6px, md 12px, lg 20px

## Implementation Roadmap

The project is intentionally built in numbered steps (inline comments in `app.py` and `database/db.py` mark each):

1. ✅ Landing page
2. ✅ Register/Login forms + legal pages
3. Logout route
4. Profile page
5–6. Expense dashboard
7. Add expense (`POST /expenses/add`)
8. Edit expense (`POST /expenses/<id>/edit`)
9. Delete expense (`POST /expenses/<id>/delete`)
