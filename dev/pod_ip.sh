#!/usr/bin/env bash
kubectl -n dev get po -o json | jq ".items[].status.podIP" -r
