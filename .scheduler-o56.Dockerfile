FROM 171743139339.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/scheduler:latest
COPY --chown=appuser:appuser scheduler/ /app/scheduler/
