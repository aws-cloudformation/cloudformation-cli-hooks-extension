# AWS CloudFormation CLI Hooks Extension

The CloudFormation CLI (cfn) allows you to author your own CFN extension providers that can be used by CloudFormation.

This extension library provides more commands for managing and configuring your Resource Hooks.


### Documentation

Primary documentation for the CloudFormation CLI can be found at the [AWS Documentation](https://docs.aws.amazon.com/cloudformation-cli/latest/userguide/what-is-cloudformation-cli.html) site.

### Installation

If you are using this package to build hook providers for CloudFormation, install the [CloudFormation CLI Hooks Extension](https://github.com/aws-cloudformation/cloudformation-cli-hooks-extension) - this will automatically install the the [CloudFormation CLI](https://github.com/aws-cloudformation/cloudformation-cli)! A Python virtual environment is recommended.

```shell
pip3 install cloudformation-cli-hooks-extension
```

### Usage

All of these commands are meant to be run from inside your pre-initialized Hooks project directory. You can initialize a new project by using the `cfn init` command from the [CloudFormation CLI](https://github.com/aws-cloudformation/cloudformation-cli?tab=readme-ov-file#command-init). All of the commands use the `cfn hook` prefix, ex. `cfn hook describe`.

#### Command: describe

To get more details about hook versions registered in your account, use the `describe` command. This will return the following properties:

- Description
- Created at
- Last updated at
- Default version
- Failure mode
- Target stacks
- Stack filters (if any)
- Configured properties
- Target types
- Testing status

The details for the default version will be returned by deafult. Optionally, the `--version-id` can be passed to describe a specific version.

```bash
cfn hook describe
```

Sample output:

```
No version specified, using default version

Selected AWS::CloudFormation::SampleHook version 00000001

Description: Example hook
Version 00000001 Created at: 2023-09-28 04:44:14.402000+00:00
Version 00000001 Last updated at: 2023-09-28 04:44:14.402000+00:00

Current configuration (only applies to default version):
  Default version: 00000001
  Configured behavior:
    Failure mode: WARN
    Target stacks: ALL
    Stack Filters:
      Filtering Criteria: ANY
      StackNames:
        Include: ['stack-name-0', 'stack-name-1', 'stack-name-2']
        Exclude: ['stack-name-3', 'stack-name-4', 'stack-name-5']
      StackRoles:
        Exclude: ['arn:aws:iam::000000000000:role/stack-role-0', 'arn:aws:iam::000000000000:role/stack-role-1', 'arn:aws:iam::000000000000:role/stack-role-2']

  No configured properties.

This Hook is configured to target:
  preCreate:
    AWS::S3::Bucket

Testing status: NOT_TESTED
 Warning: This Type version hasn't been tested yet. Run TestType to test it.
```

### Command: set-default-version

To set a specific version of your hooks as the default version, use the `set-default-version` command.

```bash
cfn hook set-default-version --version-id 1
```

This command return nothings, but you can then use `cfn hook describe` to check the default version set in your account.

### Command: configure

To set the type configuration of your hook, use the `configure` command.

You will first need to save your type configuration as a json file and then specify the file path in the command.


```bash
cfn hook configure --configuration-path ./myHookTypeConfig.json
```

Sample output:

```
ConfigurationArn: arn:aws:cloudformation:us-east-1:000000000000:type-configuration/hook/AWS-CloudFormation-SampleHook/default
```


## Development

For developing, it's strongly suggested to install the development dependencies inside a virtual environment. (This isn't required if you just want to use this tool.)

```bash
python3 -m venv env
source env/bin/activate
pip3 install -e /path/to/cloudformation-cli-hooks-extension
```

Install `pytest-cov`, used when running unit tests for this plugin:

```shell
pip3 install pytest-cov
```

You may also want to check out the [CloudFormation CLI](https://github.com/aws-cloudformation/cloudformation-cli) if you wish to make edits to that. In this case, installing them in one operation works well:

```shell
pip3 install \
  -e /path/to/cloudformation-cli \
  -e /path/to/cloudformation-cli-hooks-extension
```

That ensures neither is accidentally installed from PyPI.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.
