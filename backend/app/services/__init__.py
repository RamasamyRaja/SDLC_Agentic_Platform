"""
Service layer: business logic for repositories, tasks, and task artifacts.

Route handlers (app/api/*) call into these functions rather than talking to
SQLAlchemy models directly, so ownership checks, status-transition rules,
and other domain logic live in one place.
"""
