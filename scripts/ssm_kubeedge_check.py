"""Send SSM commands to KubeEdge cloud node to inspect CRDs, services, and config."""

import time
import boto3

INSTANCE_ID = "i-07ecfbdd7781c5ef5"
REGION = "ap-south-1"
TIMEOUT = 60
POLL_INTERVAL = 3

COMMANDS = {
    "1_crds": "kubectl get crd | grep -i kubeedge",
    "2_svc": "kubectl get svc edge-node -n edgecloud -o yaml",
    "3_endpoints": "kubectl get endpoints edge-node -n edgecloud -o yaml",
    "4_endpoint_slices": (
        "kubectl get endpointslices -n edgecloud -o yaml 2>/dev/null || "
        "kubectl get endpointslice -n edgecloud -o yaml 2>/dev/null || "
        "echo 'no endpoint slices'"
    ),
    "5_deployments": (
        "kubectl get deploy -n kubeedge 2>/dev/null || echo 'no kubeedge deployments'\n"
        "kubectl get pods -n kubeedge-system 2>/dev/null || echo 'no kubeedge-system pods'\n"
        "kubectl get pods -n kubeedge 2>/dev/null || echo 'no kubeedge pods'"
    ),
    "6_downstream": "grep -A30 'downstream' /etc/kubeedge/config/cloudcore.yaml",
    "7_dynamic_controller": "grep -A5 'dynamicController' /etc/kubeedge/config/cloudcore.yaml",
    "8_rules": (
        "kubectl get ruleendpoints -A 2>/dev/null || echo 'no ruleendpoints'\n"
        "kubectl get rules -A 2>/dev/null || echo 'no rules'"
    ),
    "9_crd_names": "kubectl get crd -o name 2>/dev/null",
    "10_cloudcore_yaml": "cat /etc/kubeedge/config/cloudcore.yaml",
}


def get_ssm_client():
    session = boto3.Session(profile_name="edgecloud", region_name=REGION)
    return session.client("ssm")


def send_and_wait(ssm, name, cmd_text):
    """Send a command, poll until done, return output."""
    resp = ssm.send_command(
        InstanceIds=[INSTANCE_ID],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [cmd_text]},
        TimeoutSeconds=60,
        Comment=f"kubeedge-check-{name}",
    )
    cmd_id = resp["Command"]["CommandId"]

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        invocations = ssm.list_command_invocations(CommandId=cmd_id, Details=True)
        for inv in invocations.get("CommandInvocations", []):
            status = inv["Status"]
            if status == "Success":
                output = ""
                for plugin in inv.get("CommandPlugins", []):
                    output += plugin.get("Output", "")
                return output
            elif status in ("Failed", "Cancelled", "TimedOut"):
                err = ""
                for plugin in inv.get("CommandPlugins", []):
                    err += plugin.get("Output", "")
                return f"[{status}] {err}"
    return "[TIMEOUT] Command did not finish in time"


def main():
    ssm = get_ssm_client()
    results = {}

    for name, cmd in COMMANDS.items():
        print(f"\n{'='*80}")
        print(f"RUNNING: {name}")
        print(f"COMMAND: {cmd}")
        print(f"{'='*80}")
        try:
            output = send_and_wait(ssm, name, cmd)
            results[name] = output
            print(output)
        except Exception as e:
            err = f"ERROR: {e}"
            results[name] = err
            print(err)

    print("\n\n" + "#" * 80)
    print("SUMMARY OF ALL RESULTS")
    print("#" * 80)
    for name, output in results.items():
        print(f"\n--- {name} ---")
        print(output)


if __name__ == "__main__":
    main()
