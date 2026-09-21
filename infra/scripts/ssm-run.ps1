param(
  [Parameter(Mandatory=$true)][string]$ScriptPath,
  [Parameter(Mandatory=$true)][string]$InstanceId,
  [string]$Comment = "SSM",
  [int]$TimeoutSec = 120
)
# Reusable SSM runner: base64-encode a local bash script, send via AWS-RunShellScript,
# poll, and print the StandardOutput/StandardError.
#
# Note: if the remote command's output contains non-ASCII bytes, the bundled AWS CLI
# may fail to print it to a cp1252 console ('charmap' error). If that happens the command
# DID run; wrap your script to base64/gzip its own result output and decode locally.
$ErrorActionPreference = "Stop"
$raw = Get-Content -LiteralPath $ScriptPath -Raw -Encoding UTF8
$bytes = [System.Text.Encoding]::UTF8.GetBytes($raw)
$b64 = [System.Convert]::ToBase64String($bytes)
$cmd = "echo $b64 | base64 -d > /tmp/ssm_script.sh && chmod +x /tmp/ssm_script.sh && /tmp/ssm_script.sh"
$json = '{"commands":["' + $cmd + '"]}'
$paramsFile = "$env:TEMP\ssm_params.json"
[System.IO.File]::WriteAllText($paramsFile, $json, (New-Object System.Text.UTF8Encoding($false)))

$cmdId = aws ssm send-command --profile edgecloud --region ap-south-1 --instance-ids $InstanceId --document-name "AWS-RunShellScript" --comment $Comment --parameters file://$paramsFile --output text --query 'Command.CommandId'
if (-not $cmdId) { Write-Error "send-command failed"; exit 1 }
Write-Host "CommandId=$cmdId"

$status = ""
for ($i = 0; $i -lt ($TimeoutSec / 5); $i++) {
  Start-Sleep -Seconds 5
  $inv = aws ssm get-command-invocation --profile edgecloud --region ap-south-1 --command-id $cmdId --instance-id $InstanceId --query 'Status' --output text
  if ($inv -in @("Success","Failed","Cancelled","TimedOut")) { $status = $inv; break }
}
if (-not $status) { Write-Error "Timeout waiting for command"; exit 1 }
Write-Host "Status=$status"
$out = aws ssm get-command-invocation --profile edgecloud --region ap-south-1 --command-id $cmdId --instance-id $InstanceId --query 'StandardOutputContent' --output text
$err = aws ssm get-command-invocation --profile edgecloud --region ap-south-1 --command-id $cmdId --instance-id $InstanceId --query 'StandardErrorContent' --output text
Write-Host "----- STDOUT -----"
Write-Host $out
if ($err) { Write-Host "----- STDERR -----"; Write-Host $err }
if ($status -ne "Success") { exit 2 }
