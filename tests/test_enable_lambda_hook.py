# pylint: disable=protected-access,redefined-outer-name
import os
import json
from unittest.mock import Mock, patch
from argparse import ArgumentParser
import pytest

from botocore.stub import Stubber

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError, SysExitRecommendedError
from rpdk.core.cli import main

from hook_extension.enable_lambda_hook import (
    setup_parser,
    _activate_lambda_function_invoker,
    _set_type_configuration,
    _enable_lambda_function_invoker,
    _build_configuration_json_string
)

DUMMY_LAMBDA_ARN = "arn:aws:lambda:us-east-2:123456789012:function:my-function:1"
DUMMY_EXECUTION_ROLE_ARN = "arn:aws:iam::123456789012:role/my-role"

@pytest.fixture
def cfn_client():
    return create_sdk_session().client("cloudformation")

class TestEntryPoint:
    def test_command_available(self):
        patch_enable_lambda_function_invoker_hook = patch(
            "hook_extension.enable_lambda_hook._enable_lambda_function_invoker", autospec=True
        )
        with patch_enable_lambda_function_invoker_hook as mock_configure_hook:
            main(args_in=["hook", "enable-lambda-function-invoker", "--lambda-function-arn",
                          DUMMY_LAMBDA_ARN, "--execution-role-arn", DUMMY_EXECUTION_ROLE_ARN])

        mock_configure_hook.assert_called_once()

    def test_command_without_required_args_fails(self):
        patch_enable_lambda_function_invoker_hook = patch(
            "hook_extension.enable_lambda_hook._enable_lambda_function_invoker", autospec=True
        )
        with patch_enable_lambda_function_invoker_hook, pytest.raises(SystemExit):
            main(args_in=["hook", "enable-lambda-function-invoker"])


@pytest.mark.parametrize("region", [None, "us-west-2", "ca-west-1"])
@pytest.mark.parametrize("profile", [None, "sandbox"])
@pytest.mark.parametrize("endpoint_url", [None, "https://my_endpoint.my_domain"])
@pytest.mark.parametrize("lambda_function_arn", [DUMMY_LAMBDA_ARN, "AnotherDummyLambdaArn"])
@pytest.mark.parametrize("execution_role_arn", [DUMMY_EXECUTION_ROLE_ARN, "AnotherDummyExecutionRoleArn"])
@pytest.mark.parametrize("alias", [None, "MyCompany::MyOrganization::Hook"])
@pytest.mark.parametrize("failure_mode", ["WARN", "FAIL"])
@pytest.mark.parametrize("include_targets", [None, "AWS::*::*", "AWS::S3::*,AWS::*::Table"])
class TestCommandLineArguments:
    def test_parser(self, region, profile, endpoint_url, lambda_function_arn, execution_role_arn, alias, failure_mode, include_targets): # pylint: disable=too-many-arguments
        hook_parser = ArgumentParser()
        setup_parser(hook_parser.add_subparsers())

        args_in = []
        for arg_name in ["region", "profile", "endpoint_url", "lambda_function_arn", "execution_role_arn", "alias", "failure_mode", "include_targets"]:
            arg_value = locals()[arg_name]
            if arg_value is not None:
                args_in.append("--" + arg_name.replace("_", "-"))
                args_in.append(arg_value)

        parsed = hook_parser.parse_args(["enable-lambda-function-invoker"] + args_in)
        assert parsed.region == region
        assert parsed.profile == profile
        assert parsed.endpoint_url == endpoint_url
        assert parsed.lambda_function_arn == lambda_function_arn
        assert parsed.execution_role_arn == execution_role_arn
        assert parsed.alias == alias
        assert parsed.include_targets == include_targets
        assert parsed.failure_mode == failure_mode

    def test_args_passed(self, region, profile, endpoint_url, lambda_function_arn, execution_role_arn, alias, failure_mode, include_targets): # pylint: disable=too-many-arguments
        args_in = []
        for arg_name in ["region", "profile", "endpoint_url", "lambda_function_arn", "execution_role_arn", "alias", "failure_mode", "include_targets"]:
            arg_value = locals()[arg_name]
            if arg_value is not None:
                args_in.append("--" + arg_name.replace("_", "-"))
                args_in.append(arg_value)

        patch_enable_lambda_function_invoker = patch(
            "hook_extension.enable_lambda_hook._enable_lambda_function_invoker", autospec=True
        )

        with patch_enable_lambda_function_invoker as mock_enable_lambda_function_invoker:
            main(args_in=["hook", "enable-lambda-function-invoker"] + args_in)
        mock_enable_lambda_function_invoker.assert_called_once()
        argparse_namespace = mock_enable_lambda_function_invoker.call_args.args[0]
        assert argparse_namespace.region == region
        assert argparse_namespace.profile == profile
        assert argparse_namespace.endpoint_url == endpoint_url
        assert argparse_namespace.lambda_function_arn == lambda_function_arn
        assert argparse_namespace.execution_role_arn == execution_role_arn
        assert argparse_namespace.alias == alias
        assert argparse_namespace.include_targets == include_targets
        assert argparse_namespace.failure_mode == failure_mode

