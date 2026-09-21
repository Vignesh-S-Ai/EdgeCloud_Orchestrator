#!/usr/bin/env python3
"""Send combined SSM commands to EC2 instance to audit KubeEdge deployment."""

import boto3
import time
import json
import sys

session = boto3.Session(profile_name='edgecloud', region_name='ap-south-1')
ssm = session.client('ssm')

INSTANCE_ID = 'i-07ecfbdd7781c5ef5'

combined_script = r"""
echo "=====CRDS_START====="
kubectl get crd -o custom-columns=NAME:.metadata.name,GROUP:.spec.group,VERSION:.spec.versions[0].name 2>/dev/null || echo "(kubectl not found or no CRDs)"
echo "=====CRDS_END====="

echo "=====CRDS_KUBEEDGE_START====="
kubectl get crd 2>/dev/null | grep -E 'rule|router|kubeedge' || echo "(no kubeedge router/rule CRDs found)"
echo "=====CRDS_KUBEEDGE_END====="

echo "=====CRDS_OPS_START====="
kubectl get crd 2>/dev/null | grep -E 'operation|upgrade|configupdate|imagepull|device' || echo "(no kubeedge ops/device CRDs found)"
echo "=====CRDS_OPS_END====="

echo "=====IPTABLES_NAT_START====="
iptables -t nat -L -n --line-numbers 2>/dev/null | head -80 || echo "(iptables not available or no permission)"
echo "=====IPTABLES_NAT_END====="

echo "=====IPTABLES_NAT_KUBE_START====="
iptables -t nat -L -n 2>/dev/null | grep -i kube || echo "(no kube chains in NAT)"
echo "=====IPTABLES_NAT_KUBE_END====="

echo "=====IPTABLES_FILTER_KUBE_START====="
iptables -L -n 2>/dev/null | grep -i kube || echo "(no kube chains in filter)"
echo "=====IPTABLES_FILTER_KUBE_END====="

echo "=====PORT_9443_START====="
ss -tlnp | grep 9443 || echo "port 9443 free"
echo "=====PORT_9443_END====="

echo "=====PORT_10004_START====="
ss -tlnp | grep 10004 || echo "port 10004 free"
echo "=====PORT_10004_END====="

echo "=====K3S_CHAINS_START====="
iptables -t nat -L -n 2>/dev/null | grep -E 'KUBE|CNI|FLANNEL' | head -20 || echo "(no K3s/CNI chains found)"
echo "=====K3S_CHAINS_END====="

echo "=====SVC_EDGE_NODE_START====="
kubectl get svc edge-node -n edgecloud -o yaml 2>/dev/null || echo "(edge-node service not found)"
echo "=====SVC_EDGE_NODE_END====="

echo "=====SVC_ALL_START====="
kubectl get svc -n edgecloud 2>/dev/null || echo "(no edgecloud namespace or no services)"
echo "=====SVC_ALL_END====="

echo "=====K3S_CIDR_START====="
k3s kubectl cluster-info dump 2>/dev/null | grep -o 'service-cluster-ip-range=[^ ]*' | head -1 || echo "(k3s not found or no cluster-info)"
echo "=====K3S_CIDR_END====="
"""

resp = ssm.send_command(
    InstanceIds=[INSTANCE_ID],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': [combined_script]},
    TimeoutSeconds=120,
)

cmd_id = resp['Command']['CommandId']
print(f"CommandId: {cmd_id}")

for attempt in range(24):
    time.sleep(5)
    result = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE_ID)
    status = result['Status']
    print(f"  Attempt {attempt+1}: status={status}", file=sys.stderr)
    if status in ('Success', 'Failed', 'TimedOut', 'Cancelled'):
        break

print(f"\nFinal Status: {result['Status']}")
print(f"ResponseCode: {result.get('ResponseCode', 'N/A')}")

# Dump full result structure to see what keys exist
print("\n=== Full response keys ===")
print(json.dumps(list(result.keys()), indent=2))

for key in sorted(result.keys()):
    val = result[key]
    if isinstance(val, str) and len(val) > 0:
        print(f"\n--- {key} ---")
        print(val)
    elif isinstance(val, dict):
        print(f"\n--- {key} (dict) ---")
        print(json.dumps(val, indent=2))
    elif isinstance(val, list) and val:
        print(f"\n--- {key} (list) ---")
        print(json.dumps(val, indent=2))
