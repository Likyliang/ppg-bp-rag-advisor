"""Internal administration services.

The admin subsystem is intentionally separate from the patient-facing report
pipeline.  It stores operational state in a local SQLite database while the
governed YAML catalog/configuration files remain the auditable source of truth.
"""

from app.admin.db import init_admin_db

__all__ = ["init_admin_db"]
