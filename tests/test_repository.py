"""Repository: the single `WHERE user_id = :subject` chokepoint.

Written RED before repository.py was implemented (mandatory-TDD surface:
multi-user data isolation is security-adjacent).
"""

from datetime import datetime, timedelta

import pytest

from fitness_mcp.repository import POISONED_MEAL_NOTE, Database


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(str(tmp_path / "test.db"))
    database.init_db()
    return database


def test_connections_use_wal_mode(db):
    # WAL lets the eval process read the audit log while the server writes,
    # instead of flaking with 'database is locked'.
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_init_db_is_idempotent(db):
    profile_before = db.get_profile("user_001")
    meals_before = db.get_progress("user_001", "30d")["recent_meals"]
    db.init_db()  # second run must not error or duplicate seeds
    assert db.get_profile("user_001") == profile_before
    assert db.get_progress("user_001", "30d")["recent_meals"] == meals_before


def test_seeded_synthetic_users_have_distinct_profiles(db):
    p1 = db.get_profile("user_001")
    p2 = db.get_profile("user_002")
    assert p1["height_cm"] > 0
    assert p1 != p2


def test_seed_includes_poisoned_meal_for_user_001(db):
    meals = db.get_progress("user_001", "7d")["recent_meals"]
    assert any(m["description"] == POISONED_MEAL_NOTE for m in meals)


def test_get_profile_returns_latest_weight_from_history(db):
    db.log_weight("user_001", 70.5)
    assert db.get_profile("user_001")["weight_kg"] == 70.5


def test_get_profile_unknown_subject_raises(db):
    with pytest.raises(LookupError):
        db.get_profile("user_999")


def test_writes_are_scoped_to_the_writing_subject(db):
    other_meals_before = db.get_progress("user_002", "7d")["recent_meals"]
    other_weight_before = db.get_profile("user_002")["weight_kg"]

    db.log_meal("user_001", "isolation-check meal", calories=100)
    db.log_weight("user_001", 68.0)
    db.log_workout("user_001", "run", 30)

    assert db.get_progress("user_002", "7d")["recent_meals"] == other_meals_before
    assert db.get_profile("user_002")["weight_kg"] == other_weight_before


def test_log_meal_optional_fields_default(db):
    db.log_meal("user_001", "just a description")  # no calories, no timestamp
    meals = db.get_progress("user_001", "1d")["recent_meals"]
    match = [m for m in meals if m["description"] == "just a description"]
    assert match and match[0]["calories"] is None


# The trend/aggregation tests use an unseeded subject so the arithmetic is
# isolated from user_001's seed rows (which land inside the same windows).


def test_progress_weight_trend_computed_from_history(db):
    now = datetime.now()
    db.log_weight("user_042", 80.0, at=now - timedelta(days=6))
    db.log_weight("user_042", 78.5, at=now)
    trend = db.get_progress("user_042", "7d")["weight"]
    assert trend["start_kg"] == 80.0
    assert trend["end_kg"] == 78.5
    assert trend["delta_kg"] == pytest.approx(-1.5)


def test_progress_counts_workouts_and_sums_calories(db):
    db.log_workout("user_042", "run", 30)
    db.log_workout("user_042", "lift", 45)
    db.log_meal("user_042", "eggs", calories=150)
    db.log_meal("user_042", "unknown calories meal")  # None must not break the sum
    progress = db.get_progress("user_042", "1d")
    assert progress["workouts"]["count"] == 2
    assert progress["workouts"]["total_minutes"] == 75
    assert progress["calories"]["total"] == 150


def test_progress_invalid_period_raises(db):
    with pytest.raises(ValueError, match="period"):
        db.get_progress("user_001", "next tuesday")


@pytest.mark.parametrize("period", ["366d", "9000000d", "99999999999999999999d"])
def test_progress_period_beyond_one_year_rejected_cleanly(db, period):
    # Must be a clean ValueError (client-actionable), never an OverflowError.
    with pytest.raises(ValueError, match="past year"):
        db.get_progress("user_001", period)


def test_progress_period_zero_rejected(db):
    with pytest.raises(ValueError, match="period"):
        db.get_progress("user_001", "0d")


def test_progress_period_boundary_365d_accepted(db):
    assert db.get_progress("user_001", "365d")["period_days"] == 365


def test_progress_for_subject_with_no_rows_is_zero_shaped(db):
    progress = db.get_progress("user_042", "7d")  # no data, must not leak or crash
    assert progress["weight"] is None
    assert progress["workouts"]["count"] == 0
    assert progress["recent_meals"] == []
