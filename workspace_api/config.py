# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import os

PREFIX_FOR_NAME = os.environ.get("PREFIX_FOR_NAME", "")
PROVIDER_ENVIRONMENT = os.environ.get("PROVIDER_ENVIRONMENT", "datalab")
DISABLE_STORAGE = os.environ.get("DISABLE_STORAGE", "false")
DISABLE_DATALAB = os.environ.get("DISABLE_DATALAB", "false")
USE_VCLUSTER = os.environ.get("USE_VCLUSTER", "false")
SESSION_MODE = os.environ.get("SESSION_MODE", "on")
MAX_SESSIONS = os.environ.get("MAX_SESSIONS", "3")
UI_MODE = os.environ.get("UI_MODE", "no")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "/ui/management")
AUTH_MODE = os.environ.get("AUTH_MODE", "gateway")
AUTH_AUDIENCE = os.environ.get("AUTH_AUDIENCE", "workspace-api")
AUTH_DEBUG = os.environ.get("AUTH_DEBUG", "false")
TOKEN_BROKER_TIMEOUT_SECONDS = os.environ.get("TOKEN_BROKER_TIMEOUT_SECONDS", "10")
STORES = os.environ.get("STORES", "postgres,redis,mongo")
