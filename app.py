#!/usr/bin/env python3

from aws_cdk import core

from WorkSpaces.AWSManagedAD import AWSManagedAD
from WorkSpaces.AmazonWorkSpaces import AWSWorkSpaces


app = core.App()

env_workspaces = core.Environment(
        account = app.node.try_get_context("Account"),
        region = app.node.try_get_context("Region")
      )

AD = AWSManagedAD(
    app, "AWSManagedAD",
    env = env_workspaces
)

AWSWorkSpaces(
    app, "AWSWorkSpaces", AD,
    env = env_workspaces
)

app.synth()
