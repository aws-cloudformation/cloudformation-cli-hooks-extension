# pylint: disable = no-name-in-module
"""This tool provides additional support for managing CloudFormation Resource Hooks.
"""
import logging

from rpdk.core.plugin_base import ExtensionPlugin

from .__init__ import __version__
from .describe_hook import setup_parser as setup_describe_parser
from .configure_hook import setup_parser as setup_configure_parser
from .set_default_hook_version import setup_parser as setup_set_default_version_parser

LOG = logging.getLogger(__name__)

HOOK_COMMAND_NAME = "hook"

class HookExtension(ExtensionPlugin):
    """
    A class used for adding the 'hook' command to the CFN CLI.
    """
    COMMAND_NAME = HOOK_COMMAND_NAME

    def setup_parser(self, parser):
        hook_parser = parser.add_subparsers(title='hook subcommands',
                                   description=__doc__)

        def no_command(args):
            if args.version:
                print("cloudformation-cli-hooks-extension", __version__)
            else:
                parser.print_help()

        parser.set_defaults(command=no_command)
        parser.add_argument(
            "--version",
            action="store_true",
            help="Show the executable version and exit.",
        )

        setup_describe_parser(hook_parser)
        setup_configure_parser(hook_parser)
        setup_set_default_version_parser(hook_parser)
