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

from configure_hook import setup_parser, _configure_hook, _set_type_configuration

TEST_TYPE_NAME = "Random::Type::Name"

@pytest.fixture
def cfn_client():
    return create_sdk_session().client("cloudformation")

class TestEntryPoint:
    def test_command_available(self):
        patch_configure_hook = patch(
            "configure_hook._configure_hook", autospec=True
        )
        with patch_configure_hook as mock_configure_hook:
            main(args_in=["hook", "configure", "--configuration-path", "/my/config/path"])

        mock_configure_hook.assert_called_once()

    def test_command_without_required_args_fails(self):
        patch_configure_hook = patch(
            "configure_hook._configure_hook", autospec=True
        )
        with patch_configure_hook, pytest.raises(SystemExit):
            main(args_in=["hook", "configure"])


@pytest.mark.parametrize(
        "args_in, expected",
        [
            (["--region", "us-west-2", "--configuration-path", "/my/config/path"],
                {"region": "us-west-2", "profile": None, "endpoint_url": None, "configuration_path": "/my/config/path"}),
            (["--profile", "sandbox", "--configuration-path", "/another/diff/path"],
                {"region": None, "profile": "sandbox", "endpoint_url": None, "configuration_path": "/another/diff/path"}),
            (["--endpoint-url", "https://my_endpoint.my_domain", "--configuration-path", "/my/config/path"],
                {"region": None, "profile": None, "endpoint_url": "https://my_endpoint.my_domain", "configuration_path": "/my/config/path"}),
            (["--configuration-path", "another/new/path"], {"region": None, "profile": None, "endpoint_url": None, "configuration_path": "another/new/path"}),
            (["--region", "us-west-2", "--profile", "sandbox", "--configuration-path", "/path/here"],
                {"region": "us-west-2", "profile": "sandbox", "endpoint_url": None, "configuration_path": "/path/here"}),
            (["--region", "us-west-2", "--profile", "sandbox", "--endpoint-url", "https://my_endpoint.my_domain", "--configuration-path", "/my/config/path"],
                {"region": "us-west-2", "profile": "sandbox", "endpoint_url": "https://my_endpoint.my_domain", "configuration_path": "/my/config/path"})
        ]
    )
class TestCommandLineArguments:
    def test_parser(self, args_in, expected):
        base_parser = ArgumentParser()
        setup_parser(base_parser)
        parsed = base_parser.parse_args(args_in)
        assert parsed.region == expected["region"]
        assert parsed.profile == expected["profile"]
        assert parsed.endpoint_url == expected["endpoint_url"]
        assert parsed.configuration_path == expected["configuration_path"]

    def test_args_passed(self, args_in, expected):
        patch_configure_hook = patch(
            "configure_hook._configure_hook", autospec=True
        )

        with patch_configure_hook as mock_configure_hook:
            main(args_in=["hook", "configure"] + args_in)
        mock_configure_hook.assert_called_once()
        argparse_namespace = mock_configure_hook.call_args.args[0]
        assert argparse_namespace.region == expected["region"]
        assert argparse_namespace.profile == expected["profile"]
        assert argparse_namespace.endpoint_url == expected["endpoint_url"]
        assert argparse_namespace.configuration_path == expected["configuration_path"]

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
            "configure_hook.Project", autospec=True, return_value=mock_project
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
            "configure_hook.Project", autospec=True, return_value=mock_project
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
