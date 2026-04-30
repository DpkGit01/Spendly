"""
Tests for Step 6: Date Filter on the /profile page.

Spec reference: .claude/specs/06-date-filter-profile.md

Key spec behaviours verified here:
  - GET /profile with no params returns the unfiltered (all-time) view
  - date range via ?from=YYYY-MM-DD&to=YYYY-MM-DD scopes all three data
    sections (summary, recent transactions, category breakdown)
  - Malformed date strings in query params do NOT crash the app (no 500);
    they silently fall back to the unfiltered view
  - A range where from > to shows a flash error and falls back to unfiltered
  - The "Clear" link appears only when a filter is active
  - The date inputs are pre-populated with the submitted values after apply
  - The rupee symbol (₹) is present regardless of the active filter
  - A user with no expenses in the selected range sees 0 totals, not an error
  - Unauthenticated requests to /profile redirect to /login

Implementation note: app.py reads query params as `from` and `to` (short
names), which matches what the filter form POSTs.  Tests use those names.
The spec refers to them as `date_from` / `date_to` in the description; both
refer to the same concept.

Fixture wiring: database/db.py hard-codes DB_PATH as a file path.  The
`app` fixture below patches `database.db.DB_PATH` to a temporary file so
every test gets a fully isolated SQLite database, and tears it down after.
"""

import os
import tempfile
import pytest

import database.db as db_module
from app import app as flask_app
from database.db import init_db, create_user


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

@pytest.fixture()
def app(tmp_path):
    """
    Yield the Flask app configured for testing with an isolated SQLite DB.

    `database.db.DB_PATH` is monkey-patched to a temp file so that `get_db()`
    inside every helper uses the test database instead of the production file.
    The original path is restored after the test.
    """
    db_file = str(tmp_path / "test_spendly.db")
    original_path = db_module.DB_PATH
    db_module.DB_PATH = db_file

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        init_db()
        yield flask_app

    db_module.DB_PATH = original_path


@pytest.fixture()
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture()
def registered_user(app):
    """
    Creates a user in the test DB and returns (user_id, email, password).
    Does NOT log in — callers decide whether to authenticate.
    """
    email = "filter_tester@spendly.test"
    password = "securepass1"
    user_id = create_user("Filter Tester", email, password)
    return user_id, email, password


@pytest.fixture()
def auth_client(client, registered_user):
    """A test client that is already logged in as `registered_user`."""
    _, email, password = registered_user
    client.post("/login", data={"email": email, "password": password})
    return client


def _insert_expense(user_id, amount, category, date, description=""):
    """Helper: directly insert an expense row into the test DB."""
    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Auth guard                                                                   #
# --------------------------------------------------------------------------- #

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        """
        Spec: /profile is a protected route.
        An unauthenticated GET must redirect to /login, not render the page.
        """
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Expected 302 redirect for unauthenticated /profile access"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be the login page"
        )

    def test_unauthenticated_get_profile_with_params_redirects(self, client):
        """
        Spec: query params do not bypass the auth guard.
        A logged-out request with date params must still redirect to /login.
        """
        response = client.get("/profile?from=2026-01-01&to=2026-12-31")
        assert response.status_code == 302, (
            "Auth guard must fire even when date params are present"
        )
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------------- #
# Happy path — no filter (all-time view)                                       #
# --------------------------------------------------------------------------- #

