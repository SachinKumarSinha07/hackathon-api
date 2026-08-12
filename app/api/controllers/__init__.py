"""Controllers package initialization.

Register each new controller's router here and add it to __all__.
"""

from app.api.controllers.health_controller import router as health_router
from app.api.controllers.project_controller import router as project_router
from app.api.controllers.user_controller import router as user_router

__all__ = ["health_router", "project_router", "user_router"]
