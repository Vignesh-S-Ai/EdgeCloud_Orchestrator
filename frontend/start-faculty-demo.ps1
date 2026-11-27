# Start the CLOUD-13 faculty dashboard using IAM-authenticated SSM tunnels.
# No public AWS ports are opened. Keep the tunnel windows running during the demo.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = $PSScriptRoot
$plugin = 'C:\Program Files\Amazon\SessionManagerPlugin\bin\session-manager-plugin.exe'

if (-not (Test-Path $plugin)) {
  throw 'AWS Session Manager Plugin is missing. Install with: winget install --id Amazon.SessionManagerPlugin'
}
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
  throw 'AWS CLI was not found.'
}

$env:AWS_PROFILE = 'edgecloud'
$env:AWS_DEFAULT_REGION = 'ap-south-1'
$identity = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or $identity -ne '171743139339') {
  throw 'The edgecloud AWS profile did not resolve to the expected AWS account.'
}

$instanceStatus = aws ssm describe-instance-information --filters Key=InstanceIds,Values=i-0086f3895dc6e18ae --query 'InstanceInformationList[0].PingStatus' --output text
if ($LASTEXITCODE -ne 0 -or $instanceStatus -ne 'Online') {
  throw 'The CLOUD-13 AWS Cloud EC2 instance is not Online in Systems Manager.'
}

# Ensure the private K3s services have local-only port-forwards on the Cloud EC2 host.
$remoteScript = @'
sudo bash -lc 'if ! ss -ltn | grep -q ":18001 "; then nohup kubectl -n edgecloud port-forward --address 127.0.0.1 svc/cloud-node 18001:8001 >/tmp/cloud13-cloud-pf.log 2>&1 </dev/null & fi; if ! ss -ltn | grep -q ":18002 "; then nohup kubectl -n edgecloud port-forward --address 127.0.0.1 svc/scheduler 18002:8002 >/tmp/cloud13-scheduler-pf.log 2>&1 </dev/null & fi; sleep 2; ss -ltn | grep -E ":18001 |:18002 "'
'@
$commandParams = @{ commands = @($remoteScript) } | ConvertTo-Json -Depth 5 -Compress
$commandFile = Join-Path $env:TEMP 'cloud13-dashboard-bootstrap.json'
[IO.File]::WriteAllText($commandFile, $commandParams, [Text.Encoding]::ASCII)
$commandId = aws ssm send-command --instance-ids i-0086f3895dc6e18ae --document-name AWS-RunShellScript --parameters "file://$commandFile" --comment 'Start private CLOUD-13 dashboard service forwards' --timeout-seconds 30 --query Command.CommandId --output text
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the private K3s port-forwards.' }

$state = 'InProgress'
for ($i = 0; $i -lt 25 -and $state -eq 'InProgress'; $i++) {
  Start-Sleep -Seconds 1
  $state = aws ssm get-command-invocation --command-id $commandId --instance-id i-0086f3895dc6e18ae --query Status --output text
}
if ($state -ne 'Success') {
  $details = aws ssm get-command-invocation --command-id $commandId --instance-id i-0086f3895dc6e18ae --query StandardErrorContent --output text
  throw "Private K3s port-forward initialization failed: $details"
}

$tunnelScript = Join-Path $PSScriptRoot 'ssm-tunnel.ps1'
foreach ($port in @(30083, 9443, 18001, 18002)) {
  $listening = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  if (-not $listening) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $tunnelScript, '-Port', "$port")
    Start-Sleep -Milliseconds 500
  } else {
    Write-Host "localhost:$port is already listening; leaving it untouched." -ForegroundColor Yellow
  }
}

$viteListening = Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue
if (-not $viteListening) {
  Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', "Set-Location '$frontendRoot'; npm run dev -- --host 127.0.0.1")
} else {
  Write-Host 'Vite is already listening on localhost:5173; leaving it untouched.' -ForegroundColor Yellow
}

Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:5173'
Write-Host ''
Write-Host 'CLOUD-13 faculty dashboard is starting.' -ForegroundColor Green
Write-Host 'Keep the four SSM tunnel windows open. Close them after the demonstration.' -ForegroundColor Cyan
Write-Host 'Dashboard: http://127.0.0.1:5173'
