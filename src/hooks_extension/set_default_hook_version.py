import logging
from argparse import Namespace

from botocore.exceptions import ClientError

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.project import Project
from rpdk.core.exceptions import DownstreamError

LOG = logging.getLogger(__name__)

def _set_type_default_version(cfn_client, type_name: str, version_id: str) -> None:
    """
    Sets Hook default version by calling CloudFormation SetTypeDefaultVersion API with arguments.
    https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_SetTypeDefaultVersion.html

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        type_name (string): The hook type name to call SetTypeDefaultVersion with.
        version_id (string) - The desired default hook version id.

    Returns:
        None.

    Side effect: Hook default version will be updated in AWS account.
    """
    LOG.debug("Calling SetTypeDefaultVersion for %s version %s", type_name, version_id)
    try:
        cfn_client.set_type_default_version(Type="HOOK", TypeName=type_name, VersionId=version_id)
        LOG.debug("Successful response from SetTypeDefaultVersion")
    except cfn_client.exceptions.TypeNotFoundException as e:
        msg = "Trying to set type default version resulted in TypeNotFoundException. You may need to register the hook first using `cfn submit`."
        print("\n" + msg)
        raise DownstreamError(msg) from e
    except ClientError as e:
        raise DownstreamError from e

def _set_default_hook_version(args: Namespace) -> None:
    """
    Main method for the hook set-default-version command. Uses version id to set the default hook version in AWS.

    Parameters:
        args (Namespace): The arguments to use with this command.
            Required keys in Namespace: 'version_id', 'profile', 'endpoint_url', 'region'. All default to None.

    Returns:
        None.
    """
    cfn_client = create_sdk_session(args.region, args.profile).client("cloudformation", endpoint_url=args.endpoint_url)

    project = Project()
    project.load()
    type_name = project.type_name
    version_id = args.version_id.zfill(8)

    _set_type_default_version(cfn_client, type_name, version_id)

def setup_parser(parser):
    parser.set_defaults(command=_set_default_hook_version)
    parser.add_argument("--version-id", help="Version id to use as default.", required=True)
    parser.add_argument("--profile", help="AWS profile to use.")
    parser.add_argument("--endpoint-url", help="CloudFormation endpoint to use.")
    parser.add_argument("--region", help="AWS Region to submit the type.")
