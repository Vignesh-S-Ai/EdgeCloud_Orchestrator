import boto3
import time
import json

session = boto3.Session(profile_name="edgecloud", region_name="ap-south-1")
ssm = session.client("ssm")

INSTANCE_ID = "i-07ecfbdd7781c5ef5"

commands = [
    ('K3s Flannel Network', "ip addr show | grep -A3 'cni0\\|flannel\\|vxlan'"),
    ('K3s Route Table', "ip route show"),
    ('K3s Pod CIDR', "k3s kubectl get node -o jsonpath='{.items[*].spec.podCIDR}'"),
    ('Flannel Config', "cat /var/lib/rancher/k3s/agent/etc/flannel/flannel.env 2>/dev/null || echo 'no flannel env'"),
    ('Route to Edge Pod CIDR', "ip route | grep 10.42"),
    ('K3s Service CIDR', "k3s kubectl get svc kubernetes -o jsonpath='{.spec.clusterIP}' 2>/dev/null && echo"),
    ('Iptables KUBE-SVC', "iptables -t nat -L -n | grep -A2 'KUBE-SVC' | head -30"),
    ('Test Edge Pod Connectivity', "curl -s --connect-timeout 3 http://10.42.1.56:8000/health 2>&1 || echo 'UNREACHABLE'"),
    ('Edge Tunnel Connectivity', "ss -tnp | grep -E '10000|10002' | head -10"),
    ('CloudStream TUNNEL-PORT Chain', "iptables -t nat -L TUNNEL-PORT -n 2>/dev/null || echo 'no TUNNEL-PORT chain'"),
    ('Ping Edge Node', "ping -c 1 -W 2 172.18.125.42 2>&1 || echo 'EDGE UNREACHABLE'"),
]

# Build a single script that runs all commands with clear delimiters
script_parts = ["#!/bin/bash"]
for label, cmd in commands:
    script_parts.append(f'echo "===== {label} ====="')
    script_parts.append(cmd)
    script_parts.append('echo ""')

full_script = "\n".join(script_parts)

print(f"Sending SSM command to {INSTANCE_ID}...")
resp = ssm.send_command(
    InstanceIds=[INSTANCE_ID],
    DocumentName="AWS-RunShellScript",
    Parameters={"commands": [full_script]},
    TimeoutSeconds=60,
)
command_id = resp["Command"]["CommandId"]
print(f"Command ID: {command_id}")

# Poll for completion
print("Waiting for command to complete...")
for i in range(60):
    time.sleep(5)
    invocations = ssm.list_command_invocations(CommandId=command_id)
    inv = invocations["CommandInvocations"][0]
    status = inv["Status"]
    print(f"  [{i*5}s] Status: {status}")
    if status in ("Success", "Failed", "Cancelled", "TimedOut"):
        break

# Fetch output
output = ssm.get_command_invocation(CommandId=command_id, InstanceId=INSTANCE_ID)
print("\n" + "=" * 80)
print("STANDARD OUTPUT:")
print("=" * 80)
print(output.get("StandardOutputContent", "(empty)"))
print("=" * 80)
print("STANDARD ERROR:")
print("=" * 80)
print(output.get("StandardErrorContent", "(empty)"))
print("=" * 80)
