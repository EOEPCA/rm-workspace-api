#!/usr/bin/env bash

if [ "$KUBECONFIG" != /etc/rancher/k3s/k3s.yaml ] ; then
    echo "wrong kubeconfig"
    exit 1
fi

set -eux

cd `dirname $0`

kubectl delete clusterrolebindings.rbac.authorization.k8s.io workspace-api
kubectl delete clusterroles.rbac.authorization.k8s.io workspace-api

for file in *.yaml; do
    kubectl apply -f "$file"
done

( cd ./workspace-charts ; kubectl kustomize . | kubectl apply -f - )
