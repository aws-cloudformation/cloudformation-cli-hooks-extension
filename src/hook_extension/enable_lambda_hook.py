"""
This sub command sets the type configuration of the hook registered in your AWS account.
"""
import logging
import json
from argparse import Namespace

from botocore.exceptions import ClientError

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError

LOG = logging.getLogger(__name__)

COMMAND_NAME = "enable-lambda-invoker"


def _activate_lambda_invoker(cfn_client, execution_role_arn: str, alias: str) -> None:
    kwargs = {
        "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
        "Type": "HOOK",
        "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b"
    }
    if execution_role_arn:
        kwargs["ExecutionRoleArn"] = execution_role_arn
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
        type_configuration_json (string): The json formatted string to use as the Hook's TypeConfiguration

    Returns:
        None.

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

def _enable_lambda_invoker(args: Namespace) -> None:
    """
    Main method for the hook enable-lambda-invoker command. Uses file path specified to set the type configuration of the Hook in AWS.

    """
    cfn_client = create_sdk_session(args.region, args.profile).client("cloudformation", endpoint_url=args.endpoint_url)

    lambda_hook_arn = _activate_lambda_invoker(cfn_client, args.execution_role, args.alias)["Arn"]

    configuration_json = json.dumps({
        "CloudFormationConfiguration":{
            "HookConfiguration": {
                "FailureMode": args.failure_mode if args.failure_mode else "FAIL",
                "TargetStacks": "ALL",
                "Properties":{
                    "LambdaFunctions": [args.lambda_arn]
                }
            }
        }

    })

    set_type_config_response = _set_type_configuration(cfn_client, lambda_hook_arn, configuration_json)

def setup_parser(parser):
    enable_lambda_invoker_subparser = parser.add_parser(COMMAND_NAME, description=__doc__)
    enable_lambda_invoker_subparser.set_defaults(command=_enable_lambda_invoker)
    enable_lambda_invoker_subparser.add_argument("--lambda-arn", help="Lambda function ARN to use for the hook.", required=True)
    enable_lambda_invoker_subparser.add_argument("--failure-mode", help="Failure mode to configure for hook. Valid values: [WARN, FAIL]. Default is FAIL.")
    enable_lambda_invoker_subparser.add_argument("--execution-role", help="ARN of the IAM role to use for hook execution.")
    enable_lambda_invoker_subparser.add_argument("--alias", help="Alias to use for AWSSamples::LambdaFunctionInvoker::Hook")
    enable_lambda_invoker_subparser.add_argument("--profile", help="AWS profile to use.")
    enable_lambda_invoker_subparser.add_argument("--endpoint-url", help="CloudFormation endpoint to use.")
    enable_lambda_invoker_subparser.add_argument("--region", help="AWS Region to submit the type.")
