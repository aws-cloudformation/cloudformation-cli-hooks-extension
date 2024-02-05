import logging

from rpdk.core.plugin_base import ExtensionPlugin

from describe_hook import setup_parser as setup_describe_parser
from configure_hook import setup_parser as setup_configure_parser
from set_default_hook_version import setup_parser as setup_set_default_version_parser

LOG = logging.getLogger(__name__)

HOOK_COMMAND_NAME = "hook"

DESCRIBE_COMMAND_NAME = "describe"
CONFIGURE_COMMAND_NAME = "configure"
SET_DEFAULT_VERSION_COMMAND_NAME = "set-default-version"


class HookExtension(ExtensionPlugin):
    """
    A class used for adding the 'hook' command to the CFN CLI.
    """
    COMMAND_NAME = HOOK_COMMAND_NAME

    def setup_parser(self, parser):
        hook_parser = parser.add_subparsers(title='hook subcommands',
                                   description='valid hook subcommands')

        describe_subparser = hook_parser.add_parser(DESCRIBE_COMMAND_NAME)
        setup_describe_parser(describe_subparser)

        configure_subparser = hook_parser.add_parser(CONFIGURE_COMMAND_NAME)
        setup_configure_parser(configure_subparser)

        set_default_hook_subparser = hook_parser.add_parser(SET_DEFAULT_VERSION_COMMAND_NAME)
        setup_set_default_version_parser(set_default_hook_subparser)
