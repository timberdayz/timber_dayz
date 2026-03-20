from __future__ import annotations

"""Compatibility login entry for Miaoshou platform components.

Formal runtime now prefers versioned file_path manifests, but older code paths
and compatibility tests still expect `modules.platforms.miaoshou.components.login`.
"""

from modules.platforms.miaoshou.components.miaoshou_login import (
    MiaoshouMiaoshouLogin,
)


class MiaoshouLogin(MiaoshouMiaoshouLogin):
    """Stable compatibility alias for the recorder-generated Miaoshou login component."""

    pass