class TestSetTypeConfiguration:
    def test_set_type_configuration_happy(self, cfn_client):
        response = ({
            "ConfigurationArn": "TestArn"
        })

        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "set_type_configuration",
                response,
                { "TypeArn": "TestTypeArn", "Configuration": "TestConfiguration" }
            )
            output = _set_type_configuration(cfn_client, "TestTypeArn", "TestConfiguration")
        assert output == response

    def test_set_type_configuration_type_not_found(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_configuration",
                service_error_code="TypeNotFoundException",
                expected_params={ "TypeArn": "TestTypeArn", "Configuration": "TestConfiguration" }
            )
            _set_type_configuration(cfn_client, "TestTypeArn", "TestConfiguration")
        assert e.type == DownstreamError

    def test_set_type_configuration_client_error(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "set_type_configuration",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeArn": "TestTypeArn", "Configuration": "TestConfiguration" }
            )
            _set_type_configuration(cfn_client, "TestTypeArn", "TestConfiguration")
        assert e.type == DownstreamError

@pytest.mark.parametrize(
        "execution_role_arn, alias",
        [(DUMMY_EXECUTION_ROLE_ARN, None), (DUMMY_EXECUTION_ROLE_ARN, "Test::MyAlias::Hook")]
    )
class TestActivateLambdaInvoker:
    def test_activate_type_happy(self, cfn_client, execution_role_arn, alias):
        response = ({
            "Arn": "arn:aws:cloudformation:us-west-2:123456789012:type/resource/Example-Test-Alias"
        })

        expected_params = {
            "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
            "Type": "HOOK",
            "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b",
            "ExecutionRoleArn": execution_role_arn
        }
        if alias:
            expected_params["TypeNameAlias"] =  alias

        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "activate_type",
                response,
                expected_params
            )
            output = _activate_lambda_function_invoker(cfn_client, execution_role_arn, alias)
        assert output == response

    def test_activate_type_type_not_found(self, cfn_client, execution_role_arn, alias):
        expected_params = {
            "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
            "Type": "HOOK",
            "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b",
            "ExecutionRoleArn": execution_role_arn
        }
        if alias:
            expected_params["TypeNameAlias"] =  alias

        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "activate_type",
                service_error_code="TypeNotFoundException",
                expected_params=expected_params
            )
            _activate_lambda_function_invoker(cfn_client, execution_role_arn, alias)
        assert e.type == DownstreamError

    def test_activate_type_client_error(self, cfn_client, execution_role_arn, alias):
        expected_params = {
            "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
            "Type": "HOOK",
            "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b",
            "ExecutionRoleArn": execution_role_arn
        }
        if alias:
            expected_params["TypeNameAlias"] =  alias

        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "activate_type",
                service_error_code="CFNRegistryException",
                expected_params=expected_params
            )
            _activate_lambda_function_invoker(cfn_client, execution_role_arn, alias)
        assert e.type == DownstreamError

