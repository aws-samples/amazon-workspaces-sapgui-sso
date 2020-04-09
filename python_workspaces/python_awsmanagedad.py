from aws_cdk import core
import aws_cdk.aws_directoryservice as _ds
import aws_cdk.aws_workspaces as _ws
import aws_cdk.aws_ec2 as _ec2
import aws_cdk.aws_iam as _iam
import aws_cdk.aws_ssm as _ssm
import aws_cdk.aws_route53 as _r53
import aws_cdk.aws_lambda as _lambda
import aws_cdk.custom_resources as _custom
import aws_cdk.aws_cloudformation as _cf


class AWSManagedAD(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        _vpcID = self.node.try_get_context("VpcId")
        _dpassword = self.node.try_get_context("domain_password")
        _dname = self.node.try_get_context("domain_name")
        _subnet1 = self.node.try_get_context("Subnet1")
        _subnet2 = self.node.try_get_context("Subnet2")
        _ec2keypair = self.node.try_get_context("keypair")
        _ec2instance = self.node.try_get_context("instance_type")

        #Import Vpc
        Vpc = _ec2.Vpc.from_lookup(self,"ImportVPC",vpc_id = _vpcID)
        Subnet1 = _ec2.Subnet.from_subnet_attributes(
            self,"subnetfromADManagedAD",
            subnet_id = _subnet1[0],
            availability_zone = _subnet1[1]
        )

        # Create an AWS Managed AD Service
        ad = _ds.CfnMicrosoftAD(
            self,"ManagedAD",
            name = _dname,
            password = _dpassword,
            edition = "Standard",
            vpc_settings =
                { "vpcId": _vpcID,
                  "subnetIds": [ _subnet1[0], _subnet2[0] ]
                }
	    )

        self.directory = ad

        #Create r53 hosted Zone for DNS DomainName
        hostedzone = _r53.HostedZone(
            self, "HostedZoneforAD",
            zone_name = _dname,
            vpcs = [Vpc]
        )

        targetip = _r53.RecordTarget(values = ad.attr_dns_ip_addresses)

        _r53.ARecord(
            self, "RecordAforAD",
            target = targetip,
            zone = hostedzone
        )

        #create role "EC2JoinDomain" to apply on Windows EC2JoinDomain
        ssmrole = _iam.Role(
            self,"SSMRoleforEC2",
            assumed_by = _iam.ServicePrincipal('ec2.amazonaws.com'),
            managed_policies = [
                _iam.ManagedPolicy.from_managed_policy_arn(
                    self,"AmazonEC2RoleforSSM",
                    managed_policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforSSM"
                )
            ],
            role_name = "EC2JoinDomain"
        )

        #create a security group for RDP access
        rdpsg = _ec2.SecurityGroup(
            self, "SGForRDP",
            vpc = Vpc
        )

        rdpsg.add_ingress_rule(
            peer = _ec2.Peer.any_ipv4(),
            connection = _ec2.Port.tcp(3389)
        )

        #create Windows EC2 as AD Admin server
        adadminEC2 = _ec2.Instance(
            self, "WindowsEC2",
            instance_type = _ec2.InstanceType(instance_type_identifier = _ec2instance),
            machine_image = _ec2.MachineImage.latest_windows(
                version = _ec2.WindowsVersion.WINDOWS_SERVER_2016_ENGLISH_FULL_BASE
            ),
            vpc = Vpc,
            key_name = _ec2keypair,
            role = ssmrole,
            security_group = rdpsg,
            vpc_subnets = _ec2.SubnetSelection(
                subnets = [ Subnet1 ]
            )
        )

        #Create a SSM Parameter Store for Domain Name
        domain = _ssm.StringParameter(
            self, "ADDomainName",
            parameter_name = "ad_join_domain_name",
            string_value = ad.name
        )

        #Create a SSM Parameter Store for Domain User
        aduser = _ssm.StringParameter(
            self, "ADDomainUser",
            parameter_name = "ad_join_domain_user",
            string_value = "Admin"
        )

        #Create a SSM Parameter Store for Domain Password
        adpassword = _ssm.StringParameter(
            self, "AdPasswordParmeterStore",
            parameter_name = "ad_join_admin_password",
            string_value = _dpassword
        )

        domain.node.add_dependency(ad)
        aduser.node.add_dependency(ad)
        adpassword.node.add_dependency(ad)

        #Create SSM Document to join Window EC2 into AD
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
                            "    $domainJoinPasswordParameterStore = \"{}\"".format(adpassword.parameter_name),
                            "",
                            "    # Retrieve configuration values from parameters",
                            "    $ipdns = ([System.Net.Dns]::GetHostAddresses(\"{}\").IPAddressToString[0])".format(_dname),
                            "    $domain = (Get-SSMParameterValue -Name $domainNameParameterStore).Parameters[0].Value",
                            "    $username = $domain + \"\\\" + (Get-SSMParameterValue -Name $domainJoinUserNameParameterStore).Parameters[0].Value",
                            "    $password = (Get-SSMParameterValue -Name $domainJoinPasswordParameterStore).Parameters[0].Value| ConvertTo-SecureString -asPlainText -Force",
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

        _ssm.CfnAssociation(
            self,"WindowJoinAD",
            name = ssmdocument.name,
            targets = [{
                "key": "InstanceIds",
                "values": [ adadminEC2.instance_id ]
            }]
        )

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
                    "ds:DescribeDirectories",
                    "ds:AuthorizeApplication",
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

        #Creare a IAM Role for Lambda
        lambdarole = _iam.Role(
            self,"LambdaRoleForRegisterDS",
            assumed_by = _iam.ServicePrincipal('lambda.amazonaws.com'),
            inline_policies = { "LambdaActicateDS": lambdapolicy },
            role_name = "LambdaActivateDirectoryService"
        )

        #Create a Lambda function to Register Directory Service on WorkSpaces
        dslambda = _lambda.Function(
            self, "LambdaStackForDSFunction",
            runtime = _lambda.Runtime.PYTHON_3_7,
            handler = "workspaceds.handler",
            role = lambdarole,
            code=_lambda.Code.asset('lambda'),
            environment={
                "DIRECTORY_ID": ad.ref,
                "SUBNETID1": _subnet1[0],
                "SUBNETID2": _subnet2[0]
            }
        )

        _cf.CustomResource(
            self, "InvokeLambdaFunction",
            provider = _cf.CustomResourceProvider.from_lambda(dslambda)
        )


    def get_ad(self):
        return self.directory
        #Create EC2 Windows Server 2012 to Manage AD
        #adeni = _ec2.CfnNetworkInterface

        #build up a workspaces based on windows 10 bundle_id
