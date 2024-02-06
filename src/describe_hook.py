"""
This sub command provides a description of the hook registered in your AWS account.
"""
import json
import logging
from argparse import Namespace
from fnmatch import fnmatch

from botocore.exceptions import ClientError

from rpdk.core.project import Project
from rpdk.core.exceptions import DownstreamError, InternalError
from rpdk.core.type_name_resolver import TypeNameResolver, contains_wildcard
from rpdk.core.boto_helpers import create_sdk_session

LOG = logging.getLogger(__name__)

COMMAND_NAME = "describe"

CLOUDFORMATION_CONFIGURATION_KEY = "CloudFormationConfiguration"
HOOK_CONFIGURATION_KEY = "HookConfiguration"

def _build_properties_string(hook_configuration_data: dict) -> str:
    """
    Builds the string that displays the configured properties from the Hook type configuration.

    Parameters:
        hook_configuration_data (dict): The hook type configuration data as returned by the CloudFormation BatchDescribeTypeConfigurations API.

    Returns:
        string: Formatted string table of the configured properties and their values (or 'No configured properties.' if none are specified).
            Table header row contains labels for 'Property' and 'Value'. Each property/value pair is printed on its own row.
            Spacing to and from column seperator is consistent.

    e.g.

    Property   | Value
    --------------------
    MinStacks  | 2
    ExtraList  | ['value1', 'value2', 'value3']
    """
    if not hook_configuration_data.get('Properties'):
        return "No configured properties."

    configured_properties = hook_configuration_data["Properties"]

    # calc largest key length for spacing
    max_property_key_length = max(map(len, configured_properties.keys()))
    max_width = max(len("Property"), max_property_key_length) + 2
    # use max_width to add spaces between key and column seperator
    output_string = "Configured properties:\n" + \
    "\t\tProperty" + " "*(max_width - len('Property')) + "| Value\n" + "\t\t" + "-"*(max_width + 10) + "\n"

    property_value_string = ["\t\t" + str(prop) + " "*(max_width-len(prop)) + "| " + str(val) for prop, val in configured_properties.items()]
    output_string += "\n".join(property_value_string)
    return output_string

def _build_stack_filters_string(hook_configuration_data: dict) -> str:
    """
    Builds the string that displays the stack filters from the Hook type configuration.

    Parameters:
        hook_configuration_data (dict): The hook type configuration data as returned by the CloudFormation BatchDescribeTypeConfigurations API.

    Returns:
        string: Formatted string of any existing stack filters (or empty string if none are specified).

    e.g.

        Stack Filters:
            FilteringCriteria: ANY
            StackNames:
            Include: ['my-stack-1']
            StackRoles:
            Exclude: ['my-stack-role-2']
    """
    if "StackFilters" not in hook_configuration_data:
        return ""

    stack_filters = hook_configuration_data["StackFilters"]

    output_string = "\t\tStack Filters:\n" + \
    f"\t\t\tFiltering Criteria: {stack_filters['FilteringCriteria']}\n".format()

    string_list = []
    for filter_name in stack_filters:
        if filter_name == "FilteringCriteria":
            continue
        string_list.append(f"\t\t\t{filter_name}:\n")
        if "Include" in stack_filters[filter_name]:
            string_list.append(f"\t\t\t\tInclude: {stack_filters[filter_name]['Include']}\n")
        if "Exclude" in stack_filters[filter_name]:
            string_list.append(f"\t\t\t\tExclude: {stack_filters[filter_name]['Exclude']}\n")
    output_string += "".join(string_list)
    return output_string

def _matches_filters(target_handler: dict, filters: dict) -> bool:
    """
    Determines whether the specified target handler matches the specified target filters based on target name, action, and invocation point.

    Parameters:
        target_handler (dict): Must contain keys 'TargetName', 'Action', and 'InvocationPoint' which specify the target for the hook.
            TargetName cannot contain wildcard chars.
        filters (dict): Specifies the target filters for the hooks. Must match spec defined here:
            https://docs.aws.amazon.com/cloudformation-cli/latest/userguide/hooks-structure.html#hooks-targetfilters

    Returns:
        bool: Whether the [target_handler] matches any of the [filters].
    """
    if "Targets" in filters:
        for target_filter in filters["Targets"]:
            if contains_wildcard(target_filter["TargetName"]):
                matches_target_name = fnmatch(target_handler["TargetName"], target_filter["TargetName"])
            else:
                matches_target_name = target_handler["TargetName"] == target_filter["TargetName"]
            matches_action = target_handler["Action"] == target_filter["Action"]
            matches_invocation_point = target_handler["InvocationPoint"] == target_filter["InvocationPoint"]
            if matches_target_name and matches_action and matches_invocation_point:
                return True
        return False

    if "TargetNames" in filters:
        target_name_matches = map(lambda target_name: fnmatch(target_handler["TargetName"], target_name), filters["TargetNames"])
        matches_target_name = any(target_name_matches)
    else:
        matches_target_name = True

    if "Actions" in filters:
        matches_action = target_handler["Action"] in filters["Actions"]
    else:
        matches_action = True

    if "InvocationPoints" in filters:
        matches_invocation_point = target_handler["InvocationPoint"] in filters["InvocationPoints"]
    else:
        matches_invocation_point = True

    return matches_target_name and matches_action and matches_invocation_point

