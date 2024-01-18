#!/usr/bin/env python
"""Hook extension for the CloudFormation CLI"""
import os.path
import re
from setuptools import setup

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):
    with open(os.path.join(HERE, *parts), "r", encoding="utf-8") as fp:
        return fp.read()


# https://packaging.python.org/guides/single-sourcing-package-version/
def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name="cloudformation-cli-hooks-extension",
    version=find_version("src", "hooks_extension", "__init__.py"),
    description=__doc__,
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="Amazon Web Services",
    # TODO: REVISIT FIELDS BELOW BEFORE PUBLISHING
    author_email="aws-cloudformation-developers@amazon.com",
    url="https://github.com/aws-cloudformation/aws-cloudformation-rpdk-python-plugin/",
    # https://packaging.python.org/guides/packaging-namespace-packages/
    packages=["hooks_extension"],
    package_dir={"": "src"},
    include_package_data=True,
    zip_safe=True,
    python_requires=">=3.6",
    install_requires=["cloudformation-cli>=0.2.33"],
    entry_points={
        "rpdk.v1.extensions": [
            "describeHook = hooks_extension.describe_hook:DescribeHookExtension",
            "configureHook = hooks_extension.configure_hook:ConfigureHookExtension",
            "setDefaultHook = hooks_extension.set_default_hook_version:SetDefaultHookVersionExtension",
        ],
    }
    # license="Apache License 2.0",
    # classifiers=[
    #     "Development Status :: 5 - Production/Stable",
    #     "Environment :: Console",
    #     "Intended Audience :: Developers",
    #     "License :: OSI Approved :: Apache Software License",
    #     "Natural Language :: English",
    #     "Topic :: Software Development :: Build Tools",
    #     "Topic :: Software Development :: Code Generators",
    #     "Operating System :: OS Independent",
    #     "Programming Language :: Python :: 3 :: Only",
    #     "Programming Language :: Python :: 3.6",
    #     "Programming Language :: Python :: 3.7",
    # ],
    # keywords="Amazon Web Services AWS CloudFormation",
)