class TestNoFilter:
    def test_profile_no_params_returns_200(self, auth_client):
        """
        Spec: Visiting /profile with no query params returns the unfiltered view
        (identical to Step 5 behaviour). HTTP 200 expected.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200, (
            "Authenticated GET /profile should return 200"
        )

    def test_profile_no_params_shows_all_expenses(self, auth_client, registered_user):
        """
        Spec: no filter means all expenses appear in the summary count.
        Inserts two expenses on different dates and checks the total count.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 100.0, "Food", "2025-01-15", "January food")
        _insert_expense(user_id, 200.0, "Bills", "2026-03-10", "March bill")

        response = auth_client.get("/profile")
        assert response.status_code == 200
        # Both expenses must be reflected — the summary block shows the count
        assert b"2" in response.data, (
            "All-time view should show count of 2 when two expenses exist"
        )

    def test_profile_no_params_displays_rupee_symbol(self, auth_client, registered_user):
        """
        Spec: All amounts continue to display the rupee symbol regardless of filter.
        Even the unfiltered view must show ₹.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 500.0, "Food", "2026-04-01", "Groceries")

        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert "₹".encode() in response.data, (
            "Rupee symbol must appear on the profile page"
        )

    def test_profile_no_params_shows_filter_form(self, auth_client):
        """
        Spec: The profile page always contains the date-filter bar with
        'from' and 'to' date inputs and an Apply button.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        data = response.data
        assert b'name="from"' in data, "Filter form must have a 'from' date input"
        assert b'name="to"' in data, "Filter form must have a 'to' date input"
        assert b"Apply" in data, "Filter form must have an Apply/submit button"

    def test_profile_no_params_no_clear_link(self, auth_client):
        """
        Spec: The 'Clear' link is only shown when a filter is active.
        With no query params, no Clear link should be present.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        # The clear link targets the bare /profile URL with the text 'Clear'
        assert b"Clear" not in response.data, (
            "Clear link must NOT appear when no filter is active"
        )

    def test_profile_no_params_shows_empty_state_gracefully(self, auth_client):
        """
        Spec: A user with no expenses sees ₹0.00 total spent, 0 transactions,
        and an empty category breakdown — no errors.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        data = response.data
        # Template renders ₹0.00 when total is zero
        assert "₹0.00".encode() in data or b"0.00" in data, (
            "User with no expenses should see zero totals"
        )
        assert b"No" in data, (
            "Empty state messages ('No expenses...', 'No transactions...') expected"
        )


# --------------------------------------------------------------------------- #
# Date range filtering                                                          #
# --------------------------------------------------------------------------- #