class TestBuildConfigurationJsonString:
    @pytest.mark.parametrize("lambda_function_arn", [DUMMY_LAMBDA_ARN, "AnotherLambdaArn"])
    @pytest.mark.parametrize("failure_mode", ["WARN", "FAIL"])
    def test_build_configuration_json_string_no_include_targets(self, lambda_function_arn, failure_mode):
        configuration_string = _build_configuration_json_string(lambda_function_arn, failure_mode, None)
        configuration_object = json.loads(configuration_string)

        assert "TargetFilters" not in configuration_object
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["FailureMode"] == failure_mode
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["TargetStacks"] == "ALL"
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["Properties"]["LambdaFunctions"] == [lambda_function_arn]

    @pytest.mark.parametrize("lambda_function_arn", [DUMMY_LAMBDA_ARN, "AnotherLambdaArn"])
    @pytest.mark.parametrize("failure_mode", ["WARN", "FAIL"])
    @pytest.mark.parametrize("include_targets, expected_targets",
                             [("AWS::S3::Bucket", ["AWS::S3::Bucket"]), ("AWS::Cloud*::*,AWS::DynamoDB::Table", ["AWS::Cloud*::*", "AWS::DynamoDB::Table"])])
    def test_build_configuration_json_string_with_include_targets(self, lambda_function_arn, failure_mode, include_targets, expected_targets):
        configuration_string = _build_configuration_json_string(lambda_function_arn, failure_mode, include_targets)
        configuration_object = json.loads(configuration_string)

        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["FailureMode"] == failure_mode
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["TargetStacks"] == "ALL"
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["Properties"]["LambdaFunctions"] == [lambda_function_arn]
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["TargetFilters"]["Actions"] == ["CREATE", "UPDATE"]
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["TargetFilters"]["InvocationPoints"] == ["PRE_PROVISION"]
        assert configuration_object["CloudFormationConfiguration"]["HookConfiguration"]["TargetFilters"]["TargetNames"] == expected_targets


