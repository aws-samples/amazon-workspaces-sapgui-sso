from aws_cdk import core
import aws_cdk.aws_directoryservice as _ds
import aws_cdk.aws_workspaces as _ws
import aws_cdk.aws_ec2 as _ec2


class AWSWorkSpaces(core.Stack):

    def __init__(self, scope: core.Construct, id: str, directory, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # The code that defines your stack goes here
        _user = self.node.try_get_context("WorkSpacesUser")
        _windows = self.node.try_get_context("WorkSpacesBundle")

        #build up a workspaces based on windows 10 bundle_id
        ws = _ws.CfnWorkspace(
            self,"WorkSpaces",
            bundle_id = _windows,
            directory_id = directory.get_ad().ref,
            user_name = _user
        )