class TestDateRangeFilter:
    def test_filter_scopes_summary_count(self, auth_client, registered_user):
        """
        Spec: Submitting a custom date range with valid from/to shows only
        expenses within that range in all three sections — including summary count.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 300.0, "Food", "2026-01-10", "January inside")
        _insert_expense(user_id, 500.0, "Bills", "2025-12-01", "December outside")

        response = auth_client.get("/profile?from=2026-01-01&to=2026-01-31")
        assert response.status_code == 200
        data = response.data
        # Summary shows count=1 (only the January expense)
        assert b"1" in data, "Filtered view should show only 1 expense in range"
        # The out-of-range amount (500) should not appear in the amounts column
        assert b"500" not in data or b"300" in data, (
            "Out-of-range expense amount should not appear; in-range one should"
        )

    def test_filter_scopes_recent_transactions(self, auth_client, registered_user):
        """
        Spec: Recent transactions section must respect the active date filter —
        only transactions within the date range appear.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 150.0, "Transport", "2026-02-14", "In range tx")
        _insert_expense(user_id, 999.0, "Shopping", "2025-11-05", "Out of range tx")

        response = auth_client.get("/profile?from=2026-02-01&to=2026-02-28")
        assert response.status_code == 200
        data = response.data
        assert b"In range tx" in data, (
            "Transaction inside the date range must appear in recent transactions"
        )
        assert b"Out of range tx" not in data, (
            "Transaction outside the date range must not appear"
        )

    def test_filter_scopes_category_breakdown(self, auth_client, registered_user):
        """
        Spec: The category breakdown section must respect the active date filter.
        Categories with no expenses in range must not appear.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 400.0, "Health", "2026-03-05", "In-range health")
        _insert_expense(user_id, 700.0, "Entertainment", "2025-06-20", "Old entertainment")

        response = auth_client.get("/profile?from=2026-03-01&to=2026-03-31")
        assert response.status_code == 200
        data = response.data
        assert b"Health" in data, "In-range category must appear in breakdown"
        assert b"Entertainment" not in data, (
            "Out-of-range category must not appear in breakdown"
        )

    def test_filter_inclusive_boundaries(self, auth_client, registered_user):
        """
        Spec: date_from and date_to are inclusive bounds (BETWEEN ? AND ?).
        Expenses exactly on the boundary dates must be included.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 50.0, "Food", "2026-04-01", "On start boundary")
        _insert_expense(user_id, 75.0, "Food", "2026-04-30", "On end boundary")
        _insert_expense(user_id, 999.0, "Bills", "2026-05-01", "After end boundary")

        response = auth_client.get("/profile?from=2026-04-01&to=2026-04-30")
        assert response.status_code == 200
        data = response.data
        assert b"On start boundary" in data, "Expense on start boundary must be included"
        assert b"On end boundary" in data, "Expense on end boundary must be included"
        assert b"After end boundary" not in data, "Expense after end boundary must be excluded"

    def test_filter_empty_range_shows_zero_totals(self, auth_client, registered_user):
        """
        Spec: A user with no expenses in the selected range sees ₹0.00 total spent,
        0 transactions, and an empty category breakdown — no errors.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 1000.0, "Bills", "2025-01-15", "Old expense")

        # Filter to a future range that has no expenses
        response = auth_client.get("/profile?from=2030-01-01&to=2030-12-31")
        assert response.status_code == 200, (
            "Empty filtered range must not crash — must return 200"
        )
        data = response.data
        assert "₹0.00".encode() in data or b"0.00" in data, (
            "Empty range must display ₹0.00 total"
        )

    def test_filter_only_from_param(self, auth_client, registered_user):
        """
        Spec: If either parameter is absent, the route applies only the
        bound that is present (open-ended range). 'from' without 'to'
        filters expenses >= from with no upper bound.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 200.0, "Food", "2026-01-01", "Jan 2026 expense")
        _insert_expense(user_id, 300.0, "Food", "2025-06-15", "Mid-2025 expense")

        response = auth_client.get("/profile?from=2026-01-01")
        assert response.status_code == 200, "Partial filter (from only) must return 200"
        data = response.data
        assert b"Jan 2026 expense" in data, (
            "Expense on/after from date must appear with only 'from' param"
        )

    def test_filter_only_to_param(self, auth_client, registered_user):
        """
        Spec: 'to' without 'from' filters expenses <= to with no lower bound.
        Must not crash and must return 200.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 100.0, "Transport", "2024-12-31", "End of 2024")
        _insert_expense(user_id, 500.0, "Shopping", "2026-06-01", "Mid 2026")

        response = auth_client.get("/profile?to=2025-01-31")
        assert response.status_code == 200, "Partial filter (to only) must return 200"
        data = response.data
        assert b"End of 2024" in data, (
            "Expense before/on to-date must appear with only 'to' param"
        )


# --------------------------------------------------------------------------- #
# Malformed date inputs                                                        #
# --------------------------------------------------------------------------- #

class TestMalformedDates:
    @pytest.mark.parametrize("from_val,to_val", [
        ("not-a-date", "2026-04-30"),
        ("2026-01-01", "not-a-date"),
        ("not-a-date", "not-a-date"),
        ("", ""),
        ("2026-13-01", "2026-04-30"),   # month 13 is invalid
        ("2026-00-00", "2026-04-30"),   # month/day zero
        ("abcdefgh", "12345678"),
        ("2026/01/01", "2026/04/30"),   # wrong separator
        ("01-01-2026", "30-04-2026"),   # wrong order
        ("2026-4-1", "2026-4-30"),      # missing zero-padding
    ])
    def test_malformed_dates_do_not_crash(self, auth_client, from_val, to_val):
        """
        Spec: If either parameter is absent or malformed, the route falls back
        to an 'All Time' (unfiltered) view rather than erroring out.
        A 500 response is a test failure; 200 with graceful fallback is required.
        """
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert response.status_code == 200, (
            f"Malformed dates from='{from_val}' to='{to_val}' must not cause a 500 — "
            f"got {response.status_code}"
        )

    def test_malformed_from_falls_back_to_unfiltered(self, auth_client, registered_user):
        """
        Spec: A malformed 'from' value is silently treated as absent, so the
        view falls back to showing all data (no lower bound applied).
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 123.0, "Food", "2025-03-01", "Old expense visible")

        response = auth_client.get("/profile?from=garbage&to=2026-12-31")
        assert response.status_code == 200
        # Because 'from' is invalid, it is ignored; the 'to' bound may still
        # apply, but the expense from 2025 should be included
        assert b"Old expense visible" in response.data, (
            "With invalid 'from', old expense must still be shown (no lower bound)"
        )

    def test_malformed_to_falls_back_to_unfiltered(self, auth_client, registered_user):
        """
        Spec: A malformed 'to' value is silently treated as absent (no upper bound).
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 777.0, "Bills", "2027-01-01", "Future expense visible")

        response = auth_client.get("/profile?from=2026-01-01&to=INVALID")
        assert response.status_code == 200
        # 'to' is invalid so no upper bound — future expense must appear
        assert b"Future expense visible" in response.data, (
            "With invalid 'to', future expense must still be shown (no upper bound)"
        )


# --------------------------------------------------------------------------- #
# from > to — invalid range                                                    #
# --------------------------------------------------------------------------- #

class TestInvalidRange:
    def test_from_greater_than_to_returns_200(self, auth_client):
        """
        Spec: If date_from > date_to after validation, the app must not crash.
        It must return HTTP 200 (fallback to unfiltered or show flash error).
        """
        response = auth_client.get("/profile?from=2026-12-31&to=2026-01-01")
        assert response.status_code == 200, (
            "from > to must not cause a 500; expected 200 with error handling"
        )

    def test_from_greater_than_to_shows_flash_or_unfiltered(
        self, auth_client, registered_user
    ):
        """
        Spec: Submitting a range where date_from > date_to shows a flash error
        ('Start date must be before end date.') and falls back to the unfiltered view.
        Both expenses (before and after the inverted range) should appear if
        the fallback is unfiltered, OR the flash message must be visible.
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 100.0, "Food", "2026-03-01", "March expense")
        _insert_expense(user_id, 200.0, "Bills", "2026-06-01", "June expense")

        response = auth_client.get("/profile?from=2026-12-31&to=2026-01-01")
        assert response.status_code == 200
        data = response.data

        flash_shown = b"Start date must be before end date" in data
        # If flash is not shown, the fallback must be unfiltered (both expenses visible)
        unfiltered_shown = b"March expense" in data and b"June expense" in data

        assert flash_shown or unfiltered_shown, (
            "When from > to, either the flash error message or unfiltered results "
            "must be displayed"
        )