class TestEnableLambdaInvoker:
    def test_enable_lambda_function_invoker_no_experimental_flag(self):
        os.environ["CFN_CLI_HOOKS_EXPERIMENTAL"] = ""

        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "lambda_function_arn",
                "failure_mode",
                "execution_role_arn",
                "alias",
                "include_targets"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.lambda_function_arn=DUMMY_LAMBDA_ARN
        args.failure_mode=None
        args.execution_role_arn=DUMMY_EXECUTION_ROLE_ARN
        args.alias=None
        args.include_targets=None

        with pytest.raises(Exception) as e:
            _enable_lambda_function_invoker(args)

        assert e.type == SysExitRecommendedError

    @pytest.mark.parametrize("input_value", ["n", "N", "", "adsfas", "1"])
    def test_enable_lambda_function_invoker_no_include_targets_abort(self, input_value):
        os.environ["CFN_CLI_HOOKS_EXPERIMENTAL"] = "enabled"
        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "lambda_function_arn",
                "failure_mode",
                "execution_role_arn",
                "alias",
                "include_targets"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.lambda_function_arn=DUMMY_LAMBDA_ARN
        args.failure_mode=None
        args.execution_role_arn=DUMMY_EXECUTION_ROLE_ARN
        args.alias=None
        args.include_targets=None

        patch_input = patch("builtins.input", return_value=input_value)
        with patch_input, pytest.raises(Exception) as e:
            _enable_lambda_function_invoker(args)

        assert e.type == SysExitRecommendedError

    @pytest.mark.parametrize("input_value", ["y", "Y"])
    def test_enable_lambda_function_invoker_no_include_targets_continue(self, capsys, cfn_client, input_value):
        os.environ["CFN_CLI_HOOKS_EXPERIMENTAL"] = "enabled"
        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "lambda_function_arn",
                "failure_mode",
                "execution_role_arn",
                "alias",
                "include_targets"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.lambda_function_arn=DUMMY_LAMBDA_ARN
        args.failure_mode=None
        args.execution_role_arn=DUMMY_EXECUTION_ROLE_ARN
        args.alias=None
        args.include_targets=None

        patch_sdk = patch("boto3.session.Session.client", autospec=True, return_value = cfn_client)
        patch_input = patch("builtins.input", return_value=input_value)
        with patch_sdk, patch_input:
            with Stubber(cfn_client) as stubber:
                stubber.add_response(
                    "activate_type",
                    { "Arn": "DummyTypeArn" },
                    {
                        "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
                        "Type": "HOOK",
                        "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b",
                        "ExecutionRoleArn": DUMMY_EXECUTION_ROLE_ARN
                    }
                )
                stubber.add_response(
                    "set_type_configuration",
                    { "ConfigurationArn": "TestArn" },
                    { "TypeArn": "DummyTypeArn",
                     "Configuration": json.dumps(
                         {
                             "CloudFormationConfiguration":{
                                    "HookConfiguration": {
                                        "FailureMode": "FAIL",
                                        "TargetStacks": "ALL",
                                        "Properties":{
                                            "LambdaFunctions": [DUMMY_LAMBDA_ARN]
                                        }
                                    }
                                }
                         }
                     ) }

                )
                _enable_lambda_function_invoker(args)

        out, _ = capsys.readouterr()

        expected = "Success: AWSSamples::LambdaFunctionInvoker::Hook will now be invoked for CloudFormation deployments for ALL resources in FAIL mode.\n"

        assert out == expected

    def test_enable_lambda_invoker_basic_happy_path(self, capsys, cfn_client):
        os.environ["CFN_CLI_HOOKS_EXPERIMENTAL"] = "enabled"
        args = Mock(
            spec_set=[
                "region",
                "profile",
                "endpoint_url",
                "lambda_function_arn",
                "failure_mode",
                "execution_role_arn",
                "alias",
                "include_targets"
            ]
        )
        args.region=None
        args.profile=None
        args.endpoint_url=None
        args.lambda_function_arn=DUMMY_LAMBDA_ARN
        args.failure_mode=None
        args.execution_role_arn=DUMMY_EXECUTION_ROLE_ARN
        args.alias=None
        args.include_targets="AWS::SQS::Queue,AWS::Cloud*::*"

        patch_sdk = patch("boto3.session.Session.client", autospec=True, return_value = cfn_client)
        with patch_sdk:
            with Stubber(cfn_client) as stubber:
                stubber.add_response(
                    "activate_type",
                    { "Arn": "DummyTypeArn" },
                    {
                        "TypeName": "AWSSamples::LambdaFunctionInvoker::Hook",
                        "Type": "HOOK",
                        "PublisherId": "096debcd443a84c983955f8f8476c221b2b08d8b",
                        "ExecutionRoleArn": DUMMY_EXECUTION_ROLE_ARN
                    }
                )
                stubber.add_response(
                    "set_type_configuration",
                    { "ConfigurationArn": "TestArn" },
                    { "TypeArn": "DummyTypeArn",
                     "Configuration": json.dumps(
                         {
                             "CloudFormationConfiguration":{
                                    "HookConfiguration": {
                                        "FailureMode": "FAIL",
                                        "TargetStacks": "ALL",
                                        "Properties":{
                                            "LambdaFunctions": [DUMMY_LAMBDA_ARN]
                                        },
                                        "TargetFilters": {
                                            "TargetNames": [
                                                "AWS::SQS::Queue",
                                                "AWS::Cloud*::*"
                                            ],
                                            "Actions": [
                                                "CREATE",
                                                "UPDATE"
                                            ],
                                            "InvocationPoints": [
                                                "PRE_PROVISION"
                                            ]
                                        }
                                    }
                                }
                         }
                     ) }

                )
                _enable_lambda_function_invoker(args)

        out, _ = capsys.readouterr()
        expected = "Success: AWSSamples::LambdaFunctionInvoker::Hook will now be invoked for CloudFormation deployments for " \
                        "AWS::SQS::Queue,AWS::Cloud*::* resources in FAIL mode.\n"

        assert out == expected
