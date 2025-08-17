import os

PREFIX_FOR_NAME = os.environ.get("PREFIX_FOR_NAME", "ws")
WORKSPACE_SECRET_NAME = os.environ.get("WORKSPACE_SECRET_NAME", "workspace")
HARBOR_URL = os.environ.get("HARBOR_URL", "")
HARBOR_ADMIN_USERNAME = os.environ.get("HARBOR_ADMIN_USERNAME", "")
HARBOR_ADMIN_PASSWORD = os.environ.get("HARBOR_ADMIN_PASSWORD", "")
# set UI_MODE to "ui" to activate UI
UI_MODE = os.environ.get("UI_MODE", "no")
# set FRONTEND_URL to "http://localhost:5173" to use dev server
FRONTEND_URL = os.environ.get("FRONTEND_URL", "/ui")
