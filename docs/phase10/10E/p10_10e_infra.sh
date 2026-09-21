#!/bin/bash
export LC_ALL=C
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
echo "=== NODES + READINESS ==="
kubectl get nodes -o wide
echo "=== NODE CPU/RAM (kubelet, includes edge pknode) ==="
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.capacity.cpu}{" cpu\t"}{.status.capacity.memory}{" mem\n"}{end}'
echo "=== PODS STATUS (edgecloud ns) ==="
kubectl get pods -n edgecloud -o wide
echo "=== POD RESTART COUNTS ==="
kubectl get pods -n edgecloud -o jsonpath='{range .items[*]}{.metadata.name}{"\trestarts="}{.status.containerStatuses[0].restartCount}{"\tready="}{.status.containerStatuses[0].ready}{"\n"}{end}'
echo "=== CLOUD HOST CPU/RAM ==="
uptime
nproc
free -m | head -2
echo "=== EDGE HOST find (from cluster node labels) ==="
kubectl get nodes --show-labels
echo "=== INFRA DONE ==="
