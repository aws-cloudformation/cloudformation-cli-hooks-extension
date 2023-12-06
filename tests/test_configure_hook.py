# pylint: disable=protected-access,redefined-outer-name
import json
from datetime import datetime
from unittest.mock import Mock, patch
from argparse import ArgumentParser
from dateutil.tz import tzutc
import pytest

from pathlib import Path

from botocore.exceptions import ClientError
from botocore.stub import Stubber

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError, InvalidProjectError
from rpdk.core.project import Project
from rpdk.core.cli import main

from hooks_extension.configure_hook import ConfigureHookExtension

TEST_TYPE_NAME = "Random::Type::Name"

@pytest.fixture
def extension():
    configure_hook_extension = ConfigureHookExtension()
    configure_hook_extension._cfn_client = create_sdk_session().client("cloudformation")
    return configure_hook_extension

class TestEntryPoint:
    def test_command_available(self):
        patch_configure_hook = patch(
            "hooks_extension.configure_hook.ConfigureHookExtension._configure_hook", autospec=True
        )
        with patch_configure_hook as mock_configure_hook:
            main(args_in=["configure-hook", "--configuration-path", "/my/config/path"])

        mock_configure_hook.assert_called_once()

    def test_command_without_required_args_fails(self):
        patch_configure_hook = patch(
            "hooks_extension.configure_hook.ConfigureHookExtension._configure_hook", autospec=True
        )
        with patch_configure_hook, pytest.raises(SystemExit):
            main(args_in=["configure-hook"])


@pytest.mark.parametrize(
        "args_in, expected",
        [
            (["--region", "us-west-2", "--configuration-path", "/my/config/path"], {"region": "us-west-2", "profile": None, "endpoint_url": None, "configuration_path": "/my/config/path"}),
            (["--profile", "sandbox", "--configuration-path", "/another/diff/path"], {"region": None, "profile": "sandbox", "endpoint_url": None, "configuration_path": "/another/diff/path"}),
            (["--endpoint-url", "https://my_endpoint.my_domain", "--configuration-path", "/my/config/path"],
                {"region": None, "profile": None, "endpoint_url": "https://my_endpoint.my_domain", "configuration_path": "/my/config/path"}),
            (["--configuration-path", "another/new/path"], {"region": None, "profile": None, "endpoint_url": None, "configuration_path": "another/new/path"}),
            (["--region", "us-west-2", "--profile", "sandbox", "--configuration-path", "/path/here"], {"region": "us-west-2", "profile": "sandbox", "endpoint_url": None, "configuration_path": "/path/here"}),
            (["--region", "us-west-2", "--profile", "sandbox", "--endpoint-url", "https://my_endpoint.my_domain", "--configuration-path", "/my/config/path"],
                {"region": "us-west-2", "profile": "sandbox", "endpoint_url": "https://my_endpoint.my_domain", "configuration_path": "/my/config/path"})
        ]
    )
class TestCommandLineArguments:
    def test_parser(self, extension, args_in, expected):
        base_parser = ArgumentParser()
        extension.setup_parser(base_parser)
        parsed = base_parser.parse_args(args_in)
        assert parsed.region == expected["region"]
        assert parsed.profile == expected["profile"]
        assert parsed.endpoint_url == expected["endpoint_url"]
        assert parsed.configuration_path == expected["configuration_path"]

    def test_args_passed(self, args_in, expected):
        patch_configure_hook = patch(
            "hooks_extension.configure_hook.ConfigureHookExtension._configure_hook", autospec=True
        )
        with patch_configure_hook as mock_configure_hook:
            main(args_in=["configure-hook"] + args_in)
        mock_configure_hook.assert_called_once()
        argparse_namespace = mock_configure_hook.call_args.args[1]
        assert argparse_namespace.region == expected["region"]
        assert argparse_namespace.profile == expected["profile"]
        assert argparse_namespace.endpoint_url == expected["endpoint_url"]
        assert argparse_namespace.configuration_path == expected["configuration_path"]

class TestSetTypeConfiguration:
    def test_set_type_configuration_happy(self, extension):
        response = ({
            "ConfigurationArn": "TestArn"
        })
        with Stubber(extension._cfn_client) as stubber:
            stubber.add_response(
                "set_type_configuration",
                response,
                { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": "TestConfiguration" }
            )
            output = extension._set_type_configuration(TEST_TYPE_NAME, "TestConfiguration")
        assert output == response

    def test_set_type_configuration_type_not_found(self, extension):
        with Stubber(extension._cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_configuration",
                service_error_code="TypeNotFoundException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": "TestConfiguration" }
            )
            extension._set_type_configuration(TEST_TYPE_NAME, "TestConfiguration")
        assert e.type == DownstreamError

    def test_set_type_configuration_client_error(self, extension):
        with Stubber(extension._cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_configuration",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": "TestConfiguration" }
            )
            extension._set_type_configuration(TEST_TYPE_NAME, "TestConfiguration")
        assert e.type == DownstreamError

class TestConfigureHook:
    def test_configure_hook_happy(self, extension, capsys):
        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME
        patch_project = patch(
            "hooks_extension.configure_hook.Project", autospec=True, return_value=mock_project
        )

        response = ({
            "ConfigurationArn": "TestArn"
        })

        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "configuration_path"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.configuration_path= Path(__file__).resolve().parent / "test_data" / "test_configuration.json"

        with patch_project:
            with Stubber(extension._cfn_client) as stubber:
                with open(args.configuration_path) as f:
                    test_configuration = f.read()
                    stubber.add_response(
                        "set_type_configuration",
                        response,
                        { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": test_configuration }
                    )
                    extension._configure_hook(args)

        out, _ = capsys.readouterr()

        expected = "ConfigurationArn: TestArn\n"

        assert out == expected


    def test_configure_hook_no_file(self, extension, capsys):
        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME
        patch_project = patch(
            "hooks_extension.configure_hook.Project", autospec=True, return_value=mock_project
        )

        response = ({
            "ConfigurationArn": "TestArn"
        })

        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "configuration_path"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.configuration_path= "random_nonexistent_path.json"

        with patch_project, pytest.raises(Exception) as e:
            extension._configure_hook(args)

        assert e.type == InvalidProjectError