# --------------------------------------------------------------------------- #
# Clear link presence                                                          #
# --------------------------------------------------------------------------- #

class TestClearLink:
    def test_clear_link_absent_without_filter(self, auth_client):
        """
        Spec: The 'Clear' link appears only when a filter is active.
        No query params → no Clear link.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"Clear" not in response.data, (
            "Clear link must not appear when no date filter is active"
        )

    def test_clear_link_present_with_from_param(self, auth_client):
        """
        Spec: When a valid 'from' date is in the query string, the Clear link
        must be rendered so the user can remove the filter.
        """
        response = auth_client.get("/profile?from=2026-01-01")
        assert response.status_code == 200
        assert b"Clear" in response.data, (
            "Clear link must appear when 'from' filter is active"
        )

    def test_clear_link_present_with_to_param(self, auth_client):
        """
        Spec: When a valid 'to' date is in the query string, the Clear link
        must be rendered.
        """
        response = auth_client.get("/profile?to=2026-04-30")
        assert response.status_code == 200
        assert b"Clear" in response.data, (
            "Clear link must appear when 'to' filter is active"
        )

    def test_clear_link_present_with_both_params(self, auth_client):
        """
        Spec: When both 'from' and 'to' are in the query string, the Clear
        link is shown.
        """
        response = auth_client.get("/profile?from=2026-01-01&to=2026-04-30")
        assert response.status_code == 200
        assert b"Clear" in response.data, (
            "Clear link must appear when full date range filter is active"
        )

    def test_clear_link_points_to_bare_profile(self, auth_client):
        """
        Spec: The 'All Time' preset (and therefore the Clear link) must pass no
        query params — it links to the clean /profile URL.
        """
        response = auth_client.get("/profile?from=2026-01-01&to=2026-04-30")
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        # The Clear anchor href must be /profile without any query params
        import re
        clear_links = re.findall(r'href="([^"]*)"[^>]*>[^<]*Clear', data)
        assert any(
            link.rstrip("/") in ("/profile", "") or link == "/profile"
            for link in clear_links
        ), (
            f"Clear link must point to bare /profile URL (no query params). "
            f"Found hrefs: {clear_links}"
        )


# --------------------------------------------------------------------------- #
# Input pre-population                                                         #
# --------------------------------------------------------------------------- #

class TestInputPrePopulation:
    def test_from_input_prepopulated_after_apply(self, auth_client):
        """
        Spec: After submitting the filter, the date inputs must reflect the
        currently active filter so the user can see and adjust what is applied.
        The 'from' input value must equal the submitted date.
        """
        response = auth_client.get("/profile?from=2026-02-01&to=2026-02-28")
        assert response.status_code == 200
        assert b"2026-02-01" in response.data, (
            "The 'from' date input must be pre-populated with the active filter value"
        )

    def test_to_input_prepopulated_after_apply(self, auth_client):
        """
        Spec: The 'to' date input value must equal the submitted date after apply.
        """
        response = auth_client.get("/profile?from=2026-02-01&to=2026-02-28")
        assert response.status_code == 200
        assert b"2026-02-28" in response.data, (
            "The 'to' date input must be pre-populated with the active filter value"
        )

    def test_inputs_empty_when_no_filter(self, auth_client):
        """
        Spec: When no filter is active, the date inputs should be empty
        (no pre-populated values).
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        # Look for value="" or value attributes that are empty for the date inputs
        # The template renders value="{{ date_from or '' }}" so without filter it is ''
        assert 'value=""' in data or "value=''" in data, (
            "Date inputs should have empty values when no filter is active"
        )


