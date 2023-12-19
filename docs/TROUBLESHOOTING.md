# Troubleshooting

## Issue

'A task in the account creation step function failed: ', 'An error occurred (AccessDenied) when calling the AssumeRole operation: User: arn:aws:sts::000000000000:assumed-role/lza-account-creation-work-rLambdaFunctionValidateRe-aaaaaaaaaaaa/ValidateResources is not authorized to perform: sts:AssumeRole on resource: arn:aws:iam::111111111111:role/account-creation-validation'

## Solution

Ensure that the role located in the deploy-config.yaml _lzaAccountValidationRole_ matches the role that has been deployed within the LZA solution.
