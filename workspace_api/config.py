# Copyright 2025, EOX (https://eox.at) and Versioneer (https://versioneer.at)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

PREFIX_FOR_NAME = os.environ.get("PREFIX_FOR_NAME", "ws")
WORKSPACE_SECRET_NAME = os.environ.get("WORKSPACE_SECRET_NAME", "workspace")
CONTAINER_REGISTRY_SECRET_NAME = os.environ.get("CONTAINER_REGISTRY_SECRET_NAME", "container-registry")
# set UI_MODE to "ui" to activate UI
UI_MODE = os.environ.get("UI_MODE", "no")
# set FRONTEND_URL to "http://localhost:9000" to use dev server
FRONTEND_URL = os.environ.get("FRONTEND_URL", "/ui/management")
