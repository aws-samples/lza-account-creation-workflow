# Changelog

## Unreleased

### Security

- Reword the "force-update flag is False" error messages so Bandit no
  longer reports B608 (false positive). Add a `.bandit` configuration that
  documents why, and point `scripts/scan.sh` at `app/lambda_src`,
  `app/lambda_layer` and `scripts`.
- Replace the log-retention custom resource and its role with one explicit
  CloudWatch log group per Lambda function (two-month retention).
- Scope the CreateAccountS3, CreateAdditionalResources and ReturnResponse
  roles to specific buckets, keys, topics and account ARNs.
- Read the LZA pipeline KMS key ARN and config bucket name from two SSM
  parameters (`lzaPipelineKmsKeyArn`, `lzaConfigBucketName`). Synth reports
  an error that names the parameter when a value is empty or invalid, and
  the synth CodeBuild role can read exactly those two parameters.
- Add a dedicated access-log bucket (SSE-S3, 90-day expiry) and enable
  server access logging on the pipeline source and artifact buckets.
  Remove the unused `PipelineS3Bucket`.
- Move the inline IAM policies in `dependencies/` templates to managed
  policies.

### Removed

- `dependencies/config-log-validation-role.yaml`, the
  `lzaConfigLogValidationRole` setting and the unused
  `ASSUMED_CONFIG_LOG_ROLE_NAME` variable. Remove the
  `lza-config-log-validation-role` stack from your LZA customizations.

### Fixed

- Attach the `account_creation_helper` layer to CheckForRunningProcesses,
  CreateAccountS3 and CreateAccountGitHub.
- Grant GetAccountStatus `codebuild:BatchGetBuilds` on the LZA CodeBuild
  projects.

### Upgrade notes

- Create the two SSM parameters described in the README before deploying.
- Log history in the old Lambda log groups is not kept; the previous log
  retention custom resource deletes those groups when the stack updates.
