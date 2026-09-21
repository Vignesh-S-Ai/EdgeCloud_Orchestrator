# IF EVERYTHING IS LOST, START HERE

## Prerequisites

- AWS CLI configured with a profile that has AdminAccess
- Terraform >= 1.0 installed
- Docker installed
- kubectl installed
- SSM Session Manager plugin installed
- Repository checked out locally

## Step 1: Read the Master Document

Read `docs/MASTER_PROJECT_REBUILD_AND_DISASTER_RECOVERY.md` for architecture, resource inventory, and decision framework.

## Step 2: Execute Rebuild Phases

Follow `docs/MASTER_REBUILD_RUNBOOK.md` — 16 phases. Key order:

1. AWS account + IAM
2. Terraform ECR repos (Phase 2)
3. Build + push images (Phase 3)
4. Terraform full apply (Phase 4) — EC2 boots with images already in ECR
5. Install K3s via SSM (Phase 7)
6. Install CloudCore via SSM (Phase 9)
7. Install EdgeCore via SSM (Phases 10-11)
8. Deploy K8s manifests (Phase 13)
9. Configure Rules (Phase 14)
10. Validate (Phase 15)
11. Benchmark (Phase 16)

## Step 3: Run Validation

```bash
bash infra/rebuild/scripts/08-validate.sh
```

## Step 4: Benchmark

Validate order-of-magnitude:
- /decision cached C1: ~66ms
- /decision uncached: ~1100ms
- /orchestrate C1: ~415ms

## Key Documents

| Document | Purpose |
|----------|---------|
| `MASTER_PROJECT_REBUILD_AND_DISASTER_RECOVERY.md` | Entry point |
| `MASTER_REBUILD_RUNBOOK.md` | 16-phase step-by-step |
| `CURRENT_WORKING_STATE_SNAPSHOT.md` | Exact current state |
| `FULL_REBUILD_VALIDATION_CHECKLIST.md` | 34 validation gates |
| `NEW_AWS_ACCOUNT_REBUILD.md` | Fresh account procedure |
| `KUBEEDGE_REBUILD_BLUEPRINT.md` | KubeEdge details |
| `TERRAFORM_REBUILD_SAFETY.md` | Terraform safety |
| `REBUILD_VERSION_MATRIX.md` | Locked versions |
| `RECOVERY_SECRETS_AND_CREDENTIALS.md` | Secrets procedure |
| `DISASTER_RECOVERY_SCENARIOS.md` | Per-scenario recovery |
| `REPOSITORY_REPRODUCIBILITY_AUDIT.md` | Repo gaps |
