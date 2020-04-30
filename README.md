AWS CDK example to build Amazon WorkSpaces to integrate SAP environment with feature Single-Sign-On
--------------------------------------
How to setup Amazon WorkSpaces and integrate with SAP GUI for single sign-on. More information see SAP on AWS blog


Prerequisite
-------------
* [AWS Command Line Interface (AWS CLI) should be already configured with Administrator permission.](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-welcome.html)
* [Version 1.31.0 of Amazon Cloud Development Kit (AWS CDK) should be installed.](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)
* [Python 3 should be installed](https://www.python.org/downloads/)

In the example, there are two stacks in WorkSpaces folder: one is the AWSManagedAD stack, and the other is AWSWorkSpaces stack.

The brief about 2 stacks is below,
* AWSManagedAD:
    * Create AWS Managed Microsoft AD.
    * Create an Amazon Route 53 private hosted zone and an A record pointing to AWS Managed Microsoft AD.
    * Create an Amazon Elastic Compute Cloud (Amazon EC2) Windows instance for domain user/group management.
    * Create an AWS Systems Manager Parameter and Document that attaches to the Amazon EC2 instance to join AWS Managed Microsoft AD automatically.
    * Create an AWS Lambda function to register WorkSpaces with AWS Managed Microsoft AD.

* AWSWorkSpaces
    * Create an Amazon WorkSpaces for SAP GUI configuration

Setup Process
-------------
(1) Clone my sample repo to your folder in your device and navigate into the folder

```
$ git clone https://github.com/aws-samples/amazon-workspaces-sapgui-sso
```

(2) Create two AWS Secrets Managers secrets. One is the secret for domain admin password, and the other is the pre-created Amazon Amazon EC2 key pair name. The name of the Secret Key is "Key". The password should comply to the AWS Managed Microsoft AD [password rule](https://docs.aws.amazon.com/directoryservice/latest/admin-guide/ms_ad_getting_started_create_directory.html).


(3) Edit cdk.json file to meet your environment

```
1.	{  
2.	  "app": "python3 app.py",  
3.	  "context": {  
4.	      "Account": "<AWS Account ID>",  
5.	      "Region": "<AWS Region>",  
6.	      "Domain_name": "<AD Domain Name>",  
7.	      "Secret_domain_password_arn": "<Secret Manager for AD Password ARN value>",  
8.	      "Instance_type": "<EC2 Instance Type>",  
9.	      "VpcId": "<VPC ID>",  
10.	      "Subnet1": [ "<Piublic Subnet1 ID>", "<The Availability Zone that the subnet locates in>" ],  
11.	      "Subnet2": [ "<Piublic Subnet2 ID>", "<The Availability Zone that the subnet locates in>" ],  
12.	      "Secret_keypair_arn": "<Secret Manager for EC2 Key Value ARN value>",  
13.	      "WorkSpacesUser" : "<NetBIOS\User>",  
14.	      "WorkSpacesBundle": "wsb-8vbljg4r6"  
15.	  }  
16.	}
```

Some parameters explanation below,
-	`Region`: Choose the Region that supports the AWS Directory Service and Amazon WorkSpaces. In this blog, I use the Region in `us-west-2`
-	`Domain_name`: Fill in the preferred domain name for AWS Managed Microsoft AD. I use `test.lab` in this blog.
-	`Secret_domain_password_arn`: Input the secret Amazon Resource Name (ARN) value for domain admin password secret.
-	`Instance_type`: Refer to the [Amazon EC2 Documentation](https://aws.amazon.com/ec2/instance-types/) for the instance type.
-	`Subnet[1|2]`:Fill in the list value for the two subnets in the same VpcId. The former element in the array is the `subnet ID`, and the latter is the `Availability Zone` where the subnet resides.
-   `Secret_keypair_arn`: Input Secret ARN value for the Amazon EC2 key pair secret.
-	`WorkSpacesUser`: Fill in the user name that you would create after the AWS Managed AD is built. The format is `NETBIOS\AD_USER`, in this lab, I used `test\\Hank`
-	`WorkSpacesBundle`: Fill in the default Amazon WorkSpaces bundle ID to deploy SAP GUI. I picked up `wsb-8vbljg4r6`, which is for `Standard Windows 10`.

(4) Install the Python required libraries for cdk

```
$ pip install -r requirement.txt
```

(5) Run the CDK bootstrap on your AWS account

```
$ cdk bootstrap  aws://<AWS_ACCOUNT>/<AWS_REGION>
```

(6) Deploy the AWSManagedAD stack with your AWS profile

```
$ cdk deploy AWSManagedAD --profile <AWS Profile>
```
If you don’t specify AWS profile, the default profile will be used. This stack might take 10-20 minutes to deploy all resources.

(7) Once the AWSManagedAD Stack is deployed, you can login to the Amazon EC2 instance and create a domain user for Amazon WorkSpaces later. Revise the default security group to connect from your local environment to Amazon EC2 instance. Please specify `First Name`, `Last Name` and the `Email` for the user.

(8) Deploy the AWSWorkSpaces stack with specified domain user.

```
$ cdk deploy AWSWorkSpaces --profile <AWS Profile>
```
This stack might take 10 minutes to deploy Amazon WorkSpaces.

(9) Once the Amazon WorkSpaces is built, you can download and install [Amazon WorkSpaces Client](https://clients.amazonworkspaces.com/), fill in the registration code from the Amazon WorkSpaces console and login in with domain user.

LICENSE
-------------
This library is licensed under the MIT-0 License. See the LICENSE file.
