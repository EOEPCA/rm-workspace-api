#!/usr/bin/env bash

if [ "$KUBECONFIG" != /etc/rancher/k3s/k3s.yaml ] ; then
    echo "wrong kubeconfig"
    exit 1
fi

set -eux

NAMESPACE=$1

kubectl -n $NAMESPACE create secret generic mucho-secreto --from-literal=access=access_value --from-literal=bucketname=bucketname_value --from-literal=secret=secret_value
# also create configmap
kubectl -n $NAMESPACE create configmap workspace --from-literal=quota_in_mb=256
