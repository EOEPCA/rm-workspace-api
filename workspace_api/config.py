# Copyright 2026, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import os

PREFIX_FOR_NAME = os.environ.get("PREFIX_FOR_NAME", "")
PROVIDER_ENVIRONMENT = os.environ.get("PROVIDER_ENVIRONMENT", "datalab")
USE_VCLUSTER = os.environ.get("USE_VCLUSTER", "false")
SESSION_MODE = os.environ.get("SESSION_MODE", "on")
MAX_SESSIONS = os.environ.get("MAX_SESSIONS", "3")
ENDPOINT = os.environ.get("ENDPOINT", os.environ.get("AWS_ENDPOINT_URL"))
REGION = os.environ.get("REGION", os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION")))
UI_MODE = os.environ.get("UI_MODE", "no")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "/ui/management")
AUTH_MODE = os.environ.get("AUTH_MODE", "gateway")
AUTH_DEBUG = os.environ.get("AUTH_DEBUG", "false")
DISABLE_STORES = os.environ.get("DISABLE_STORES", "false")
DISABLED_STORE_TYPES = os.environ.get("DISABLED_STORE_TYPES", os.environ.get("DISABLED_STORES", ""))
DISABLE_DOCKER_REGISTRY = os.environ.get("DISABLE_DOCKER_REGISTRY", "false")
