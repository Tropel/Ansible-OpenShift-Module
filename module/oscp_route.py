#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: oscp_route
short_description: Open Shift Route
description:
    - Handles route in Open Shift Enterprise.
    - The module is using the REST Interface to interact with the Open Shift Master.

author: "Robert Forsström, @mtekkie"
notes:
    - In order for this module to work a service account needs to be created.
    - It is up to you to decide which project it should have access to.
    - In the following example it is given the maximum permissions (cluster admin):
    - oc project default
    - oc create serviceaccount ansible
    - oadm policy add-cluster-role-to-user cluster-admin system:serviceaccount:default:ansible
    - To get the JWT token to authenticate to the API:
    - oc describe serviceaccount ansible
    - Find the relevant token.
    - oc describe secret ansible-token-xxxx

requirements:
    - A authentication token for an Open Shift Service Account.

options:
    state:
        description:
            - If it should be present or absent.
        required: true
        default: present
        choices: [present, absent]
        version_added: 1.0

    master_url:
        description:
            - URL to Open Shift Master server
        required: true
        default: null

    auth_token:
        description:
            - Security Token token for a service account.
        required: true
        default: null

    project:
        description:
            - Open Shift Project name
        required: true
        default: null

    name:
        description:
            - Name of route
        required: true
        default: null

    host:
        description:
            - Host is an alias/DNS that points to the service.
            - Optional Must follow DNS952 subdomain conventions.
        required: false
        default: 'deployconfigname'-'project'.'wildcarddomain'

    path:
        description:
            - Path that the router watches for, to route traffic for to the service.
            - Optional
        required: false
        default: null
    to:
        description:
            - To is an object the route points to.
            - Only the Service kind is allowed, and it will be defaulted to Service.
            - v1.RouteTargetReference
        required: true
        default: null

    alternateBackends:
        description:
            - AlternateBackends is an extension of the 'to' field.
            - If more than one service needs to be pointed to, then use this
            - field. Use the weight field in RouteTargetReference object to
            - specify relative preference
            - List of v1.RouteTargetReference
        required: false
        default: null

    port:
        description:
            - If specified, the port to be used by the router.
            - Most routers will use all endpoints exposed by the service by default
            - set this value to instruct routers which port to use.
            - v1.RoutePort
        required: False
        default: null
    tls:
        description:
            -TLS provides the ability to configure certificates
            - and termination for the route
            - v1.TLSConfig
        required: false
        default: null
'''



EXAMPLES = '''
- oscp_route:
    master_url: https://funnybunny.middleware.se:8443
    auth_token: eyJhbGciOiJSUzI1NiIsInR5.....
    project: masterminder
    name: inboundroute
    host: maniac.apps.middleware.se
    to:
      kind: Service
      name: serv-ice
    port:
      targetPort: robert-port-1
    tls:
      termination: edge
      insecureEdgeTerminationPolicy: Redirect
