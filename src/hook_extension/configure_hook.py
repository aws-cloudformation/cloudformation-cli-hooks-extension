"""
This sub command sets the type configuration of the hook registered in your AWS account.
"""
import logging
from pathlib import Path
from argparse import Namespace

from botocore.exceptions import ClientError

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.project import Project
from rpdk.core.exceptions import DownstreamError, InvalidProjectError

LOG = logging.getLogger(__name__)

COMMAND_NAME = "configure"

def _set_type_configuration(cfn_client, type_name: str, type_configuration_json: str) -> None:
    """
    Sets Hook type configuration by calling CloudFormation SetTypeConfiguration API with arguments.
    https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_SetTypeConfiguration.html

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        type_name (string): The hook type name to call SetTypeConfiguration with.
        type_configuration_json (string): The json formatted string to use as the Hook's TypeConfiguration

    Returns:
        None.

    Side effect: Type configuration of hook will be updated in AWS account.
    """
    LOG.debug("Calling SetTypeConfiguration for %s", type_name)
    try:
        response = cfn_client.set_type_configuration(TypeName=type_name, Type="HOOK", Configuration=type_configuration_json)
        LOG.debug("Successful response from SetTypeConfiguration")
        return response
    except cfn_client.exceptions.TypeNotFoundException as e:
        msg = "Setting type configuration resulted in TypeNotFoundException. Have you registered this hook first?"
        print("\n" + msg)
        raise DownstreamError(msg) from e
    except ClientError as e:
        raise DownstreamError from e


def _configure_hook(args: Namespace) -> None:
    """
    Main method for the hook configure command. Uses file path specified to set the type configuration of the Hook in AWS.

    Parameters:
        args (Namespace): The arguments to use with this command.
            Required keys in Namespace: 'configuration_path', 'profile', 'endpoint_url', 'region'. All default to None.

    Returns:
        None.

    Side effect: Configuration Arn printed to system out.
    """
    cfn_client = create_sdk_session(args.region, args.profile).client("cloudformation", endpoint_url=args.endpoint_url)
    project = Project()
    project.load()
    type_name = project.type_name

    configuration_file_path = Path(args.configuration_path)

    try:
        configuration_file = open(configuration_file_path, 'r', encoding="utf-8")
    except FileNotFoundError as e:
        raise InvalidProjectError(f"Configuration file {configuration_file_path} not found.") from e

    with configuration_file:
        configuration_json = configuration_file.read()

    set_type_config_response = _set_type_configuration(cfn_client, type_name, configuration_json)
    print(f"ConfigurationArn: {set_type_config_response['ConfigurationArn']}")

def setup_parser(parser):
    configure_subparser = parser.add_parser(COMMAND_NAME, description=__doc__)
    configure_subparser.set_defaults(command=_configure_hook)
    configure_subparser.add_argument("--configuration-path", help="Filepath to CloudFormation configuration json to use for the hook.", required=True)
    configure_subparser.add_argument("--profile", help="AWS profile to use.")
    configure_subparser.add_argument("--endpoint-url", help="CloudFormation endpoint to use.")
    configure_subparser.add_argument("--region", help="AWS Region to submit the type.")
