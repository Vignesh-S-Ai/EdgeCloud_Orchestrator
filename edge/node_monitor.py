import boto3, time

session = boto3.Session(profile_name='edgecloud')
ssm = session.client('ssm', region_name='ap-south-1')

for i in range(10):
    t = time.time()
    try:
        resp = ssm.send_command(
            InstanceIds=['i-07ecfbdd7781c5ef5'],
            DocumentName='AWS-RunShellScript',
            Parameters={'commands': ['/usr/local/bin/kubectl get node wsl2-edge-node --no-headers | awk \'{print $2}\'']},
            TimeoutSeconds=30
        )
        cmd_id = resp['Command']['CommandId']
        time.sleep(15)
        result = ssm.get_command_invocation(CommandId=cmd_id, InstanceId='i-07ecfbdd7781c5ef5')
        status = result.get('StandardOutputContent', '').strip()
        print(f'Check {i+1:2d}/10 ({int(time.time()-t):2d}s): status={status}', flush=True)
        if 'NotReady' in status:
            print('*** NODE WENT NOTREADY ***')
        elif status == '':
            print(f'  (empty - stderr: {result.get("StandardErrorContent", "")[:200]})')
    except Exception as e:
        print(f'Check {i+1:2d}/10: ERROR {e}', flush=True)
    if i < 9:
        time.sleep(15)

print('=== 5-MINUTE MONITORING COMPLETE ===')
