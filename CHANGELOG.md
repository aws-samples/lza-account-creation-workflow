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

### Changed

- Move every Lambda function and layer from Python 3.12 to Python 3.14, with
  the matching SAM build image
  (`public.ecr.aws/sam/build-python3.14:1.174.0-20261120044557`). The
  runtime and image are set once in `app/cdk_helpers/lambda_helper.py`.
- Update Python dependencies: aws-cdk-lib 2.277.0, cdk-nag 2.38.2,
  boto3 1.44.7, PyYAML 6.0.3, requests 2.34.2, msal 1.39.0, PyGithub 2.10.0,
  urllib3 2.8.0, moto 5.2.5, pytest 9.2.0, pytest-cov 7.1.0 and tox 4.67.15.
  `pip-audit` reports no known vulnerabilities for the pinned set.
- The CDK CLI must be 2.1149.0 or later.
- Migrate the unit tests to moto 5 (`mock_aws`).
- Reformat the Python code to pass `pycodestyle` at 120 columns. Layout only;
  no behaviour change.

### Fixed

- Keep the CDK app compatible with Python 3.11, which the pipeline's synth
  step uses: no f-string expressions spread over several lines.
- Attach the `account_creation_helper` layer to CheckForRunningProcesses,
  CreateAccountS3 and CreateAccountGitHub.
- Grant GetAccountStatus `codebuild:BatchGetBuilds` on the LZA CodeBuild
  projects.

### Upgrade notes

- Create the two SSM parameters described in the README before deploying.
- Log history in the old Lambda log groups is not kept; the previous log
  retention custom resource deletes those groups when the stack updates.
