# pylint: disable=protected-access,redefined-outer-name,too-many-lines
import json
from datetime import datetime
from unittest.mock import Mock, patch
from argparse import ArgumentParser
from dateutil.tz import tzutc
import pytest

from botocore.stub import Stubber

from rpdk.core.boto_helpers import create_sdk_session
from rpdk.core.exceptions import DownstreamError, InternalError
from rpdk.core.project import Project
from rpdk.core.cli import main

from hooks_extension.describe_hook import (
    _build_properties_string,
    _build_stack_filters_string,
    _build_target_handlers_string,
    _describe_hook,
    _get_hook_data,
    _get_type_configuration_data,
    _matches_filters,
    setup_parser,

)

TEST_TYPE_NAME = "Random::Type::Name"

@pytest.fixture
def cfn_client():
    return create_sdk_session().client("cloudformation")

class TestEntryPoint:
    def test_command_available(self):
        patch_describe_hook = patch(
            "hooks_extension.describe_hook._describe_hook", autospec=True
        )
        with patch_describe_hook as mock_describe_hook:
            main(args_in=["hook", "describe"])

        mock_describe_hook.assert_called_once()

@pytest.mark.parametrize(
        "args_in, expected",
        [
            ([], {"region": None, "profile": None, "endpoint_url": None, "version_id": None}),
            (["--region", "us-west-2"], {"region": "us-west-2", "profile": None, "endpoint_url": None, "version_id": None}),
            (["--profile", "sandbox"], {"region": None, "profile": "sandbox", "endpoint_url": None, "version_id": None}),
            (["--endpoint-url", "https://my_endpoint.my_domain"],
                {"region": None, "profile": None, "endpoint_url": "https://my_endpoint.my_domain", "version_id": None}),
            (["--version-id", "4"], {"region": None, "profile": None, "endpoint_url": None, "version_id": "4"}),
            (["--region", "us-west-2", "--profile", "sandbox"], {"region": "us-west-2", "profile": "sandbox", "endpoint_url": None, "version_id": None}),
            (["--region", "us-west-2", "--profile", "sandbox", "--endpoint-url", "https://my_endpoint.my_domain", "--version-id", "4"],
                {"region": "us-west-2", "profile": "sandbox", "endpoint_url": "https://my_endpoint.my_domain", "version_id": "4"})
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
        assert parsed.version_id == expected["version_id"]

    def test_args_passed(self, args_in, expected):
        patch_describe_hook = patch(
            "hooks_extension.describe_hook._describe_hook", autospec=True
        )
        with patch_describe_hook as mock_describe_hook:
            main(args_in=["hook", "describe"] + args_in)
        mock_describe_hook.assert_called_once()
        argparse_namespace = mock_describe_hook.call_args.args[0]
        assert argparse_namespace.region == expected["region"]
        assert argparse_namespace.profile == expected["profile"]
        assert argparse_namespace.endpoint_url == expected["endpoint_url"]
        assert argparse_namespace.version_id == expected["version_id"]

class TestBuildPropertiesString:
    def test_no_properties(self):
        output = _build_properties_string({})
        assert output == "No configured properties."

    def test_one_property(self):
        sample_hook_configuration_data = {}
        sample_hook_configuration_data["Properties"] = {"MinQueues": "1"}
        output = _build_properties_string(sample_hook_configuration_data)
        expected = ("Configured properties:\n"
        "\t\tProperty   | Value\n"
        "\t\t---------------------\n"
        "\t\tMinQueues  | 1")
        assert output == expected

    def test_multiple_properties(self):
        sample_hook_configuration_data = {}
        sample_hook_configuration_data["Properties"] = {"MinQueues": "1", "MaxKeys": "5"}
        output = _build_properties_string(sample_hook_configuration_data)
        expected = ("Configured properties:\n"
        "\t\tProperty   | Value\n"
        "\t\t---------------------\n"
        "\t\tMinQueues  | 1\n"
        "\t\tMaxKeys    | 5")
        assert output == expected

    def test_multiple_properties_mixed_types(self):
        sample_hook_configuration_data = {}
        sample_hook_configuration_data["Properties"] = {"NestedProperties": "['String1', 'String2', 'String3']", "MaxKeys": "5"}
        output = _build_properties_string(sample_hook_configuration_data)
        expected = ("Configured properties:\n"
        "\t\tProperty          | Value\n"
        "\t\t----------------------------\n"
        "\t\tNestedProperties  | ['String1', 'String2', 'String3']\n"
        "\t\tMaxKeys           | 5")
        assert output == expected

class TestBuildStackFiltersString:
    def test_build_stack_filters_string_no_filter(self):
        output = _build_stack_filters_string({})
        assert output == ""

    def test_build_stack_filters_string_one_filter(self):
        sample_hook_configuration_data = {}
        sample_hook_configuration_data["StackFilters"] = {
            "FilteringCriteria": "ANY",
            "StackRoles": {
                "Exclude": [
                    "stack-role-0",
                    "stack-role-1",
                    "stack-role-2"
                ]
            }
        }
        output = _build_stack_filters_string(sample_hook_configuration_data)
        expected = ("\t\tStack Filters:\n"
        "\t\t\tFiltering Criteria: ANY\n"
        "\t\t\tStackRoles:\n"
        "\t\t\t\tExclude: ['stack-role-0', 'stack-role-1', 'stack-role-2']\n")
        assert output == expected

    def test_build_stack_filters_string_multiple_filters(self):
        sample_hook_configuration_data = {}
        sample_hook_configuration_data["StackFilters"] = {
            "FilteringCriteria": "ANY",
            "StackNames": {
                "Include": [
                    "stack-name-0",
                    "stack-name-1",
                    "stack-name-2"
                ],
                "Exclude": [
                    "stack-name-3",
                    "stack-name-4",
                    "stack-name-5"
                ]
            },
            "StackRoles": {
                "Exclude": [
                    "stack-role-0",
                    "stack-role-1",
                    "stack-role-2"
                ]
            }
        }
        output = _build_stack_filters_string(sample_hook_configuration_data)
        expected = ("\t\tStack Filters:\n"
        "\t\t\tFiltering Criteria: ANY\n"
        "\t\t\tStackNames:\n"
        "\t\t\t\tInclude: ['stack-name-0', 'stack-name-1', 'stack-name-2']\n"
        "\t\t\t\tExclude: ['stack-name-3', 'stack-name-4', 'stack-name-5']\n"
        "\t\t\tStackRoles:\n"
        "\t\t\t\tExclude: ['stack-role-0', 'stack-role-1', 'stack-role-2']\n")
        assert output == expected

class TestMatchesFilter:
    filters_targets_no_wildcard = {
        "Targets": [
            {
                "TargetName": "AWS::S3::Bucket",
                "Action": "CREATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::S3::Bucket",
                "Action": "UPDATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::DynamoDB::Table",
                "Action": "CREATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::DynamoDB::Table",
                "Action": "UPDATE",
                "InvocationPoint": "PRE_PROVISION"
            }
        ]
    }

    filters_targets_with_wildcard = {
        "Targets": [
            {
                "TargetName": "AWS::S3::Bucket",
                "Action": "CREATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::SNS::Topic",
                "Action": "UPDATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::*::Table",
                "Action": "CREATE",
                "InvocationPoint": "PRE_PROVISION"
            }
        ]
    }


    filters_target_names_no_wildcard = {
        "TargetNames": [
            "AWS::CloudFormation::Stack",
            "AWS::CloudWatch::Alarm"
        ]
    }

    filters_target_names_wildcard = {
        "TargetNames": [
            "AWS::*Formation::Stack",
            "AWS::CloudWatch::Alar?"
        ]
    }

    filters_target_actions = {
        "Actions": [
            "CREATE",
            "UPDATE"
        ]
    }

    filters_target_invocation_points = {
        "InvocationPoints": [
            "PRE_PROVISION"
        ]
    }

    filters_target_names_and_actions = {
        "TargetNames": [
            "AWS::Logs::LogStream",
            "AWS::LakeFormation::Tag"
        ],
        "Actions": [
            "DELETE"
        ]
    }

    filters_target_names_and_invocation_points = {
        "TargetNames": [
            "AWS::CloudFront::Distribution",
            "AWS::CloudWatch::Alarm"
        ],
        "InvocationPoints": [
            "PRE_PROVISION"
        ]
    }

    filters_target_actions_and_invocation_points = {
        "Actions": [
            "UPDATE"
        ],
        "InvocationPoints": [
            "PRE_PROVISION"
        ]
    }

    filters_target_names_actions_and_invocation_points = {
        "TargetNames": [
            "AWS::Glue::Connection",
            "AWS::Events::EventBus"
        ],
        "Actions": [
            "CREATE",
            "DELETE"
        ],
        "InvocationPoints": [
            "PRE_PROVISION"
        ]
    }

    @pytest.mark.parametrize(
        "test_target_handler,filters,expected",
        [
            [
                {
                    "TargetName": "AWS::DynamoDB::Table",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_targets_no_wildcard,
                True
            ],
            [
                {
                    "TargetName": "AWS::CloudWatch::Alarm",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_targets_no_wildcard,
                False
            ],
            [
                {
                    "TargetName": "AWS::DynamoDB::Table",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_targets_with_wildcard,
                True
            ],
            [
                {
                    "TargetName": "AWS::SQS::Queue",
                    "Action": "DELETE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_targets_with_wildcard,
                False
            ],
            [
                {
                    "TargetName": "AWS::CloudWatch::Alarm",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_no_wildcard,
                True
            ],
            [
                {
                    "TargetName": "AWS::Kinesis::Stream",
                    "Action": "DELETE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_no_wildcard,
                False
            ],
            [
                {
                    "TargetName": "AWS::CloudFormation::Stack",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_wildcard,
                True
            ],
            [
                {
                    "TargetName": "AWS::S3::BucketPolicy",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_wildcard,
                False
            ],
            [
                {
                    "TargetName": "AWS::EC2::EIP",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_actions,
                True
            ],
            [
                {
                    "TargetName": "AWS::Athena::CapacityReservation",
                    "Action": "DELETE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_actions,
                False
            ],
            [
                {
                    "TargetName": "AWS::IoT::CACertificate",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_invocation_points,
                True
            ],
            [
                {
                    "TargetName": "AWS::Panorama::Package",
                    "Action": "CREATE",
                    "InvocationPoint": "POST_PROVISION"
                },
                filters_target_invocation_points,
                False
            ],
            [
                {
                    "TargetName": "AWS::LakeFormation::Tag",
                    "Action": "DELETE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_and_actions,
                True
            ],
            [
                {
                    "TargetName": "AWS::LakeFormation::Tag",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_and_actions,
                False
            ],
            [
                {
                    "TargetName": "AWS::SecretsManager::Secret",
                    "Action": "DELETE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_and_actions,
                False
            ],
            [
                {
                    "TargetName": "AWS::StepFunctions::Activity",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_and_actions,
                False
            ],
            [
                {
                    "TargetName": "AWS::CloudFront::Distribution",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_and_invocation_points,
                True
            ],
            [
                {
                    "TargetName": "AWS::CloudFront::Distribution",
                    "Action": "UPDATE",
                    "InvocationPoint": "POST_PROVISION"
                },
                filters_target_names_and_invocation_points,
                False
            ],
            [
                {
                    "TargetName": "AWS::CloudWatch::Alarm",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_and_invocation_points,
                True
            ],
            [
                {
                    "TargetName": "AWS::XRay::Group",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_actions_and_invocation_points,
                True
            ],
            [
                {
                    "TargetName": "AWS::XRay::Group",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_actions_and_invocation_points,
                False
            ],
            [
                {
                    "TargetName": "AWS::QuickSight::Analysis",
                    "Action": "UPDATE",
                    "InvocationPoint": "POST_PROVISION"
                },
                filters_target_actions_and_invocation_points,
                False
            ],
            [
                {
                    "TargetName": "AWS::QuickSight::Analysis",
                    "Action": "UPDATE",
                    "InvocationPoint": "POST_PROVISION"
                },
                filters_target_names_actions_and_invocation_points,
                False
            ],
            [
                {
                    "TargetName": "AWS::Glue::Connection",
                    "Action": "CREATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_actions_and_invocation_points,
                True
            ],
            [
                {
                    "TargetName": "AWS::Glue::Connection",
                    "Action": "UPDATE",
                    "InvocationPoint": "PRE_PROVISION"
                },
                filters_target_names_actions_and_invocation_points,
                False
            ],
            [
                {
                    "TargetName": "AWS::Events::EventBus",
                    "Action": "UPDATE",
                    "InvocationPoint": "POST_PROVISION"
                },
                filters_target_names_actions_and_invocation_points,
                False
            ]
        ]
    )
    def test_filter_matching(self, test_target_handler, filters, expected):
        assert _matches_filters(test_target_handler, filters) == expected

class TestBuildTargetHandlersString:
    filters_targets = {
        "Targets": [
            {
                "TargetName": "AWS::S3::Bucket",
                "Action": "CREATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::S3::Bucket",
                "Action": "UPDATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::DynamoDB::Table",
                "Action": "CREATE",
                "InvocationPoint": "PRE_PROVISION"
            },
            {
                "TargetName": "AWS::DynamoDB::Table",
                "Action": "UPDATE",
                "InvocationPoint": "PRE_PROVISION"
            }
        ]
    }

    def test_no_filters_one_handler_one_target(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket\n")
        assert output == expected

    def test_no_filters_multiple_handlers_one_target(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                },
                "preCreate": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket\n"
        "\n\tpreCreate:"
        "\n\t\tAWS::S3::Bucket\n")
        assert output == expected

    def test_no_filters_one_handler_multiple_target(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket", "AWS::SQS::Queue"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket"
        "\n\t\tAWS::SQS::Queue\n")
        assert output == expected

    def test_no_filters_multiple_handlers_multiple_targets(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket", "AWS::SQS::Queue"],
                    "permissions": []
                },
                "preUpdate": {
                    "targetNames": ["AWS::SNS::Topic", "AWS::CloudFormation::Stack"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket"
        "\n\t\tAWS::SQS::Queue\n"
        "\n\tpreUpdate:"
        "\n\t\tAWS::CloudFormation::Stack"
        "\n\t\tAWS::SNS::Topic\n")
        assert output == expected

    def test_no_filters_multiple_handlers_multiple_targets_wildcard(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S?::Bucket", "AWS::SQ*::Queue"],
                    "permissions": []
                },
                "preUpdate": {
                    "targetNames": ["AWS::SNS::Topic", "AWS::*Formation::Stack"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        def mock_resolver_function(args):
            if args == ["AWS::S?::Bucket", "AWS::SQ*::Queue"]:
                return ["AWS::S3::Bucket", "AWS::SQS::Queue"]
            if args == ["AWS::SNS::Topic", "AWS::*Formation::Stack"]:
                return ["AWS::CloudFormation::Stack", "AWS::SNS::Topic"]
        patch_type_resolver = patch("rpdk.core.type_name_resolver.TypeNameResolver.resolve_type_names", side_effect=mock_resolver_function)

        with patch_type_resolver:
            output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket"
        "\n\t\tAWS::SQS::Queue\n"
        "\n\tpreUpdate:"
        "\n\t\tAWS::CloudFormation::Stack"
        "\n\t\tAWS::SNS::Topic\n")
        assert output == expected

    def test_no_filters_one_handler_max_targets(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::SNS::Topic", "AWS::SQS::Queue", "AWS::S3::Bucket",
                                    "AWS::CloudFormation::Stack", "AWS::CloudWatch::Alarm", "AWS::EC2::Instance"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\t6 resources\n")
        assert output == expected

    def test_no_filters_multiple_handler_max_targets(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::SNS::Topic", "AWS::SQS::Queue", "AWS::S3::Bucket",
                                    "AWS::CloudFormation::Stack", "AWS::CloudWatch::Alarm", "AWS::EC2::Instance"],
                    "permissions": []
                },
                "preCreate": {
                    "targetNames": ["AWS::S3::Bucket", "AWS::SQS::Queue"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\t6 resources\n"
        "\n\tpreCreate:"
        "\n\t\tAWS::S3::Bucket"
        "\n\t\tAWS::SQS::Queue\n")
        assert output == expected

    def test_filters_one_handler_one_target_match(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preCreate": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}
        hook_configuration_data["TargetFilters"] = self.filters_targets

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreCreate:"
        "\n\t\tAWS::S3::Bucket\n")
        assert output == expected

    def test_filters_one_handler_one_target_no_match(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}
        hook_configuration_data["TargetFilters"] = self.filters_targets

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = "Based on the schema and target filters, this hook has no targets.\n"
        assert output == expected

    def test_filters_multiple_handler_one_target_mixed_match(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                },
                "preCreate": {
                    "targetNames": ["AWS::S3::Bucket"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}
        hook_configuration_data["TargetFilters"] = self.filters_targets

        output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreCreate:"
        "\n\t\tAWS::S3::Bucket\n")

        assert output == expected

    def test_filters_multiple_handler_multiple_target_mixed_match(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "preDelete": {
                    "targetNames": ["AWS::S3::Bucket", "AWS::DynamoDB::*"],
                    "permissions": []
                },
                "preCreate": {
                    "targetNames": ["AWS::S3::Bucket", "AWS::DynamoDB::*"],
                    "permissions": []
                },
                "preUpdate": {
                    "targetNames": ["AWS::DynamoDB::*"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}
        hook_configuration_data["TargetFilters"] = self.filters_targets

        def mock_resolver_function(args):
            if args == ["AWS::S3::Bucket", "AWS::DynamoDB::*"]:
                return ["AWS::DynamoDB::GlobalTable", "AWS::DynamoDB::Table", "AWS::S3::Bucket"]
            if args == ["AWS::DynamoDB::*"]:
                return ["AWS::DynamoDB::GlobalTable", "AWS::DynamoDB::Table"]
        patch_type_resolver = patch("rpdk.core.type_name_resolver.TypeNameResolver.resolve_type_names", side_effect=mock_resolver_function)

        with patch_type_resolver:
            output = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)
        expected = ("This Hook is configured to target:"
        "\n\tpreCreate:"
        "\n\t\tAWS::DynamoDB::Table"
        "\n\t\tAWS::S3::Bucket\n"
        "\n\tpreUpdate:"
        "\n\t\tAWS::DynamoDB::Table\n")
        assert output == expected

    def test_handler_not_in_handler_actions_list(self, cfn_client):
        versioned_hook_data = {}
        versioned_hook_data["Schema"] = json.dumps({
            "handlers":
            {
                "postDelete": {
                    "targetNames": ["AWS::S3::Bucket", "AWS::DynamoDB::*"],
                    "permissions": []
                }
            }
        })
        hook_configuration_data = {}
        hook_configuration_data["TargetFilters"] = self.filters_targets

        with pytest.raises(Exception) as e:
            _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)

        assert e.type == InternalError

class TestGetHookData:
    def test_get_hook_data_happy(self, cfn_client):
        response = ({
            "Arn": "TestArn",
            "Type": "HOOK",
            "TypeName": TEST_TYPE_NAME,
            "DefaultVersionId": "00000001",
            "IsDefaultVersion": True,
            "Description": "Test Description",
            "Schema": "Test Schema"
        })

        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "describe_type",
                response,
                { "TypeName": TEST_TYPE_NAME, "Type":"HOOK" }
            )
            output = _get_hook_data(cfn_client, TEST_TYPE_NAME)
        assert output == response

    def test_get_hook_data_type_not_found(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "describe_type",
                service_error_code="TypeNotFoundException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK" }
            )
            _get_hook_data(cfn_client, TEST_TYPE_NAME)
        assert e.type == DownstreamError

    def test_get_hook_data_client_error(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "describe_type",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK" }
            )
            _get_hook_data(cfn_client, TEST_TYPE_NAME)
        assert e.type == DownstreamError

    def test_get_versioned_hook_data_happy(self, cfn_client):
        response = ({
            "Arn": "TestArn",
            "Type": "HOOK",
            "TypeName": TEST_TYPE_NAME,
            "IsDefaultVersion": True,
            "TypeTestsStatus": "NOT_TESTED",
            "TypeTestsStatusDescription": "This Type version hasn't been tested yet. Run TestType to test it.",
            "Description": "Test Description",
            "Schema": "Test Schema"
            })

        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "describe_type",
                response,
                { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000001" }
            )
            output = _get_hook_data(cfn_client, TEST_TYPE_NAME, "00000001")
        assert output == response

    def test_get_versioned_hook_data_type_not_found(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "describe_type",
                service_error_code="TypeNotFoundException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000001" }
            )
            _get_hook_data(cfn_client, TEST_TYPE_NAME,  "00000001")
        assert e.type == DownstreamError

    def test_get_versioned_hook_data_client_error(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "describe_type",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000002" }
            )
            _get_hook_data(cfn_client, TEST_TYPE_NAME, "00000002")
        assert e.type == DownstreamError

class TestGetTypeConfigurationData:
    def test_get_type_configuration_data_happy(self, cfn_client):
        response = ({
            "Errors": [],
            "UnprocessedTypeConfigurations": [],
            "TypeConfigurations": [
                {
                    "Arn": "TestArn",
                    "Alias": "default",
                    "Configuration": '{"CloudFormationConfiguration":{"HookConfiguration":{"TargetStacks":"NONE","FailureMode":"FAIL"}}}',
                    "LastUpdated": datetime(2023, 11, 7, 22, 23, 22, 485000, tzinfo=tzutc())
                }
            ]
        })
        expected = { "CloudFormationConfiguration":{"HookConfiguration":{"TargetStacks":"NONE","FailureMode":"FAIL"}} }
        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "batch_describe_type_configurations",
                response,
                { "TypeConfigurationIdentifiers": [{ "Type": "HOOK", "TypeName": TEST_TYPE_NAME, "TypeConfigurationAlias": "default" }] }
            )
            output = _get_type_configuration_data(cfn_client, TEST_TYPE_NAME, "default")
        assert output == expected

    def test_get_type_configuration_data_configuration_not_found(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "batch_describe_type_configurations",
                service_error_code="TypeConfigurationNotFoundException",
                expected_params={ "TypeConfigurationIdentifiers": [{ "Type": "HOOK", "TypeName": TEST_TYPE_NAME, "TypeConfigurationAlias": "default" }] }
            )
            _get_type_configuration_data(cfn_client, TEST_TYPE_NAME, "default")
        assert e.type == DownstreamError

    def test_get_type_configuration_data_client_error(self, cfn_client):
        with Stubber(cfn_client) as stubber, pytest.raises(Exception) as e:
            stubber.add_client_error(
                "batch_describe_type_configurations",
                service_error_code="CFNRegistryException",
                expected_params={ "TypeConfigurationIdentifiers": [{ "Type": "HOOK", "TypeName": TEST_TYPE_NAME, "TypeConfigurationAlias": "default" }] }
            )
            _get_type_configuration_data(cfn_client, TEST_TYPE_NAME, "default")
        assert e.type == DownstreamError

    def test_get_type_configuration_data_no_configurations(self, cfn_client):
        response = ({
            "Errors": [],
            "UnprocessedTypeConfigurations": [],
            "TypeConfigurations": []
        })
        expected = { "CloudFormationConfiguration":{"HookConfiguration":{"TargetStacks":"NONE","FailureMode":"WARN"}} }
        with Stubber(cfn_client) as stubber:
            stubber.add_response(
                "batch_describe_type_configurations",
                response,
                expected_params={ "TypeConfigurationIdentifiers": [{ "Type": "HOOK", "TypeName": TEST_TYPE_NAME, "TypeConfigurationAlias": "default" }] }
            )
            output = _get_type_configuration_data(cfn_client, TEST_TYPE_NAME, "default")
        assert output == expected

class TestDescribeHook:
    def test_basic_hook(self, capsys, cfn_client):
        sample_timestamp = datetime(2023, 11, 7, 22, 23, 22, 485000, tzinfo=tzutc())
        hook_data_response = ({
            "Arn": "TestArn",
            "Type": "HOOK",
            "TypeName": TEST_TYPE_NAME,
            "DefaultVersionId": "00000001",
            "IsDefaultVersion": True,
            "Description": "Test Description",
            "Schema": json.dumps({
                "handlers":
                {
                    "preDelete": {
                        "targetNames": ["AWS::S3::Bucket"],
                        "permissions": []
                    }
                }
            })
        })
        hook_versioned_data_response = ({
            "Arn": "TestArn",
            "Type": "HOOK",
            "TypeName": TEST_TYPE_NAME,
            "IsDefaultVersion": True,
            "TypeTestsStatus": "NOT_TESTED",
            "TypeTestsStatusDescription": "This Type version hasn't been tested yet. Run TestType to test it.",
            "Description": "Test Description",
            "Schema": json.dumps({
                "handlers":
                {
                    "preDelete": {
                        "targetNames": ["AWS::S3::Bucket"],
                        "permissions": []
                    }
                }
            }),
            "TimeCreated": sample_timestamp,
            "LastUpdated": sample_timestamp
         })
        type_configuration_data_reponse = ({
            "Errors": [],
            "UnprocessedTypeConfigurations": [],
            "TypeConfigurations": [
                {
                    "Arn": "TestArn",
                    "Alias": "default",
                    "Configuration": '{"CloudFormationConfiguration":{"HookConfiguration":{"TargetStacks":"NONE","FailureMode":"FAIL"}}}',
                    "LastUpdated": sample_timestamp
                }
            ]
        })

        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME
        patch_project = patch(
            "hooks_extension.describe_hook.Project", autospec=True, return_value=mock_project
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
        args.version_id=None

        patch_sdk = patch("boto3.session.Session.client", autospec=True, return_value = cfn_client)

        with patch_project, patch_sdk:
            with Stubber(cfn_client) as stubber:
                stubber.add_response(
                    "describe_type",
                    hook_data_response,
                    { "TypeName": TEST_TYPE_NAME, "Type":"HOOK" }
                )
                stubber.add_response(
                    "describe_type",
                    hook_versioned_data_response,
                    { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000001"}
                )
                stubber.add_response(
                    "batch_describe_type_configurations",
                    type_configuration_data_reponse,
                    { "TypeConfigurationIdentifiers": [{ "Type": "HOOK", "TypeName": TEST_TYPE_NAME, "TypeConfigurationAlias": "default" }] }
                )
                _describe_hook(args)

        out, _ = capsys.readouterr()

        expected = ("\nNo version specified, using default version\n"
        f"\nSelected {TEST_TYPE_NAME} version 00000001\n"
        "\nDescription: Test Description\n"
        f"Version 00000001 Created at: {sample_timestamp}\n"
        f"Version 00000001 Last updated at: {sample_timestamp}\n"
        "\nCurrent configuration (only applies to default version):\n"
        "\tDefault version: 00000001\n"
        "\tConfigured behavior:\n"
        "\t\tFailure mode: FAIL\n"
        "\t\tTarget stacks: NONE\n"
        "\n\tNo configured properties.\n\n"
        "This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket\n\n"
        "Testing status: NOT_TESTED\n"
        " Warning: This Type version hasn't been tested yet. Run TestType to test it.\n").expandtabs(2)
        assert out == expected

    def test_specific_version_hook(self, capsys, cfn_client):
        sample_timestamp = datetime(2023, 11, 7, 22, 23, 22, 485000, tzinfo=tzutc())
        hook_data_response = ({
            "Arn": "TestArn",
            "Type": "HOOK",
            "TypeName": TEST_TYPE_NAME,
            "DefaultVersionId": "00000001",
            "IsDefaultVersion": True,
            "Description": "Test Description",
            "Schema": json.dumps({
                "handlers":
                {
                    "preDelete": {
                        "targetNames": ["AWS::S3::Bucket"],
                        "permissions": []
                    }
                }
            })
        })
        hook_versioned_data_response = ({
            "Arn": "TestArn",
            "Type": "HOOK",
            "TypeName": TEST_TYPE_NAME,
            "IsDefaultVersion": True,
            "TypeTestsStatus": "NOT_TESTED",
            "TypeTestsStatusDescription": "This Type version hasn't been tested yet. Run TestType to test it.",
            "Description": "Test Description",
            "Schema": json.dumps({
                "handlers":
                {
                    "preDelete": {
                        "targetNames": ["AWS::S3::Bucket"],
                        "permissions": []
                    }
                }
            }),
            "TimeCreated": sample_timestamp,
            "LastUpdated": sample_timestamp
         })
        type_configuration_data_reponse = ({
            "Errors": [],
            "UnprocessedTypeConfigurations": [],
            "TypeConfigurations": [
                {
                    "Arn": "TestArn",
                    "Alias": "default",
                    "Configuration": '{"CloudFormationConfiguration":{"HookConfiguration":{"TargetStacks":"NONE","FailureMode":"FAIL"}}}',
                    "LastUpdated": sample_timestamp
                }
            ]
        })

        mock_project = Mock(spec=Project)
        mock_project.type_name = TEST_TYPE_NAME

        patch_project = patch(
            "hooks_extension.describe_hook.Project", autospec=True, return_value=mock_project
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
        args.version_id="2"

        patch_sdk = patch("boto3.session.Session.client", autospec=True, return_value = cfn_client)

        with patch_project, patch_sdk:
            with Stubber(cfn_client) as stubber:
                stubber.add_response(
                    "describe_type",
                    hook_data_response,
                    { "TypeName": TEST_TYPE_NAME, "Type":"HOOK" }
                )
                stubber.add_response(
                    "describe_type",
                    hook_versioned_data_response,
                    { "TypeName": TEST_TYPE_NAME, "Type":"HOOK", "VersionId": "00000002"}
                )
                stubber.add_response(
                    "batch_describe_type_configurations",
                    type_configuration_data_reponse,
                    { "TypeConfigurationIdentifiers": [{ "Type": "HOOK", "TypeName": TEST_TYPE_NAME, "TypeConfigurationAlias": "default" }] }
                )
                _describe_hook(args)

        out, _ = capsys.readouterr()

        expected = (
        f"\nSelected {TEST_TYPE_NAME} version 00000002\n"
        "\nDescription: Test Description\n"
        f"Version 00000002 Created at: {sample_timestamp}\n"
        f"Version 00000002 Last updated at: {sample_timestamp}\n"
        "\nCurrent configuration (only applies to default version):\n"
        "\tDefault version: 00000001\n"
        "\tConfigured behavior:\n"
        "\t\tFailure mode: FAIL\n"
        "\t\tTarget stacks: NONE\n"
        "\n\tNo configured properties.\n\n"
        "This Hook is configured to target:"
        "\n\tpreDelete:"
        "\n\t\tAWS::S3::Bucket\n\n"
        "Testing status: NOT_TESTED\n"
        " Warning: This Type version hasn't been tested yet. Run TestType to test it.\n").expandtabs(2)
        assert out == expected
