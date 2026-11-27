FROM 171743139339.dkr.ecr.ap-south-1.amazonaws.com/edgecloud/edge-node:latest
COPY --chown=appuser:appuser edge/ /app/edge/
