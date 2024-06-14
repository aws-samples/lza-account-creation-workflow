# Troubleshooting

## Issue-1

```bash
A task in the account creation step function failed: ', 'An error occurred (AccessDenied) when calling the AssumeRole operation: User: arn:aws:sts::000000000000:assumed-role/lza-account-creation-work-rLambdaFunctionValidateRe-aaaaaaaaaaaa/ValidateResources is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::111111111111:role/account-creation-validation
```

## Solution-1

Ensure that the role located in the deploy-config.yaml _lzaAccountValidationRole_ matches the role that has been deployed within the LZA solution.

## Issue-2

```bash
RuntimeError: Failed to bundle asset lza-account-creation-workflow-pipeline/Deploy-Application/lza-account-creation-workflow-application/rLambdaLayerAccountCreationHelper/Code/Stage, bundle output is located at /Users/brstucke/Documents/Projects/lza-account-creation-workflow/cdk.out/asset.b0ca15b35628b7c49a69449332b610e681bb5dad168964d26469d6d9c69568d2-error: Error: spawnSync docker ENOENT
```

## Solution-2

- Ensure Docker / Finch is running
- (Mac) Ensure the _Finch_ binary in /usr/local/bin is symlinked to _Docker_.

## Issue-3

```bash
1:05:11 PM | CREATE_FAILED        | AWS::CodeCommit::Repository | rCodeCommitRepositoryFC966E2D
Code archive supplied cannot be more than 20 MB compressed
```

## Solution-3

If using a virutal environment for python make sure to use the directory _.venv_ if you decided to keep your currenty virtual environment name. Update the config _deployInfrastructure > codecommit > ignoreFilesDirectoriesCodeCommit_ with your current virtual enviornment directory to ensure that it does't get added to AWS CodeCommit.
