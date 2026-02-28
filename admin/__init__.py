"""
ARKAINBRAIN — Agent Control Plane (ACP) Admin

Flask blueprint: /admin/*
6 pages: Dashboard, Profiles, Flags, Agents, Workflows, Audit
"""

from flask import Blueprint

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

from admin import routes  # noqa: E402, F401
