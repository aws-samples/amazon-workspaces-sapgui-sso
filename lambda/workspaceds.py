#
#  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#  SPDX-License-Identifier: MIT-0
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy of this
#  software and associated documentation files (the "Software"), to deal in the Software
#  without restriction, including without limitation the rights to use, copy, modify,
#  merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
#  INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
#  PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
#  OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#  SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 

import json
import boto3
import os
import cfnresponse
import logging
import threading

client = boto3.client('workspaces')
responseStr = {'Status' : {}}

def handler(event, context):

    status = cfnresponse.SUCCESS
    try:
        if event['RequestType'] == 'Delete':
            client.deregister_workspace_directory(
                DirectoryId = os.environ['DIRECTORY_ID']
            )
            responseStr['Status']['LambdaFunction'] = "Deregister Successfully"

        else:
            client.register_workspace_directory(
                DirectoryId= os.environ['DIRECTORY_ID'],
                EnableWorkDocs = False
            )
            responseStr['Status']['LambdaFunction'] = "Register Successfully"

    except Exception as e:
        logging.error('Exception: %s' % e, exc_info=True)
        responseStr['Status']['LambdaFunction'] = str(e)
        status = cfnresponse.FAILED

    finally:
        cfnresponse.send(event, context, status, {'Status':json.dumps(responseStr)}, None)
