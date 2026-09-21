"""Follow-up SSM commands to get truncated/missing output."""

import time
import boto3

INSTANCE_ID = "i-07ecfbdd7781c5ef5"
REGION = "ap-south-1"
TIMEOUT = 60
POLL_INTERVAL = 3

COMMANDS = {
    "cloudcore_yaml_part2": "cat /etc/kubeedge/config/cloudcore.yaml | tail -n +70",
    "edgecontroller_crds": "kubectl get deploy,ds -A | grep -i kubeedge",
    "all_ns_pods": "kubectl get pods -A | grep -i kubeedge",
    "edgecore_check": "ls /etc/kubeedge/config/ 2>/dev/null",
    "cloudcore_full": "wc -l /etc/kubeedge/config/cloudcore.yaml",
    "cloudcore_full_cat": "cat /etc/kubeedge/config/cloudcore.yaml | head -200",
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
        Comment=f"kubeedge-followup-{name}",
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
