"""
Compatibility re-export module.

Tests and legacy imports reference `backend.routers.field_mapping_templates`, while the
active implementation lives under `backend.domains.data_platform.routers.field_mapping_templates`.
Re-export the real module object so monkeypatching works as expected.
"""

from __future__ import annotations

import sys

from backend.domains.data_platform.routers import field_mapping_templates as _impl

# Make this module a transparent alias of the real implementation module.
# This ensures monkeypatching `backend.routers.field_mapping_templates` also
# affects the active router code that lives under the domains package.
sys.modules[__name__] = _impl

