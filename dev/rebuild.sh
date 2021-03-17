#!/usr/bin/env bash

if [ "$KUBECONFIG" != /etc/rancher/k3s/k3s.yaml ] ; then
    echo "wrong kubeconfig"
    exit 1
fi

set -eux
./dev/build.sh && kubectl -n dev delete po `kubectl -n dev get po -o json | jq ".items[].metadata.name" -r`
