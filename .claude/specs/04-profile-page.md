# Spec: Profile Page

## Overview
This feature turns the `/profile` stub into a fully rendered, login-protected page that shows the authenticated user's account information (name, email, member since) alongside a quick summary of their expense activity (total expenses recorded and total amount spent). It is the first route that requires authentication to access, establishing the `login_required` guard pattern that all subsequent expense routes will reuse.

## Depends on
- Step 01 — Database Setup (`users` and `expenses` tables must exist)
- Step 02 — Registration (a user record must exist)
- Step 03 — Login and Logout (`session["user_id"]` must be set on login; `get_user_by_email` pattern established)

## Routes
- `GET /profile` — render the authenticated user's profile page — logged-in only (redirect to `/login` if no session)

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email`, `created_at`) and `expenses` table provide all needed data.

## Templates
- **Create:** `templates/profile.html` — displays user name, email, member-since date, total number of expenses, and total amount spent (₹)
- **Modify:** `templates/base.html` — add a "Profile" link in the navbar that is only visible when `session.user_id` is set

## Files to change
- `app.py` — replace the `/profile` stub with a real handler: check session, fetch user and expense summary, render `profile.html`
- `database/db.py` — add `get_user_by_id(user_id)` helper that returns a user row or `None`
- `templates/base.html` — show "Profile" nav link for logged-in users

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use f-strings in SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for()` for every internal link — never hardcode paths
- Session guard: if `session.get("user_id")` is falsy, redirect to `url_for("login")` with a flash message "Please log in to view your profile."
- `get_user_by_id` belongs in `database/db.py`, not inline in the route
- Expense summary query must use a parameterised `WHERE user_id = ?` — never expose another user's data
- Format `created_at` as a human-readable date (e.g. "April 1, 2026") in the template using Jinja2's `strftime` or a passed Python date object
- Display monetary totals in ₹ with two decimal places (e.g. ₹3,300.00)

## Definition of done
- [ ] Visiting `GET /profile` while logged out redirects to `/login` with a flash message
- [ ] Visiting `GET /profile` while logged in renders the profile page (no raw stub string)
- [ ] The profile page displays the logged-in user's name
- [ ] The profile page displays the logged-in user's email
- [ ] The profile page displays the member-since date in a readable format
- [ ] The profile page displays the total number of expenses for that user
- [ ] The profile page displays the total amount spent (₹) for that user
- [ ] A "Profile" link appears in the navbar only when the user is logged in
- [ ] Clicking the navbar "Profile" link navigates to `/profile`
- [ ] No other user's data is accessible (verified by checking session isolation)
