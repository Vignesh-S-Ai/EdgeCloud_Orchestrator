# CLOUD-13 Faculty Demo

## Start the live dashboard

From PowerShell, run:

```powershell
Set-Location C:\Vignpro\EdgeCloud-Orchestrator\frontend
.\start-faculty-demo.ps1
```

The launcher:
- Uses the existing AWS CLI profile `edgecloud`.
- Verifies the AWS account and SSM instance status.
- Starts private Cloud/Scheduler Kubernetes port-forwards on the Cloud EC2 host if needed.
- Opens four IAM-authenticated SSM port-forwarding sessions:
  - `localhost:30083` -> Orchestrator NodePort
  - `localhost:9443` -> KubeEdge ServiceBus
  - `localhost:18001` -> Cloud Node service
  - `localhost:18002` -> Scheduler service
- Starts the Vite frontend on `http://127.0.0.1:5173`.

Keep all four SSM terminal windows and the Vite terminal open while presenting. Closing an SSM window disconnects that tunnel. The dashboard uses live health/resource endpoints and the Live Inference Lab submits actual image workloads to `POST /orchestrate`.

## Faculty demo sequence

1. Overview: explain the Edge, Orchestrator, Scheduler and Cloud services; show live health and CPU/RAM/disk gauges.
2. Live Inference Lab: upload a test image, choose Low/Medium/High priority, and run orchestration. Show the selected target, actual target, scheduler explanation, latency breakdown and detection output.
3. Live Orchestration: use the live scheduler decision probe. Routing history in this view remains explicitly labelled sample data because the backend does not expose a persistent history endpoint.
4. Edge Node and Cloud Node: inspect live health and resource snapshots.
5. Workloads and Logs: treat any sample-labelled panels as illustrative, not live Kubernetes inventory or production logs.

## Security and accuracy

- No public inbound AWS ports are required.
- Do not share AWS credentials or SSM session details with faculty.
- Do not switch to Demo mode during a live-evidence explanation.
- The Edge health status may read `degraded` because its camera is not open; the model can still be loaded and image inference is available through the API.
- Benchmark results are historical experiment evidence, not live rolling metrics.
