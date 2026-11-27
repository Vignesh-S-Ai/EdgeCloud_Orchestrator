param(
  [Parameter(Mandatory = $true)]
  [ValidateSet(30083, 9443, 18001, 18002)]
  [int]$Port
)

$ErrorActionPreference = 'Stop'
$env:Path += ';C:\Program Files\Amazon\SessionManagerPlugin\bin'
$env:AWS_PROFILE = 'edgecloud'
$env:AWS_DEFAULT_REGION = 'ap-south-1'

$params = @{ portNumber = @("$Port"); localPortNumber = @("$Port") } | ConvertTo-Json -Compress
$tempFile = Join-Path $env:TEMP "cloud13-ssm-$Port.json"
[IO.File]::WriteAllText($tempFile, $params, [Text.Encoding]::ASCII)

Write-Host "CLOUD-13 secure tunnel: localhost:$Port -> AWS Cloud EC2:$Port" -ForegroundColor Cyan
aws ssm start-session --target i-0086f3895dc6e18ae --document-name AWS-StartPortForwardingSession --parameters "file://$tempFile" --region ap-south-1 --profile edgecloud
