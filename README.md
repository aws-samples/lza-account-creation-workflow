# account-creation-workflow

## Description

This solution will enable the ability to provide customers with a Self-Service mechinisum to deploy a new AWS Account using the Landing Zone Accelerator (LZA) solution. It uses an AWS Step Function to orchestrate a number of AWS Lambda Functions to add the account information to a Git repository, trigger LZA CodePipeline, validate that all AWS Resources are in place, then send out an completion email to the person requesting the account.

Optionally, there is a feature that will integration Microsoft Entra ID (Azure Active Directory) groups with permission sets during the account request. This feature can be enabled in the deploy-config.yaml file.

## Architecture

![alt text](images/AccountCreation.png)

### Step Function WorkFlow for Account Creation

![alt text](images/stepfunctions_graph.png)

### Folder Structure

| Folder/File                                       | Description |
| :------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| app                                               | CDK Application Infrastructure Code (e.g. Lambdas / StepFunctions / SES / S3)                                                                                                              |
| app/lambda_layer                                  | Directory to hold all AWS Lambda Layers source code.                                                                                                                                                                                  |
| app/lambda_layer/account_creation_helper          | AWS Lambda Layer that has all code that is referrenced more that once within multple Lambda Functions. |
| app/lambda_layer/azure_ad_helper         | AWS Lambda Layer that has code for connecting to the Microsoft Entra ID services. The layer uses MS Graph API for the connection. |
| app/lambda_layer/boto3          | AWS Lambda Layer for the boto3, since AWS Lambda doesn't always get packaged with the latest version fo Boto3. |
| app/lambda_layer/identity_center_helper          | AWS Lambda Layer that support common AWS Identity Center calls.  |
| app/lambda_src                                    | Directory to hold AWS Lambda Functions source code.                                 |
| app/lambda_src/event                              | Directory to hold AWS Lambda Functions that are triggered by an Event                                                                                                                                                                                |
| app/lambda_src/event/AccountTagToSsmParameter      | AWS Lambda Function creates an SSM Parameter in the target account based on Tags attached to the account within AWS Organizations. The SSM Parameter will be prefixed with "/account/tags/".                                                                                                                                                      |     |                                                                                                                |     |
| app/lambda_src/stepfunction                       | Directory to hold AWS Lambda Functions that are used within the AWS Step Function.                                                                                                                                                                         |
| app/lambda_src/stepfunction/AttachPermissionSet                         | AWS Lambda Function that will add a permissions set to an SSO Group. |
| app/lambda_src/stepfunction/AzureADGroupSync                            | AWS Lambda Function that will sync the desired Microsoft Entra ID Group to AWS Identity Center. |
| app/lambda_src/stepfunction/CheckForRunningProcesses                           | AWS Lambda Function that will check to see if the Decommissioning CodeBuild project and LZA Pipeline is currently running. If one of those resources are running it will delay the AWS Step Function. |
| app/lambda_src/stepfunction/CreateAccount                            | AWS Lambda Function that will use LZA to create an AWS Account. |
| app/lambda_src/stepfunction/CreateAddtionalResources                         | AWS Lambda Function that will create AWS resources that couldn't be managed by LZA or CloudFormation (e.g. Account Alias / Service Catalog Tags)                                                                                                                                                  |
| app/lambda_src/stepfunction/GetAccountStatus                         | AWS Lambda Function that will scan the AWS Service Catalog Provisioned Product to see if the account creation has completed.                                                                                                                                                  |
| app/lambda_src/stepfunction/ReturnResponse                           | AWS Lambda Function that will return either an Account Number (if account creation successful) or an error message (if there is a failure in the creation process).                                                                                                           |
| app/lambda_src/stepfunction/SendEmailWithSES                         | AWS Lambda Function that will send out emails to account requester or team mates waiting for the account creation to finish. |
| app/lambda_src/stepfunction/ValidateADGroupSyncToSSO                           | AWS Lambda Function validate that the desired Microsoft Entra ID Group to AWS Identity Center.. |
| app/lambda_src/stepfunction/ValidateResources                        | AWS Lambda Function that will ensure all Control Tower Customizations have run successfully.                                                                                                                                                                                  |
| app/stepfunction                                  | Directory that holds the AWS Step Function definitions.                                                                                                                                                                                                    |
| configs                                           | Configuration files used for the solution                                                                                                                                                                                      |
| configs/deploy-config.yaml                        | Configuration file used for deployment and application infrastructure                                                                                                                                                          |
| images                                            | Images used in README document.                                                                                                                                                                                                |
| pipeline                                          | CDK Deployment Infrastructure Code (e.g. CodePipeline / CodeCommit / CodeBuild )                                                                                                                                               |
| scripts                                           | Supporting scripts to ensure the Solution uses best practices                                                                                                                                                                  |
| tests                                             | All testing code should reside                                                                                                                                                                                                 |
| requirements.txt                                  | Pip requirements file for deployment environment.                                                                                                                                                                              |

