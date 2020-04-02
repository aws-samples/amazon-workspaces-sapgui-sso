#!/usr/bin/env python3

from aws_cdk import core

from python_workspaces.python_workspaces_stack import PythonWorkspacesStack


app = core.App()
PythonWorkspacesStack(app, "python-workspaces")

app.synth()