'''

RETURN = '''
'''



import urllib2
import ssl
import json
from string import Template
import types

## Constants:
API_BASE = "/oapi/v1"


def main():
    module = AnsibleModule(
        argument_spec = dict(
            state                   = dict(default='present', choices=['present', 'absent']),
            master_url              = dict(required=True),
            auth_token              = dict(required=True),
            project                 = dict(required=True),
            name                    = dict(required=True),
            host                    = dict(required=False),
            path                    = dict(required=False),
            to                      = dict(required=True, type='dict'),
            alternateBackends       = dict(required=False, type='list', default=[]),
            port                    = dict(required=False, type='dict', default={}),
            tls                     = dict(required=False, type='dict', default={})
        )
    )

    SERVICE  = API_BASE+"/namespaces/"+module.params.get("project")+"/routes/"
    PATH = SERVICE+module.params.get("name")

    TEMPLATE = '''
    {
      "kind": "Route",
      "apiVersion": "v1",
      "metadata": {
        "name": "$name",
        "namespace": "$project"
      },
      "spec": {
        "host": "$host",
        "to": $to,
        "port": $port,
        "tls": $tls,
        "alternateBackends": $alternateBackends,
        "path" : "$path"
      }
    }
    '''

    cfg = template_to_dict(TEMPLATE, module.params)
    should_be = clean_dict_from_nones(cfg)
    should_be_json = dict_to_json(should_be)

    try:
        current_json = http_get(PATH, module)
        current = json_to_dict(current_json)
        # Only If resource exists on server ...
        if module.params.get("state") == "absent":
            http_delete(PATH,module)
            module.exit_json(changed=True)
            return

        if compliant (current,should_be):
            module.exit_json(changed=False, ansible_facts=current)
        else:
            #Set resourceVersion in should_be.
            should_be['metadata']['resourceVersion']=current['metadata']['resourceVersion']
            result = http_put(PATH, module, dict_to_json(should_be))
            facts = json_to_dict(result)
            module.exit_json(changed=True, ansible_facts=facts)

    except urllib2.HTTPError as sc:

        if not has_project(module):
            module.fail_json(msg="Project does not exist")

        if sc.code == 404 and module.params.get("state") == "present":
            result = http_post(SERVICE, module, should_be_json)
            facts = json_to_dict(result)
            module.exit_json(changed=True, ansible_facts=facts)

        if sc.code == 404 and module.params.get("state") == "absent":
            module.exit_json(changed=False)


########################### Helper functions ###################################
#
# This section contains helper fuctions v20170106:2
#
################################################################################


def dict_to_json(in_dict):
    return json.dumps(in_dict)

def json_to_dict(in_json):
    return json.loads(in_json)

# Cleans up dict. Removes entries that have a value of None.
# Mainly used for cleaning up Templates with have vaules that are not set in the
# module.
# Consumes Dict, Returns Dict.
def clean_dict_from_nones(in_dict):
    return __clean_dict_from_nones_recursive(in_dict)


def __clean_dict_from_nones_recursive(in_dict):
    new_dict = dict ()
    for key in in_dict:
        if isinstance(in_dict[key], dict):
            ret=__clean_dict_from_nones_recursive(in_dict[key])
            if len(ret) > 0:
                new_dict[key] = ret
        elif isinstance(in_dict[key], list):
            if len(in_dict[key]) > 0:
                new_dict[key]=in_dict[key]
        elif in_dict[key] != 'None':
            new_dict[key]=in_dict[key]
    return new_dict

def template_to_dict(template, params):
    # First: Create vaild json-strings from dicts that are nested.
    fixed_params= dict();
    for key in params:
        if isinstance(params[key], dict) or isinstance(params[key], list) :
            fixed_params[key] = json.dumps(params[key])
        else:
            fixed_params[key] = params[key]

    jsonified = Template(template).substitute(fixed_params)
    #print jsonified
    return json.loads(jsonified)


# Takes two Python Dicts and compare them
# If the should_be objects value is different then the is_obj then
# the function returns False
# is_obj MAY contain more attributes then should_be. Thoose are never checked.
# Returns True or False.
def compliant (is_obj, should_be):
    if not isinstance(is_obj, dict):
        return False

    is_compliant = True
    for key in should_be:
        # Recursiv processing of dicts.
        if isinstance(should_be[key], dict):
            is_compliant = compliant (is_obj[key], should_be[key])
            if not is_compliant:
                return False
        else:
            # Check values.
                #print "Checking if should_be[key] != is_obj[key]: " + should_be[key] +":"+ is_obj[key]
            if should_be[key] != is_obj[key]:
                    is_compliant = False
                    return False
    return is_compliant

# Checks if project exist.
# Returns True/False
def has_project(module):
    try:
        path = "/oapi/v1/projects/"+module.params["project"]
        http_get(path, module)
    except urllib2.HTTPError as sc:
        if sc.code == 404:
            return False
        else:
            raise
    return True

def get_message_from_v1status(body):
    if isinstance(body,list):
        body=''.join(body)
    #json to obj.
    status = json.loads(body)
    return status['message']

#####################################
# HTTP Helper functions
# Takes cares of GET/POST/PUT/DELETE
# Generic fault-handling for standard errors in OSE.
# Code: Fail:
# 401   Authentication issues
# 409   Conflict, Can not update resouce
#
#####################################
def http_get(path, module):
    return http_request("GET", path, module, "")

def http_post(path, module, data):
    return http_request("POST", path, module, data)

def http_put(path, module, data):
    return http_request("PUT", path, module, data)

def http_delete(path, module):
    return http_request("DELETE", path, module, "")

def http_request(method, path, module, data):
    try:
        url = module.params.get("master_url")+path
        #opener = urllib2.build_opener(urllib2.HTTPHandler)
        headers = {'Authorization': 'Bearer '+module.params.get("auth_token")}

        #GET
        req = urllib2.Request(url=url, headers=headers)

        if method == "DELETE":
            req = urllib2.Request(url=url, headers=headers)
            req.get_method = lambda: 'DELETE'

        elif method == "POST":
            req = urllib2.Request(url=url, headers=headers, data=data)
            req.add_header("Content-Type", "application/json")

        elif method == "PUT":
            req = urllib2.Request(url=url, headers=headers, data=data)
            req.add_header("Content-Type", "application/json")
            req.get_method = lambda: 'PUT'

        gcontext = ssl.SSLContext(ssl.PROTOCOL_TLSv1)

        content = urllib2.urlopen(req, context=gcontext).read()
        return content

    except urllib2.HTTPError as sc:
        if sc.code == 401:
            msg = "Open Shift authenication error (401):"
            msg = msg + get_message_from_v1status(sc.readlines())
            module.fail_json(msg=msg)

        elif sc.code == 409:
            msg = "Open Shift Reports Conflict (409). Can't update resource:"
            msg = msg + get_message_from_v1status(sc.readlines())
            module.fail_json(msg=msg)
        elif sc.code == 422:
            msg = "Open Shift Reports Unprocessable Enitiy (422):"
            msg = msg + get_message_from_v1status(sc.readlines())
            module.fail_json(msg=msg)
        elif sc.code == 400:
            msg = "Open Shift Reports Bad Request (400):"
            msg = msg + get_message_from_v1status(sc.readlines())
            module.fail_json(msg=msg)
        else:
            raise sc

    except urllib2.URLError as ue:
        module.fail_json(msg="Open Shift Master is unreachable. Check connection and master_url setting.")
########################### End of helper functions ############################


from ansible.module_utils.basic import AnsibleModule
if __name__ == '__main__':
    main()