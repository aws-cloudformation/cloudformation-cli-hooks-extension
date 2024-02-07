# pylint: disable=protected-access,redefined-outer-name
from unittest.mock import Mock, patch
from argparse import ArgumentParser
import pytest

from botocore.stub import Stubber

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError
from rpdk.core.project import Project
from rpdk.core.cli import main

from hook_extension.set_default_hook_version import setup_parser, _set_default_hook_version, _set_type_default_version

TEST_TYPE_NAME = "Random::Type::Name"

@pytest.fixture
def cfn_client():
    return create_sdk_session().client("cloudformation")

class TestEntryPoint:
    def test_command_available(self):
        patch_set_default_hook_version = patch(
            "hook_extension.set_default_hook_version._set_default_hook_version", autospec=True
        )
        with patch_set_default_hook_version as mock_set_default_hook_version:
            main(args_in=["hook", "set-default-version", "--version-id", "1"])

        mock_set_default_hook_version.assert_called_once()

    def test_command_without_required_args_fails(self):
        patch_set_default_hook_version = patch(
            "hook_extension.set_default_hook_version._set_default_hook_version", autospec=True
        )
        with patch_set_default_hook_version, pytest.raises(SystemExit):
            main(args_in=["hook", "set-default-version"])

@pytest.mark.parametrize(
        "args_in, expected",
        [
            (["--version-id", "1"], {"region": None, "profile": None, "endpoint_url": None, "version_id": "1"}),
            (["--region", "us-west-2", "--version-id", "2"], {"region": "us-west-2", "profile": None, "endpoint_url": None, "version_id": "2"}),
            (["--profile", "sandbox", "--version-id", "3"], {"region": None, "profile": "sandbox", "endpoint_url": None, "version_id": "3"}),
            (["--endpoint-url", "https://my_endpoint.my_domain",  "--version-id", "4"],
                {"region": None, "profile": None, "endpoint_url": "https://my_endpoint.my_domain","version_id": "4"}),
            (["--region", "us-west-2", "--profile", "sandbox", "--version-id", "5"],
                {"region": "us-west-2", "profile": "sandbox", "endpoint_url": None, "version_id": "5"}),
            (["--region", "us-west-2", "--profile", "sandbox", "--endpoint-url", "https://my_endpoint.my_domain", "--version-id", "6"],
                {"region": "us-west-2", "profile": "sandbox", "endpoint_url": "https://my_endpoint.my_domain", "version_id": "6"})
        ]
    )
class TestCommandLineArguments:
    def test_parser(self, args_in, expected):
        hook_parser = ArgumentParser()
        setup_parser(hook_parser.add_subparsers())
        parsed = hook_parser.parse_args(["set-default-version"] + args_in)
        assert parsed.region == expected["region"]
        assert parsed.profile == expected["profile"]
        assert parsed.endpoint_url == expected["endpoint_url"]
        assert parsed.version_id == expected["version_id"]

    def test_args_passed(self, args_in, expected):
        patch_set_default_hook_version = patch(
            "hook_extension.set_default_hook_version._set_default_hook_version", autospec=True
        )
        with patch_set_default_hook_version as mock_set_default_hook_version:
            main(args_in=["hook", "set-default-version"] + args_in)
        mock_set_default_hook_version.assert_called_once()
        argparse_namespace = mock_set_default_hook_version.call_args.args[0]
        assert argparse_namespace.region == expected["region"]
        assert argparse_namespace.profile == expected["profile"]
        assert argparse_namespace.endpoint_url == expected["endpoint_url"]
        assert argparse_namespace.version_id == expected["version_id"]

class TestSetTypeDefaultVersion:
    def test_set_type_default_version_happy(self, cfn_client):
        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "set_type_default_version",
                {},
                { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000001" }
            )
            _set_type_default_version(cfn_client, TEST_TYPE_NAME, "00000001")

    def test_set_type_default_version_type_not_found(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_default_version",
                service_error_code="TypeNotFoundException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00001234" }
            )
            _set_type_default_version(cfn_client, TEST_TYPE_NAME, "00001234")
        assert e.type == DownstreamError

    def test_set_type_default_version_client_error(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_default_version",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "98765432" }
            )
            _set_type_default_version(cfn_client, TEST_TYPE_NAME, "98765432")
        assert e.type == DownstreamError

class TestSetDefaultHookVersion:
    def test_set_default_hook_version_happy(self, capsys, cfn_client):
        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME
        patch_project = patch(
            "hook_extension.set_default_hook_version.Project", autospec=True, return_value=mock_project
        )

        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "version_id"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.version_id="564"

        patch_sdk = patch("boto3.session.Session.client", autospec=True, return_value = cfn_client)

        with patch_project, patch_sdk:
            with Stubber(cfn_client) as stubber:
                stubber.add_response(
                    "set_type_default_version",
                    {},
                    { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000564" }
                )
                _set_default_hook_version(args)

        out, _ = capsys.readouterr()

        assert out == ""