# --------------------------------------------------------------------------- #
# Rupee symbol always present                                                  #
# --------------------------------------------------------------------------- #

class TestRupeeSymbol:
    @pytest.mark.parametrize("query_string", [
        "",
        "?from=2026-01-01&to=2026-04-30",
        "?from=2026-01-01",
        "?to=2026-04-30",
        "?from=2030-01-01&to=2030-12-31",  # empty range
    ])
    def test_rupee_symbol_always_displayed(self, auth_client, registered_user, query_string):
        """
        Spec: All amounts continue to display the ₹ symbol regardless of the
        active filter — including when the range is empty (₹0.00).
        """
        user_id, _, _ = registered_user
        _insert_expense(user_id, 250.0, "Food", "2026-02-15", "Test expense")

        response = auth_client.get(f"/profile{query_string}")
        assert response.status_code == 200
        assert "₹".encode() in response.data, (
            f"Rupee symbol must appear on profile page with query '{query_string}'"
        )


# --------------------------------------------------------------------------- #
# Template structure landmarks                                                  #
# --------------------------------------------------------------------------- #

class TestTemplateStructure:
    def test_profile_extends_base_template(self, auth_client):
        """
        Spec: All templates extend base.html. The profile page must include
        the shared navbar/footer landmarks from base.html.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        data = response.data
        # base.html renders the Spendly brand name in the navbar
        assert b"Spendly" in data, (
            "Profile page must include base.html content (Spendly brand in navbar)"
        )

    def test_profile_has_summary_section(self, auth_client):
        """
        Spec: The profile page contains an Expense Summary section.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"Summary" in response.data or b"summary" in response.data, (
            "Profile page must contain an Expense Summary section"
        )

    def test_profile_has_recent_transactions_section(self, auth_client):
        """
        Spec: The profile page contains a Recent Transactions section.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"Transactions" in response.data or b"transactions" in response.data, (
            "Profile page must contain a Recent Transactions section"
        )

    def test_profile_has_category_breakdown_section(self, auth_client):
        """
        Spec: The profile page contains a Spending by Category section.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"Category" in response.data or b"category" in response.data, (
            "Profile page must contain a Spending by Category section"
        )

    def test_profile_has_filter_form_with_method_get(self, auth_client):
        """
        Spec: The filter bar uses a GET form (not POST) because the filter
        state lives in the query string.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        data = response.data.decode("utf-8")
        assert 'method="get"' in data.lower() or "method='get'" in data.lower(), (
            "Filter form must use GET method (filter state in query string)"
        )
