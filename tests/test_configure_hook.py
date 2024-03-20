# pylint: disable=protected-access,redefined-outer-name
from unittest.mock import Mock, patch
from argparse import ArgumentParser
from pathlib import Path
import pytest

from botocore.stub import Stubber

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError, InvalidProjectError
from rpdk.core.project import Project
from rpdk.core.cli import main

from hook_extension.configure_hook import setup_parser, _configure_hook, _set_type_configuration

TEST_TYPE_NAME = "Random::Type::Name"

@pytest.fixture
def cfn_client():
    return create_sdk_session().client("cloudformation")

class TestEntryPoint:
    def test_command_available(self):
        patch_configure_hook = patch(
            "hook_extension.configure_hook._configure_hook", autospec=True
        )
        with patch_configure_hook as mock_configure_hook:
            main(args_in=["hook", "configure", "--configuration-path", "/my/config/path"])

        mock_configure_hook.assert_called_once()

    def test_command_without_required_args_fails(self):
        patch_configure_hook = patch(
            "hook_extension.configure_hook._configure_hook", autospec=True
        )
        with patch_configure_hook, pytest.raises(SystemExit):
            main(args_in=["hook", "configure"])

@pytest.mark.parametrize("region", [None, "us-west-2", "ca-west-1"])
@pytest.mark.parametrize("profile", [None, "sandbox"])
@pytest.mark.parametrize("endpoint_url", [None, "https://my_endpoint.my_domain"])
@pytest.mark.parametrize("configuration_path", ["/my/config/path", "another/new/path"])
class TestCommandLineArguments:
    def test_parser(self, region, profile, endpoint_url, configuration_path):
        hook_parser = ArgumentParser()
        setup_parser(hook_parser.add_subparsers())

        args_in = []
        for arg_name in ['region', 'profile', 'endpoint_url', 'configuration_path']:
            arg_value = locals()[arg_name]
            if arg_value is not None:
                args_in.append('--' + arg_name.replace('_', '-'))
                args_in.append(arg_value)

        parsed = hook_parser.parse_args(["configure"] + args_in)
        assert parsed.region == region
        assert parsed.profile == profile
        assert parsed.endpoint_url == endpoint_url
        assert parsed.configuration_path == configuration_path

    def test_args_passed(self, region, profile, endpoint_url, configuration_path):
        args_in = []
        for arg_name in ['region', 'profile', 'endpoint_url', 'configuration_path']:
            arg_value = locals()[arg_name]
            if arg_value is not None:
                args_in.append('--' + arg_name.replace('_', '-'))
                args_in.append(arg_value)

        patch_configure_hook = patch(
            "hook_extension.configure_hook._configure_hook", autospec=True
        )

        with patch_configure_hook as mock_configure_hook:
            main(args_in=["hook", "configure"] + args_in)
        mock_configure_hook.assert_called_once()
        argparse_namespace = mock_configure_hook.call_args.args[0]
        assert argparse_namespace.region == region
        assert argparse_namespace.profile == profile
        assert argparse_namespace.endpoint_url == endpoint_url
        assert argparse_namespace.configuration_path == configuration_path

class TestSetTypeConfiguration:
    def test_set_type_configuration_happy(self, cfn_client):
        response = ({
            "ConfigurationArn": "TestArn"
        })

        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "set_type_configuration",
                response,
                { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": "TestConfiguration" }
            )
            output = _set_type_configuration(cfn_client, TEST_TYPE_NAME, "TestConfiguration")
        assert output == response

    def test_set_type_configuration_type_not_found(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_configuration",
                service_error_code="TypeNotFoundException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": "TestConfiguration" }
            )
            _set_type_configuration(cfn_client, TEST_TYPE_NAME, "TestConfiguration")
        assert e.type == DownstreamError

    def test_set_type_configuration_client_error(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_configuration",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": "TestConfiguration" }
            )
            _set_type_configuration(cfn_client, TEST_TYPE_NAME, "TestConfiguration")
        assert e.type == DownstreamError

class TestConfigureHook:
    def test_configure_hook_happy(self, capsys, cfn_client):
        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME
        patch_project = patch(
            "hook_extension.configure_hook.Project", autospec=True, return_value=mock_project
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

        patch_sdk = patch("boto3.session.Session.client", autospec=True, return_value = cfn_client)

        with patch_project, patch_sdk:
            with Stubber(cfn_client) as stubber:
                with open(args.configuration_path, 'r', encoding="utf-8") as f:
                    test_configuration = f.read()
                    stubber.add_response(
                        "set_type_configuration",
                        response,
                        { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "Configuration": test_configuration }
                    )
                    _configure_hook(args)

        out, _ = capsys.readouterr()

        expected = "ConfigurationArn: TestArn\n"

        assert out == expected

    def test_configure_hook_no_file(self):
        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME
        patch_project = patch(
            "hook_extension.configure_hook.Project", autospec=True, return_value=mock_project
        )

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
            _configure_hook(args)

        assert e.type == InvalidProjectError