## Pre-requisite Steps

- [Install Landing Zone Accelerator into the Management Account](https://aws.amazon.com/solutions/implementations/landing-zone-accelerator-on-aws/).

- [Install the Cloud Development Kit (CDK)](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html).

- [Install Docker](https://docs.docker.com/engine/install/) and start the Docker Engine.

- Ensure you have AWS CLI and Console access to the AWS Management Account.
  
  - NOTE: Please read disclaimer.

- (Optional) If you choose to use the Microsoft Entra ID integration the following steps will need to be performed to create a AWS Secret for that integration.

  - [How to get the required data from Microsoft Entra ID](docs/GET_MS_DATA.md)

- (Optional) If you would like to integrate the AWS Permissions Sets to an Microsoft Entra ID Group you will need to create an AWS Secret for GraphAPI.

  - Use the values collected from the previous step to set the variables for the AWS CLI Command.

  Example.

  ```bash
  # Variables 
  TENANT_ID='00000000-1111-2222-3333-444444444444'
  CLIENT_ID='55555555-6666-7777-8888-999999999999'
  OBJECT_ID='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
  SECRET_ID='ffffffff-gggg-hhhh-iiii-jjjjjjjjjjjj'
  SECRET_VALUE='****************************************'
  APP_ROLE_ID='kkkkkkkk-llll-mmmm-nnnn-oooooooooooo'
  ENTERPRISE_APP_NAME='AAAA'

  # Creating the Secret
  aws secretsmanager create-secret --name GraphApiSecret --secret-string "{\"client_id\": \"${CLIENT_ID}\", \"tenant_id\": \"${TENANT_ID}\", \"object_id\": \"${OBJECT_ID}\", \"app_role_id\": \"${APP_ROLE_ID}\", \"secret_value\": \"${SECRET_VALUE}\", \"secret_id\": \"${SECRET_ID}\"}"

  # Updating the Secret
  aws secretsmanager update-secret --secret-id GraphApiSecret --secret-string "{\"client_id\": \"${CLIENT_ID}\", \"tenant_id\": \"${TENANT_ID}\", \"object_id\": \"${OBJECT_ID}\", \"app_role_id\": \"${APP_ROLE_ID}\", \"secret_value\": \"${SECRET_VALUE}\", \"secret_id\": \"${SECRET_ID}\"}"
  ```

  - Use LZA to install the 3 dependant AWS CloudForamtion templates located in the dependencies directory.

    - account-creation-validation-role.yaml : This template will be deployed to all AWS Accounts and will provide the Validation Lambda Function with read-only access to the new account. This will ensure that the account was provisioned properly.

    - account-tagging-to-ssm-parameter-role.yaml : This template will be deployed to all AWS Accounts and will create an AWS SSM Parameter Store Parameter based on tags stored on the account within AWS Organizations. Each SSM Parameter will be prefixed with "/account/tags/".

    - config-log-validation-role.yaml : This template will be deployed into the LogArchive AWS Account and allow the Validation Lambda Function access to the S3 Bucket and AWS Config rules to ensure that they are setup properly.

    - Update the customizations-config.yaml file to deploy the 3 CloudFormation templates. Below is an example of the new entries for the config file.

    ```bash
    # customizations-config.yaml
    customizations:
      cloudFormationStacks:
        # --------------------------------------
        # Account Creation / Validation Roles
        # --------------------------------------
        - deploymentTargets:
            organizationalUnits:
              - Root
          description: IAM Role to allow Account Validation
          name: lza-account-creation-validation
          regions:
            - us-east-1
          template: cloudformation/account-creation-validation-role.yaml
          parameters:
            - name: pManagementAccountId
              value: "{{ account Management }}"
        - deploymentTargets:
            accounts:
              - LogArchive
          description: IAM Role to validate Config and Logs
          name: lza-config-log-validation-role
          regions:
            - us-east-1
          template: cloudformation/config-log-validation-role.yaml
          parameters:
            - name: pManagementAccountId
              value: "{{ account Management }}"    
        # ---------------------------------
        # Account Tagging to Account SSM
        # ---------------------------------
        - deploymentTargets:
            organizationalUnits:
              - Root
            excludedAccounts:
              - Management
          description: IAM Role to create SSM Parameters based on Account Tagging
          name: lza-account-tagging-to-ssm-parameter
          regions:
            - us-east-1
          template: cloudformation/account-tagging-to-ssm-parameter-role.yaml
          parameters:
            - name: pManagementAccountId
              value: "{{ account Management }}"
    
    ```

### **DISCLAIMER**

This solution will be deployed into your AWS Management Account. The AWS Management Account is a highly sensitive account that should be protected as much as possible using the least privileged permission model. We recommend that customers use a federated role for access _NOT_ and an IAM user. The required permissions are listed below.

For this example S3 Bucket Access Logging is not enabled but is recommended that you do so when added to your enterprise.

## Deployment Steps

- Ensure you have access to the AWS Management Account.

- Change directory into the repository directory.

  ```bash
  cd account-creation-approval-workflow
  ```

- Update the config/deploy-config.yaml file with the appropriate values. Typical values that will need updating; accountCreationFailure, accountCompletionFromEmail, ssoLoginUrl, rootEmailPrefix, rootEmailDomain, and enableAzureADIntegration.

  - To use the optional Microsoft Entra ID intgration you will need to set enableAzureADIntegration to true and make sure that the graphApiSecretName value matches the AWS Secret created in the pre-requiset step.

- Ensure that the Docker Engine is running, then run cdk the following commands to deploy the solution's deployment infrastructure. This will allow the solution to be enhanced via a CI/CD Pipeline. This will setup the deployment pipeline and dependent resources (e.g. CodeCommit / CodeBuild / CodePipeline). After the deployment the Git Repository (CodeCommit) will be populated automatically and trigger the CI/CD Pipeline (CodePipeline). Once the pipeline is complete the solution will be completely deployed.

  ```bash
  cdk bootstrap
  cdk synth
  cdk deploy
  ```

## How to Run AWS Step Function

### Arguments

- **account-name** **(-a)** (_string_) -- [REQUIRED]

  The name for the newly managed AWS Account that will be created by AWS Service Catalog / Control Tower.

- **support-dl** **(-s)** (_string_) -- [REQUIRED]

  Support Distribution Email Address for the new AWS Account.

- **managed-org-unit** **(-m)** (_string_) -- [REQUIRED]

  Managed organizational unit. The managed Account will be placed under this Organizational Unit.

- **purpose** **(-p)** (_string_) -- [REQUIRED]

  The purpose of the new AWS Account.

- **ad-integration** **(-ad)** (_string dictionary_) --

  Microsoft Entra ID Group integration to SSO Permission Sets.
  
  Example.

  ```bash
  --ad-integration "{\"PermissioSetName\": \"AzureActiveDirectoryGroupName\"}"
  ```

- **region** **(-r)** (_string_) --

  AWS Region in which the AWS Step Function exists. Default: us-east-1
  
- **force-update** **(-f)** (_string boolean_) --

  This argument will force a Service Catalog update Provisioned Product.

- **bypass-creation** **(-b)** (_string boolean_) --

  Skip adding the Account to the accounts-config.yaml and skip running of the of the Landing Zone Accelorator CodePipeline. This argument is typically used for testing the Account Creation Workflow process.

- **tags** **(-t)** (_string_) --

  Additional tag to add to the AWS Account. Default: account-name, support-dl and purpose.

  Example.

  ```bash
  --tags TEST1=VALUE1 TEST2=VALUE2
  ```
  
## Invoking the AWS Step Function

- Ensure you have access to the AWS Management Account.

- Change directory into the repository directory.

  ```bash
  cd account-creation-approval-workflow
  ```

- Ensure requirement-run.txt has been installed on the machine you would like to invoke AWS Step Function.

  - To install run requirements use the following command.

  ```bash
  pip install -r requirements-run.txt 
  ```

- Run the following commands to invoke the AWS Step Function.

  ```bash
  python ./run-stepfunction.py \
    --account-name "lza-test-01" \
    --support-dl "johnsmith@example.com" \
    --managed-org-unit "Workloads/Workload-1" \
    --purpose "Testing New Micro Service" \
    --force-update true \
    --ad-integration "{\"CustomerAccountAdmin\": \"platform-admin\", \"CustomerAccountDev\": \"workload1-app1\"}" \
    --bypass-creation true \
    --tags APPLICATION=TestingMicroService
  ```

**Result**: _Account ID_

## WARNING

The synchronization endpoint of the Graph API is in beta.
