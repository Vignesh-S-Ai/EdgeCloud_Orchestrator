"""Final SSM commands to find CloudCore pods and KubeEdge deployment mode."""

import time
import boto3

INSTANCE_ID = "i-07ecfbdd7781c5ef5"
REGION = "ap-south-1"
TIMEOUT = 60
POLL_INTERVAL = 3

COMMANDS = {
    "all_pods": "kubectl get pods -A -o wide",
    "all_ns": "kubectl get ns",
    "static_pods": "ls /etc/kubernetes/manifests/ 2>/dev/null || echo 'no manifests dir'",
    "systemd_kubeedge": "systemctl status kubeedge 2>/dev/null || systemctl status cloudcore 2>/dev/null || echo 'no kubeedge systemd service'",
    "process_cloudcore": "ps aux | grep -i cloudcore | grep -v grep",
    "process_edgecore": "ps aux | grep -i edgecore | grep -v grep || echo 'no edgecore process'",
    "k3s_check": "systemctl status k3s 2>/dev/null | head -20 || echo 'no k3s service'",
    "crd_service_obj": "kubectl get service -A -o wide",
    "configmaps_in_edgecloud": "kubectl get configmap -n edgecloud",
    "deployments_all": "kubectl get deploy -A -o wide",
    "daemonsets_all": "kubectl get ds -A -o wide",
    "full_crds": "kubectl get crd -o yaml",
}


def get_ssm_client():
    session = boto3.Session(profile_name="edgecloud", region_name=REGION)
    return session.client("ssm")


def send_and_wait(ssm, name, cmd_text):
    resp = ssm.send_command(
        InstanceIds=[INSTANCE_ID],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [cmd_text]},
        TimeoutSeconds=60,
        Comment=f"kubeedge-final-{name}",
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
    return "[TIMEOUT]"


def main():
    ssm = get_ssm_client()
    for name, cmd in COMMANDS.items():
        print(f"\n{'='*80}")
        print(f"RUNNING: {name}")
        print(f"COMMAND: {cmd}")
        print(f"{'='*80}")
        try:
            output = send_and_wait(ssm, name, cmd)
            print(output)
        except Exception as e:
            print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
