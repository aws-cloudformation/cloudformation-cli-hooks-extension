"""
This sub command sets the type configuration of the hook registered in your AWS account.
"""
import os
import logging
import json
from argparse import Namespace

from botocore.exceptions import ClientError

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError, SysExitRecommendedError

LOG = logging.getLogger(__name__)

COMMAND_NAME = "enable-lambda-function-invoker"


def _activate_lambda_function_invoker(cfn_client, execution_role_arn: str, alias: str) -> None:
    """
    Activates the AWSSamples::LambdaFunctionInvoker::Hook 3rd party hook by calling CloudFormation ActivateType API with arguments.
    https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_ActivateType.html

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        execution_role_arn (string): The ARN of the IAM role to be used as exeuction role for the hook.
        alias (string): The alias type name to use in place of AWSSamples::LambdaFunctionInvoker::Hook.

    Returns:
        dict: The response from the ActivateType API.

    Side effect: AWSSamples::LambdaFunctionInvoker::Hook type will be activated in AWS account.
    """
    kwargs = {
        "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
        "Type": "HOOK",
        "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b",
        "ExecutionRoleArn": execution_role_arn
    }
    if alias:
        kwargs["TypeNameAlias"] = alias
    LOG.debug("Calling ActivateType with input: %s", kwargs)
    try:
        response = cfn_client.activate_type(**kwargs)
        LOG.debug("Successful response from ActivateType")
        return response
    except cfn_client.exceptions.TypeNotFoundException as e:
        msg = "Setting type configuration resulted in TypeNotFoundException."
        print("\n" + msg)
        raise DownstreamError(msg) from e
    except ClientError as e:
        raise DownstreamError from e

def _set_type_configuration(cfn_client, type_arn: str, type_configuration_json: str) -> None:
    """
    Sets Hook type configuration by calling CloudFormation SetTypeConfiguration API with arguments.
    https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_SetTypeConfiguration.html

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        type_arn (string): The ARN for the hook to call SetTypeConfiguration with.
        type_configuration_json (string): The json formatted string to use as the Hook's TypeConfiguration.

    Returns:
        dict: The response from the SetTypeConfiguration API.

    Side effect: Type configuration of hook will be updated in AWS account.
    """
    LOG.debug("Calling SetTypeConfiguration for %s", type_arn)
    try:
        response = cfn_client.set_type_configuration(TypeArn=type_arn, Configuration=type_configuration_json)
        LOG.debug("Successful response from SetTypeConfiguration")
        return response
    except cfn_client.exceptions.TypeNotFoundException as e:
        msg = "Setting type configuration resulted in TypeNotFoundException. Have you registered this hook first?"
        print("\n" + msg)
        raise DownstreamError(msg) from e
    except ClientError as e:
        raise DownstreamError from e

def _build_configuration_json_string(lambda_function_arn, failure_mode, include_targets):
    """
    Builds the type configuration JSON string to use for the hook type.

    Parameters:
        lambda_function_arn (string): The ARN of the lambda function to invoke when this hook is invoked.
        failure_mode (string): Failure mode of the hook. Valid options: [WARN, FAIL]
        include_targets (string): Comma-seperated string of resource type names for this hook to target. Wildcards supported.

    Returns:
        string: JSON-formatted string of the type configuration.
    """
    configuration = {
        "CloudFormationConfiguration":{
            "HookConfiguration": {
                "FailureMode": failure_mode if failure_mode else "FAIL",
                "TargetStacks": "ALL",
                "Properties":{
                    "LambdaFunctions": [lambda_function_arn]
                }
            }
        }
    }

    if include_targets:
        configuration["CloudFormationConfiguration"]["HookConfiguration"]["TargetFilters"] = {
            "TargetNames": list(map(str.strip, include_targets.split(','))),
            "Actions": [
                "CREATE",
                "UPDATE"
            ],
            "InvocationPoints": [
                "PRE_PROVISION"
            ]
        }

    return json.dumps(configuration)


def _enable_lambda_function_invoker(args: Namespace) -> None:
    """
    Main method for the hook enable-lambda-function-invoker command.

    Parameters:
        args (Namespace): The arguments to use with this command.
            Required keys in Namespace: 'lambda_function_arn', 'failure_mode', 'execution_role_arn', 'alias',
            'include_targets','profile', 'endpoint_url', 'region'. All default to None.

    Returns: None.

    Side effect: Success message is printed to system out.
    """
    if not os.environ.get("CFN_CLI_HOOKS_EXPERIMENTAL") or os.environ.get("CFN_CLI_HOOKS_EXPERIMENTAL") != "enabled":
        msg = "To enable experimental features, please specify environment variable: 'export CFN_CLI_HOOKS_EXPERIMENTAL=enabled'"
        raise SysExitRecommendedError(msg)

    if args.include_targets is None:
        user_response = input("Without including `include-targets`, this will block all CloudFormation deployments on failure. \
                              \nDo you wish to proceed? [y/n]\n")
        if user_response.lower() != "y":
            msg = "Command aborted by user."
            raise SysExitRecommendedError(msg)

    cfn_client = create_sdk_session(args.region, args.profile).client("cloudformation", endpoint_url=args.endpoint_url)

    lambda_hook_arn = _activate_lambda_function_invoker(cfn_client, args.execution_role_arn, args.alias)["Arn"]

    configuration_json = _build_configuration_json_string(args.lambda_function_arn, args.failure_mode, args.include_targets)
    _set_type_configuration(cfn_client, lambda_hook_arn, configuration_json)

    print(f"Success: {args.alias or 'AWSSamples::LambdaFunctionInvoker::Hook'} will now be invoked " \
            f"for CloudFormation deployments for {args.include_targets or 'ALL'} resources in {args.failure_mode or 'FAIL'} mode.")

def setup_parser(parser):
    enable_lambda_invoker_subparser = parser.add_parser(COMMAND_NAME, description=__doc__)
    enable_lambda_invoker_subparser.set_defaults(command=_enable_lambda_function_invoker)
    enable_lambda_invoker_subparser.add_argument("--lambda-function-arn", help="Lambda function ARN to use for the hook.", required=True)
    enable_lambda_invoker_subparser.add_argument("--execution-role-arn", help="ARN of the IAM role to use for hook execution.", required=True)
    enable_lambda_invoker_subparser.add_argument("--failure-mode", help="Failure mode to configure for hook. Valid values: [WARN, FAIL]. Default is FAIL.")
    enable_lambda_invoker_subparser.add_argument("--alias", help="Alias to use for AWSSamples::LambdaFunctionInvoker::Hook")
    enable_lambda_invoker_subparser.add_argument("--include-targets", help="Comma-seperated list of resources to target with this hook. Wildcards supported.")
    enable_lambda_invoker_subparser.add_argument("--profile", help="AWS profile to use.")
    enable_lambda_invoker_subparser.add_argument("--endpoint-url", help="CloudFormation endpoint to use.")
    enable_lambda_invoker_subparser.add_argument("--region", help="AWS Region to submit the type.")
