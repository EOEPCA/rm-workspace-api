# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
# SPDX-License-Identifier: Apache-2.0

import os

PREFIX_FOR_NAME = os.environ.get("PREFIX_FOR_NAME", "ws")
WORKSPACE_SECRET_NAME = os.environ.get("WORKSPACE_SECRET_NAME", "workspace")
CONTAINER_REGISTRY_SECRET_NAME = os.environ.get("CONTAINER_REGISTRY_SECRET_NAME", "container-registry")
ENDPOINT = os.environ.get("ENDPOINT", os.environ.get("AWS_ENDPOINT_URL"))
REGION = os.environ.get("REGION", os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION")))
# set UI_MODE to "ui" to activate UI
UI_MODE = os.environ.get("UI_MODE", "no")
# set FRONTEND_URL to "http://localhost:9000" to use dev server
FRONTEND_URL = os.environ.get("FRONTEND_URL", "/ui/management")
