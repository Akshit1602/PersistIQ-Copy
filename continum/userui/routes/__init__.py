from continum.userui.routes.approval import router as approval_router
from continum.userui.routes.chat import router as chat_router
from continum.userui.routes.experiments import router as experiments_router
from continum.userui.routes.modules import router as modules_router
from continum.userui.routes.suggestions import router as suggestions_router

__all__ = [
    "chat_router",
    "experiments_router",
    "approval_router",
    "modules_router",
    "suggestions_router",
]
