# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import os

PREFIX_FOR_NAME = os.environ.get("PREFIX_FOR_NAME", "")
USE_VCLUSTER = os.environ.get("USE_VCLUSTER", "false")
SESSION_MODE = os.environ.get("SESSION_MODE", "on")
ENDPOINT = os.environ.get("ENDPOINT", os.environ.get("AWS_ENDPOINT_URL"))
REGION = os.environ.get("REGION", os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION")))
UI_MODE = os.environ.get("UI_MODE", "no")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "/ui/management")
AUTH_MODE = os.environ.get("AUTH_MODE", "gateway")
AUTH_DEBUG = os.environ.get("AUTH_DEBUG", "false")