def _build_target_handlers_string(cfn_client, versioned_hook_data: dict, hook_configuration_data: dict) -> str:
    """
    Builds the string that displays the target handlers based on the hook schema and hook type configuration.

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        versioned_hook_data (dict): The hook description as returned by the CloudFormation DescribeType API.
        hook_configuration_data (dict): The hook type configuration data as returned by the CloudFormation BatchDescribeTypeConfigurations API.

    Returns:
        string: Formatted string of the targets for each of handlers for this hook
            (or "Based on the schema and target filters, this hook has no targets." if no targets).

    e.g.

    This Hook is configured to target:
        preCreate:
        AWS::S3::Bucket
        AWS::SQS::Queue
        preDelete:
        AWS::CloudWatch::Alarm
        preUpdate:
        AWS::Kinesis::Stream
    """
    schema_json = json.loads(versioned_hook_data["Schema"])
    handlers = schema_json["handlers"]
    has_filters = "TargetFilters" in hook_configuration_data
    compiled_target_handlers_string = ""

    handler_names_to_actions = {
        "preCreate": ("CREATE", "PRE_PROVISION"),
        "preUpdate": ("UPDATE", "PRE_PROVISION"),
        "preDelete": ("DELETE", "PRE_PROVISION")
    }

    for handler, handler_config in handlers.items():
        if handler in handler_names_to_actions:
            action, invocation_point = handler_names_to_actions[handler]
            target_names_from_schema = handler_config["targetNames"]
        else:
            raise InternalError("Internal error (handler name in schema is invalid)")
        total_target_names = TypeNameResolver(cfn_client).resolve_type_names(target_names_from_schema)
        if has_filters:
            total_target_names = list(filter(
                lambda targetName:
                    _matches_filters(
                        {
                            "TargetName": targetName,
                            "Action": action,
                            "InvocationPoint": invocation_point
                        },
                        hook_configuration_data["TargetFilters"]
                    ),
                total_target_names))

        if not total_target_names:
            continue
        compiled_target_handlers_string += "\n\t" + handler + ":\n\t\t"

        if len(total_target_names) <= 5:
            compiled_target_handlers_string += "\n\t\t".join(total_target_names) + "\n"
        else:
            compiled_target_handlers_string += str(len(total_target_names)) + " resources\n"
    if not compiled_target_handlers_string:
        return "Based on the schema and target filters, this hook has no targets.\n"
    return "This Hook is configured to target:" + compiled_target_handlers_string

def _get_hook_data(cfn_client, type_name: str, version_id: str = None) -> dict:
    """
    Gets Hook description by calling CloudFormation DescribeType API with arguments.
    https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeType.html

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        type_name (string): The hook type name to call DescribeType with.
        version_id (string) - optional: The version id of the hook type to call DescribeType with.

    Returns:
        dict: The response from the DescribeType API.
    """
    try:
        if version_id is None:
            LOG.debug("Calling DescribeType for %s without version id to get default version id", type_name)
            hook_data = cfn_client.describe_type(TypeName=type_name, Type="HOOK")
        else:
            LOG.debug("Calling DescribeType for %s with version id %s", type_name, version_id)
            hook_data = cfn_client.describe_type(TypeName=type_name, Type="HOOK", VersionId=version_id)
    except cfn_client.exceptions.TypeNotFoundException as e:
        if version_id is None:
            msg = "Describing type resulted in TypeNotFoundException. " \
                 "This type does not seem to exist in your account in this region. Have you registered this hook?"
        else:
            msg = f"Describing type with version id {version_id} resulted in TypeNotFoundException. " \
                "This specific version does not seem to exist in your account in this region."
        print("\n" + msg)
        raise DownstreamError(msg) from e
    except ClientError as e:
        raise DownstreamError from e
    return hook_data

