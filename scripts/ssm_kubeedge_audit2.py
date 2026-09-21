#!/usr/bin/env python3
"""Get full SSM output by downloading from S3 URL."""

import boto3
import time
import sys

session = boto3.Session(profile_name='edgecloud', region_name='ap-south-1')
ssm = session.client('ssm')
s3 = session.client('s3')

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

# Print StandardOutputUrl for full download
output_url = result.get('StandardOutputUrl', '')
error_url = result.get('StandardErrorContent', '')
print(f"StandardOutputUrl: {output_url}")
print(f"StandardErrorContent: {error_url}")

# Try to download from URL
if output_url:
    print("\n=== DOWNLOADING FULL OUTPUT FROM S3 ===")
    # Parse the S3 URL
    # Format: https://ssm.REGION.amazonaws.com/path
    import urllib.request
    try:
        req = urllib.request.Request(output_url)
        # Need to sign the request for S3
        # Use boto3 to download instead
        parts = output_url.replace('https://', '').split('/', 1)
        bucket_key = parts[1] if len(parts) > 1 else ''
        bucket = bucket_key.split('/')[0] if '/' in bucket_key else ''
        key = '/'.join(bucket_key.split('/')[1:]) if '/' in bucket_key else ''

        if bucket and key:
            obj = s3.get_object(Bucket=bucket, Key=key)
            content = obj['Body'].read().decode('utf-8')
            print(content)
        else:
            print(f"Could not parse S3 URL: {output_url}")
    except Exception as e:
        print(f"Error downloading: {e}")
        print("Falling back to truncated content")
        print(result.get('StandardOutputContent', ''))
