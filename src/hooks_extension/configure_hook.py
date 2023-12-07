import logging
from pathlib import Path
from argparse import Namespace

from botocore.exceptions import ClientError

from rpdk.core.plugin_base import ExtensionPlugin
from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.project import Project
from rpdk.core.exceptions import DownstreamError, InvalidProjectError

LOG = logging.getLogger(__name__)

CONFIGURE_HOOK_COMMAND_NAME = "configure-hook"


class ConfigureHookExtension(ExtensionPlugin):
    """
    A class used for adding the 'configure-hook' command to the CFN CLI.
    """
    COMMAND_NAME = CONFIGURE_HOOK_COMMAND_NAME

    _cfn_client = None

    def _set_type_configuration(self, type_name: str, type_configuration_json: str) -> None:
        """
        Sets Hook type configuration by calling CloudFormation SetTypeConfiguration API with arguments.
        https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_SetTypeConfiguration.html

        Parameters:
            type_name (string): The hook type name to call SetTypeConfiguration with.
            type_configuration_json (string) - The json formatted string to use as the Hook's TypeConfiguration

        Returns:
            None.

        Side effect: Type configuration of hook will be updated in AWS account.
        """
        LOG.debug("Calling SetTypeConfiguration for %s", type_name)
        try:
            response = self._cfn_client.set_type_configuration(TypeName=type_name, Type="HOOK", Configuration=type_configuration_json)
            LOG.debug("Successful response from SetTypeConfiguration")
            return response
        except self._cfn_client.exceptions.TypeNotFoundException as e:
            msg = "Describing type resulted in TypeNotFoundException. Have you registered this hook?"
            raise DownstreamError(msg) from e
        except ClientError as e:
            raise DownstreamError from e


    def _configure_hook(self, args: Namespace) -> None:
        """
        Main method for the configure-hook command. Uses file path specified to set the type configuration of the Hook in AWS.

        Parameters:
            args (Namespace): The arguments to use with this command.
                Required keys in Namespace: 'configuration_path', 'profile', 'endpoint_url', 'region'. All default to None.

        Returns:
            None.

        Side effect: Configuration Arn printed to system out.
        """
        ConfigureHookExtension._cfn_client = create_sdk_session(args.region, args.profile).client("cloudformation", endpoint_url=args.endpoint_url)
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

        set_type_config_response = self._set_type_configuration(type_name, configuration_json)
        print(f"ConfigurationArn: {set_type_config_response['ConfigurationArn']}")

    def setup_parser(self, parser):
        parser.set_defaults(command=self._configure_hook)
        parser.add_argument("--configuration-path", help="Filepath to CloudFormation configuration json to use for the type.", required=True)
        parser.add_argument("--profile", help="AWS profile to use.")
        parser.add_argument("--endpoint-url", help="CloudFormation endpoint to use.")
        parser.add_argument("--region", help="AWS Region to submit the type.")
