# Troubleshooting

## Issue-1

```bash
A task in the account creation step function failed: ', 'An error occurred (AccessDenied) when calling the AssumeRole operation: User: arn:aws:sts::000000000000:assumed-role/lza-account-creation-work-rLambdaFunctionValidateRe-aaaaaaaaaaaa/ValidateResources is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::111111111111:role/account-creation-validation
```

## Solution-1

Ensure that the role located in the deploy-config.yaml _lzaAccountValidationRole_
matches the role that has been deployed within the LZA solution.

## Issue-2

```bash
RuntimeError: Failed to bundle asset lza-account-creation-workflow-pipeline/Deploy-Application/lza-account-creation-workflow-application/rLambdaLayerAccountCreationHelper/Code/Stage, bundle output is located at /Users/brstucke/Documents/Projects/lza-account-creation-workflow/cdk.out/asset.b0ca15b35628b7c49a69449332b610e681bb5dad168964d26469d6d9c69568d2-error: Error: spawnSync docker ENOENT
```

## Solution-2

- Ensure Docker / Finch is running
- (Mac) Ensure the _Finch_ binary in /usr/local/bin is symlinked to _Docker_.

## Issue-3

```bash
Code archive supplied cannot be more than 20 MB compressed
```

## Solution-3

The source archive is too large. `scripts/upload_to_source_bucket.py` already
leaves out `.venv`, `cdk.out`, `.git` and `node_modules`. If your virtual
environment has another name, or other large folders sit in the project, add
them to `deployInfrastructure > sourceCode > ignoreFilesDirectories` in
`configs/deploy-config.yaml`.

## Issue-4

```bash
This CDK CLI is not compatible with the CDK library used by your application.
(Cloud assembly schema version mismatch ...)
```

## Solution-4

Update the CDK CLI with `npm install -g aws-cdk`. The CLI must be 2.1149.0 or
later.

## Issue-5

```bash
SSM parameter not available in account 000000000000, region us-east-1: /lza-account-creation-workflow/lza-pipeline-kms-key-arn
```

## Solution-5

Create the two SSM parameters described in the README prerequisites
(`/lza-account-creation-workflow/lza-pipeline-kms-key-arn` and
`/lza-account-creation-workflow/lza-config-bucket-name`) in the management
account and Region, then run `cdk synth` again.

## Issue-6

```bash
SyntaxError: unterminated string literal
```

The pipeline's Synth step fails on a line that works locally.

## Solution-6

The pipeline synthesizes on Python 3.11. An f-string whose `{...}` expression
spans several lines only works on Python 3.12 or later. Keep each expression on
one line, or split the string into adjacent f-strings. Check locally with
`python3.11 -m compileall -q app pipeline`.