def _get_type_configuration_data(cfn_client, type_name: str, type_configuration_alias: str) -> dict:
    """
    Gets the Hook type configuration by caling CloudFormation BatchDescribeTypeConfigurations API with arguments.
    https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_BatchDescribeTypeConfigurations.html

    Parameters:
        cfn_client: Boto3 session CloudFormation client.
        type_name (string): The hook type name to use as a TypeConfigurationIdentifier when calling BatchDescribeTypeConfigurations.
        type_configuration_alias (string): The hook type configuration alias to use as a TypeConfigurationIdentifier
            when calling BatchDescribeTypeConfigurations.

    Returns:
        dict: The response from the BatchDescribeTypeConfigurations API.
    """
    type_configuration_not_found_msg = "Describing type configuration resulted in TypeConfigurationNotFoundException. " \
        "Have you set a type configuration for this hook?"
    try:
        LOG.debug("Calling BatchDescribeTypeConfigurations for %s and configuration alias %s", type_name, type_configuration_alias)
        batch_describe_type_configurations_response = cfn_client.batch_describe_type_configurations(
            TypeConfigurationIdentifiers=[{"Type": "HOOK", "TypeName": type_name, "TypeConfigurationAlias": type_configuration_alias}])["TypeConfigurations"]
        LOG.debug("Successful response from BatchDescribeTypeConfigurations")
        # Nested hook config is a string, converting to json here is necessary
        data = json.loads(batch_describe_type_configurations_response[0]["Configuration"])
    except cfn_client.exceptions.TypeConfigurationNotFoundException as e:
        print("\n" + type_configuration_not_found_msg)
        raise DownstreamError(type_configuration_not_found_msg) from e
    except ClientError as e:
        raise DownstreamError from e
    except IndexError as e:
        LOG.debug("No type configurations found. This likely means that an initial type configuration was never set. " \
                  "Using a substituted default type configuration", exc_info=e)
        data = {
            CLOUDFORMATION_CONFIGURATION_KEY: {
                HOOK_CONFIGURATION_KEY: {
                    "FailureMode": "WARN",
                    "TargetStacks": "NONE"
                }
            }
        }

    return data

def _describe_hook(args: Namespace) -> None:
    """
    Main method for the hook describe command. Displays the information for the current hook project,
    including default version, failure mode, target stacks, stack filters, configured properties, description,
    created at time, last updated time, targets, and testing status.

    Parameters:
        args (Namespace): The arguments to use with this command.
            Required keys in Namespace: 'version_id', 'profile', 'endpoint_url', 'region'. All default to None.

    Returns:
        None.

    Side effect: All information printed to system out.
    """
    cfn_client = create_sdk_session(args.region, args.profile).client("cloudformation", endpoint_url=args.endpoint_url)
    project = Project()
    project.load()
    type_name = project.type_name

    if args.version_id is None:
        print("\nNo version specified, using default version")

    hook_data = _get_hook_data(cfn_client, type_name)
    version_id =  hook_data["DefaultVersionId"] if not args.version_id else args.version_id.zfill(8)
    print(f"\nSelected {type_name} version {version_id}")

    versioned_hook_data = _get_hook_data(cfn_client, type_name, version_id)
    type_configuration_data =_get_type_configuration_data(cfn_client, type_name, "default")
    hook_configuration_data = type_configuration_data[CLOUDFORMATION_CONFIGURATION_KEY][HOOK_CONFIGURATION_KEY]

    configured_properties_string = _build_properties_string(hook_configuration_data)
    stack_filters_string = _build_stack_filters_string(hook_configuration_data)

    current_configuration_string = (f"\nCurrent configuration (only applies to default version):\n"
    f"\tDefault version: {hook_data['DefaultVersionId']}\n"
    f"\tConfigured behavior:\n"
    f"\t\tFailure mode: {hook_configuration_data['FailureMode']}\n"
    f"\t\tTarget stacks: {hook_configuration_data['TargetStacks']}\n"
    f"{stack_filters_string}"
    f"\n\t{configured_properties_string}\n")

    compiled_target_handlers_string = _build_target_handlers_string(cfn_client, versioned_hook_data, hook_configuration_data)

    print(f"\nDescription: {versioned_hook_data['Description']}\n"
    f"Version {version_id} Created at: {versioned_hook_data['TimeCreated']}\n"
    f"Version {version_id} Last updated at: {versioned_hook_data['LastUpdated']}\n"
    f"{current_configuration_string}\n"
    f"{compiled_target_handlers_string}\n"
    f"Testing status: {versioned_hook_data['TypeTestsStatus']}"
    .expandtabs(2))
    if versioned_hook_data["TypeTestsStatus"] != "PASSED":
        print(f" Warning: {versioned_hook_data['TypeTestsStatusDescription']}")

def setup_parser(parser):
    describe_subparser = parser.add_parser(COMMAND_NAME, description=__doc__)
    describe_subparser.set_defaults(command=_describe_hook)
    describe_subparser.add_argument("--version-id", help="Hook version number.")
    describe_subparser.add_argument("--profile", help="AWS profile to use.")
    describe_subparser.add_argument("--endpoint-url", help="CloudFormation endpoint to use.")
    describe_subparser.add_argument("--region", help="AWS Region to submit the type.")
