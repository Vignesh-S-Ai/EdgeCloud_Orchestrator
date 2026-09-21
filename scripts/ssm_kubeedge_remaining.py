#!/usr/bin/env python3
"""Run remaining commands on EC2 via SSM."""

import boto3
import time

session = boto3.Session(profile_name='edgecloud', region_name='ap-south-1')
ssm = session.client('ssm')

INSTANCE_ID = 'i-07ecfbdd7781c5ef5'

remaining_script = r"""
echo "=====PORT_9443====="
ss -tlnp | grep 9443 || echo "port 9443 free"
echo "=====PORT_10004====="
ss -tlnp | grep 10004 || echo "port 10004 free"
echo "=====K3S_CHAINS====="
iptables -t nat -L -n 2>/dev/null | grep -E 'KUBE|CNI|FLANNEL' | head -20 || echo "(no K3s/CNI chains found)"
echo "=====SVC_EDGE_NODE====="
kubectl get svc edge-node -n edgecloud -o yaml 2>/dev/null || echo "(edge-node service not found)"
echo "=====SVC_ALL====="
kubectl get svc -n edgecloud 2>/dev/null || echo "(no edgecloud namespace or no services)"
echo "=====K3S_CIDR====="
k3s kubectl cluster-info dump 2>/dev/null | grep -o 'service-cluster-ip-range=[^ ]*' | head -1 || echo "(k3s not found or no cluster-info)"
echo "=====DONE====="
"""

resp = ssm.send_command(
    InstanceIds=[INSTANCE_ID],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': [remaining_script]},
    TimeoutSeconds=120,
)

cmd_id = resp['Command']['CommandId']
print(f"CommandId: {cmd_id}")

for attempt in range(24):
    time.sleep(5)
    result = ssm.get_command_invocation(CommandId=cmd_id, InstanceId=INSTANCE_ID)
    status = result['Status']
    print(f"  Attempt {attempt+1}: status={status}")
    if status in ('Success', 'Failed', 'TimedOut', 'Cancelled'):
        break

print(f"\nFinal Status: {result['Status']}")
print(f"StandardOutputContent:\n{result.get('StandardOutputContent', '(empty)')}")
print(f"StandardErrorContent:\n{result.get('StandardErrorContent', '(empty)')}")
