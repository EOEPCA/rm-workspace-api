#!/usr/bin/env bash

set -eux

# build for vscode, docker-compose and k8s

docker build . -t workspace-api_workspace-api:latest -t workspace-api-k8s:0
