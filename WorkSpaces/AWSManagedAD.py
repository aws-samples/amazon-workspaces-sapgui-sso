from aws_cdk import core
import aws_cdk.aws_directoryservice as _ds
import aws_cdk.aws_workspaces as _ws
import aws_cdk.aws_ec2 as _ec2
import aws_cdk.aws_iam as _iam
import aws_cdk.aws_ssm as _ssm
import aws_cdk.aws_route53 as _r53
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_cloudformation as _cf
import aws_cdk.aws_secretsmanager as _sm


class AWSManagedAD(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Global variables to import cdk contexts from cdk.json
        _vpcID = self.node.try_get_context("VpcId")
        _sm_password = self.node.try_get_context("Secret_domain_password_arn")
        _dname = self.node.try_get_context("Domain_name")
        _subnet1 = self.node.try_get_context("Subnet1")
        _subnet2 = self.node.try_get_context("Subnet2")
        _sm_ec2keypair = self.node.try_get_context("Secret_keypair_arn")
        _ec2instance = self.node.try_get_context("Instance_type")

        # Import Vpc from the existing one in the AWS Account
        Vpc = _ec2.Vpc.from_lookup(self,"ImportVPC",vpc_id = _vpcID)
        Subnet1 = _ec2.Subnet.from_subnet_attributes(
            self,"subnetfromADManagedAD",
            subnet_id = _subnet1[0],
            availability_zone = _subnet1[1]
        )

        # Import a Secret Manager Secret for Domain Password
        secret_adpassword = _sm.Secret.from_secret_arn(
            self, "AdPasswordSecretStore",
            secret_arn = _sm_password
        )

        #Import a Secret Manager Secre for EC2 KeyPair
        secret_ec2keypair = _sm.Secret.from_secret_arn(
            self, "ImportEC2KeyPairSecretStore",
            secret_arn = _sm_ec2keypair
        )

        # Create an AWS Managed AD Service in STANDARD Version
        ad = _ds.CfnMicrosoftAD(
            self,"ManagedAD",
            name = _dname,
            password = secret_adpassword.secret_value_from_json("Key").to_string(),
            edition = "Standard",
            vpc_settings =
                { "vpcId": _vpcID,
                  "subnetIds": [ _subnet1[0], _subnet2[0] ]
                }
	    )

        self.directory = ad

        # Create r53 hosted Zone for DNS DomainName
        hostedzone = _r53.HostedZone(
            self, "HostedZoneforAD",
            zone_name = _dname,
            vpcs = [Vpc]
        )

        # Get the DNS IPs from AWS Managed AD
        targetip = _r53.RecordTarget(values = ad.attr_dns_ip_addresses)

        # Create A Record on Route 53 to point to AWS Managed AD IPs to later EC2 to join Domain
        r53Arecord = _r53.ARecord(
            self, "RecordAforAD",
            target = targetip,
            zone = hostedzone
        )

        # Create Policy to EC2JoinDomain Role
        ec2ssmpolicy = _iam.PolicyDocument(
            statements = [
                _iam.PolicyStatement(
                    actions = [
                    "ssm:DescribeAssociation",
                    "ssm:GetDocument",
                    "ssm:DescribeDocument",
                    "ssm:GetManifest",
                    "ssm:GetParameters",
                    "ssm:ListAssociations",
                    "ssm:ListInstanceAssociations",
                    "ssm:UpdateAssociationStatus",
                    "ssm:UpdateInstanceAssociationStatus",
                    "ssm:UpdateInstanceInformation"
                    ],
                    resources = [ "*" ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "ssmmessages:CreateControlChannel",
                    "ssmmessages:CreateDataChannel",
                    "ssmmessages:OpenControlChannel",
                    "ssmmessages:OpenDataChannel"
                    ],
                    resources = [ "*" ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "ec2messages:AcknowledgeMessage",
                    "ec2messages:DeleteMessage",
                    "ec2messages:FailMessage",
                    "ec2messages:GetEndpoint",
                    "ec2messages:GetMessages",
                    "ec2messages:SendReply"
                    ],
                    resources = [ "*" ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "ec2:DescribeInstanceStatus"
                    ],
                    resources = [ "*" ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "secretsmanager:GetSecretValue"
                    ],
                    resources = [ "{}".format(_sm_password) ]
                )
            ]
        )

        # Create role "EC2JoinDomain" to apply on Windows EC2JoinDomain (EC2)
        ssmrole = _iam.Role(
            self,"SSMRoleforEC2",
            assumed_by = _iam.ServicePrincipal('ec2.amazonaws.com'),
            inline_policies = { "EC2SSMPolicy": ec2ssmpolicy },
            role_name = "EC2JoinDomain"
        )

        # Create Policy to workspaces_DefaultRole Role
        wsdefaultpolicy = _iam.PolicyDocument(
            statements = [
                _iam.PolicyStatement(
                    actions = [
                    "ec2:CreateNetworkInterface",
                    "ec2:DeleteNetworkInterface",
                    "ec2:DescribeNetworkInterfaces"
                    ],
                    resources = [ "*" ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "workspaces:RebootWorkspaces",
                    "workspaces:RebuildWorkspaces",
                    "workspaces:ModifyWorkspaceProperties"
                    ],
                    resources = [ "*" ]
                )
            ]
        )

        # Create role workspaces_DefaultRole for later WorkSpaces API usage
        wsrole = _iam.Role(
            self, "WorkSpacesDefaultRole",
            assumed_by = _iam.ServicePrincipal('workspaces.amazonaws.com'),
            inline_policies = { "WorkSpacesDefaultPolicy": wsdefaultpolicy },
            role_name = "workspaces_DefaultRole"
        )

        # Create a security group for RDP access on Windows EC2JoinDomain (EC2)
        rdpsg = _ec2.SecurityGroup(
            self, "SGForRDP",
            vpc = Vpc,
            description = "The Secrurity Group from local environment to Windows EC2 Instance"
        )

        rdpsg.add_ingress_rule(
            peer = _ec2.Peer.ipv4("192.168.1.1/32"),
            connection = _ec2.Port.tcp(3389)
        )

        # Create Windows EC2JoinDomain (EC2) as AD Admin server
        adadminEC2 = _ec2.Instance(
            self, "WindowsEC2",
            instance_type = _ec2.InstanceType(instance_type_identifier = _ec2instance),
            machine_image = _ec2.MachineImage.latest_windows(
                version = _ec2.WindowsVersion.WINDOWS_SERVER_2016_ENGLISH_FULL_BASE
            ),
            vpc = Vpc,
            key_name = secret_ec2keypair.secret_value_from_json("Key").to_string(),
            role = ssmrole,
            security_group = rdpsg,
            vpc_subnets = _ec2.SubnetSelection(
                subnets = [ Subnet1 ]
            )
        )

        adadminEC2.instance.add_depends_on(ad)

        # Create a SSM Parameter Store for Domain Name
        domain = _ssm.StringParameter(
            self, "ADDomainName",
            parameter_name = "ad_join_domain_name",
            string_value = ad.name
        )

        # Create a SSM Parameter Store for Domain User
        aduser = _ssm.StringParameter(
            self, "ADDomainUser",
            parameter_name = "ad_join_domain_user",
            string_value = "Admin"
        )

        domain.node.add_dependency(ad)
        aduser.node.add_dependency(ad)

        # Create SSM Document to join Window EC2 into AD
        ssmdocument = _ssm.CfnDocument(
            self, "SSMDocumentJoinAD",
            document_type = "Command",
            name = "SSMDocumentJoinAD",
            content =
            {
                "description": "Run a PowerShell script to domain join a Windows instance securely",
                "schemaVersion": "2.0",
                "mainSteps": [
                    {
                        "action": "aws:runPowerShellScript",
                        "name": "runPowerShellWithSecureString",
                        "inputs": {
                            "runCommand": [
                            "# Example PowerShell script to domain join a Windows instance securely",
                            "# Adopt the document from AWS Blog Join a Microsoft Active Directory Domain with Parameter Store and Amazon EC2 Systems Manager Documents",
                            "",
                            "$ErrorActionPreference = 'Stop'",
                            "",
                            "try{",
                            "    # Parameter names",
                            "    # $dnsParameterStore = ([System.Net.Dns]::GetHostAddresses({}).IPAddressToString[0])".format(domain.parameter_name),
                            "    $domainNameParameterStore = \"{}\"".format(domain.parameter_name),
                            "    $domainJoinUserNameParameterStore = \"{}\"".format(aduser.parameter_name),
                            "    $domainJoinPasswordParameterStore = \"{}\"".format(secret_adpassword.secret_arn),
                            "",
                            "    # Retrieve configuration values from parameters",
                            "    $ipdns = ([System.Net.Dns]::GetHostAddresses(\"{}\").IPAddressToString[0])".format(_dname),
                            "    $domain = (Get-SSMParameterValue -Name $domainNameParameterStore).Parameters[0].Value",
                            "    $username = $domain + \"\\\" + (Get-SSMParameterValue -Name $domainJoinUserNameParameterStore).Parameters[0].Value",
                            "    $password = ((Get-SECSecretValue -SecretId $domainJoinPasswordParameterStore ).SecretString | ConvertFrom-Json ).Key | ConvertTo-SecureString -asPlainText -Force ",
                            "",
                            "    # Create a System.Management.Automation.PSCredential object",
                            "    $credential = New-Object System.Management.Automation.PSCredential($username, $password)",
                            "",
                            "    # Determine the name of the Network Adapter of this machine",
                            "    $networkAdapter = Get-WmiObject Win32_NetworkAdapter -Filter \"AdapterType = 'Ethernet 802.3'\"",
                            "    $networkAdapterName = ($networkAdapter | Select-Object -First 1).NetConnectionID",
                            "",
                            "    # Set up the IPv4 address of the AD DNS server as the first DNS server on this machine",
                            "    netsh.exe interface ipv4 add dnsservers name=$networkAdapterName address=$ipdns index=1",
                            "",
                            "    # Join the domain and reboot",
                            "    Add-Computer -DomainName $domain -Credential $credential",
                            "    Restart-Computer -Force",
                            "}",
                            "catch [Exception]{",
                            "    Write-Host $_.Exception.ToString()",
                            "    Write-Host 'Command execution failed.'",
                            "    $host.SetShouldExit(1)",
                            "}"
                            ]
                        }
                   }
               ]
            }
        )

        # Create SSM Associate to trigger SSM doucment to let Windows EC2JoinDomain (EC2) join Domain
        ssmjoinad = _ssm.CfnAssociation(
            self,"WindowJoinAD",
            name = ssmdocument.name,
            targets = [{
                "key": "InstanceIds",
                "values": [ adadminEC2.instance_id ]
            }]
        )

        ssmjoinad.add_depends_on(ssmdocument)

        # Create a Policy for Lambda Role
        lambdapolicy = _iam.PolicyDocument(
            statements = [
                _iam.PolicyStatement(
                    actions = [ "logs:CreateLogGroup" ],
                    resources = [ "arn:aws:logs:{}:{}:*".format(self.region,self.account) ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                    ],
                    resources = [ "arn:aws:logs:{}:{}:log-group:/aws/lambda/*".format(self.region,self.account) ]
                ),
                _iam.PolicyStatement(
                    actions = [
                    "workspaces:RegisterWorkspaceDirectory",
                    "workspaces:DeregisterWorkspaceDirectory",
                    "ds:DescribeDirectories",
                    "ds:AuthorizeApplication",
                    "ds:UnauthorizeApplication",
                    "iam:GetRole",
                    "ec2:DescribeInternetGateways",
                    "ec2:DescribeVpcs",
                    "ec2:DescribeRouteTables",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:CreateSecurityGroup",
                    "ec2:CreateTags"
                    ],
                    resources = [ "*" ]
                )
            ]
        )

        # Creare a IAM Role for Lambda
        lambdarole = _iam.Role(
            self,"LambdaRoleForRegisterDS",
            assumed_by = _iam.ServicePrincipal('lambda.amazonaws.com'),
            inline_policies = { "LambdaActicateDS": lambdapolicy },
            role_name = "LambdaActivateDirectoryService"
        )

        # Create a Lambda function to Register Directory Service on WorkSpaces
        dslambda = _lambda.Function(
            self, "LambdaStackForDSFunction",
            runtime = _lambda.Runtime.PYTHON_3_7,
            handler = "workspaceds.handler",
            role = lambdarole,
            code=_lambda.Code.asset('lambda'),
            environment={
                "DIRECTORY_ID": ad.ref
            },
            timeout = core.Duration.seconds(120)
        )
        # Create a customResource to trigger Lambda function after Lambda function is created
        _cf.CfnCustomResource(
            self, "InvokeLambdaFunction",
            service_token = dslambda.function_arn
        )

    # Return AWS Managed AD Directory Service ID for WorkSpaces creation
    def get_ad(self):
        return self.directory
