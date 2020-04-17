# -*- coding: utf-8 -*-
#
# hl_api_server.py
#
# This file is part of NEST.
#
# Copyright (C) 2004 The NEST Initiative
#
# NEST is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# NEST is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with NEST.  If not, see <http://www.gnu.org/licenses/>.

import array
import inspect
import io
import numpy as np
import os
import sys

import nest

import flask
from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from werkzeug import abort, Response


__all__ = [
    'app'
]


app = Flask(__name__)
CORS(app)


@app.route('/exec', methods=['GET', 'POST'])
@cross_origin()
def route_exec():
    """ Route to execute script in Python.
    """
    args, kwargs = get_arguments(request)
    with Capturing() as stdout:
        try:
            source = kwargs.get('source', '')
            globals = {'__builtins__': None}
            locals = {
              'list': list,
              'nest': nest,
              'np': np,
              'print': print,
              'set': set,
            }
            exec(source, globals, locals)
            response = {}
            if 'return' in kwargs:
                if isinstance(kwargs['return'], list):
                    return_data = {}
                    for variable in kwargs['return']:
                        return_data[variable] = locals.get(variable, None)
                else:
                    return_data = locals.get(kwargs['return'], None)
                response['data'] = nest.hl_api.serializable(return_data)
            response['stdout'] = '\n'.join(stdout)
            return jsonify(data)
        except nest.kernel.NESTError as e:
            abort(Response(getattr(e, 'errormessage'), 400))
        except Exception as e:
            abort(Response(str(e), 400))


# --------------------------
# RESTful API
# --------------------------

nest_calls = dir(nest)
nest_calls = list(filter(lambda x: not x.startswith('_'), nest_calls))
nest_calls.sort()


@app.route('/api', methods=['GET'])
@cross_origin()
def route_api():
    """ Route to list call functions in NEST.
    """
    return jsonify(nest_calls)


@app.route('/api/<call>', methods=['GET', 'POST'])
@cross_origin()
def route_api_call(call):
    """ Route to call function in NEST.
    """
    args, kwargs = get_arguments(request)
    data = api_client(call, *args, **kwargs)
    return jsonify(data)


# ----------------------
# Helpers for the server
# ----------------------

class Capturing(list):
    """ Monitor stdout contents i.e. print.
    """
    def __enter__(self):
        self._stdout = sys.stdout
        sys.stdout = self._stringio = io.StringIO()
        return self

    def __exit__(self, *args):
        self.extend(self._stringio.getvalue().splitlines())
        del self._stringio    # free up some memory
        sys.stdout = self._stdout


def get_arguments(request):
    """ Get arguments from the request.
    """
    args, kwargs = [], {}
    if request.is_json:
        json = request.get_json()
        if isinstance(json, list):
            args = json
        elif isinstance(json, dict):
            kwargs = json
            if 'args' in kwargs:
                args = list(kwargs.pop('args'))
    elif len(request.form) > 0:
        if 'args' in request.form:
            args = list(request.form.getlist('args'))
        else:
            kwargs = request.form.to_dict()
    elif len(request.args) > 0:
        if 'args' in request.args:
            args = list(request.args.getlist('args'))
        else:
            kwargs = request.args.to_dict()
    return args, kwargs


def get_or_error(func):
    """ Wrapper to get data and status.
    """
    def func_wrapper(call, *args, **kwargs):
        try:
            return func(call,  *args, **kwargs)
        except nest.kernel.NESTError as e:
            abort(Response(getattr(e, 'errormessage'), 409))
        except Exception as e:
            abort(Response(str(e), 400))
    return func_wrapper


def NodeCollection(call, args, kwargs):
    """ Get Node Collection as arguments for NEST functions.
    """
    objectnames = ['nodes', 'source', 'target', 'pre', 'post']
    paramKeys = list(inspect.signature(call).parameters.keys())
    args = [nest.NodeCollection(arg) if (paramKeys[idx] in objectnames) else arg for (idx, arg) in enumerate(args)]
    for (key, value) in kwargs.items():
        if key in objectnames:
            kwargs[key] = nest.NodeCollection(value)
    return args, kwargs


def serialize(call, args, kwargs):
    """ Serialize arguments with keywords for call functions in NEST.
    """
    args, kwargs = NodeCollection(call, args, kwargs)
    if call.__name__.startswith('Set'):
        status = {}
        if call.__name__ == 'SetDefaults':
            status = nest.GetDefaults(kwargs['model'])
        elif call.__name__ == 'SetKernelStatus':
            status = nest.GetKernelStatus()
        elif call.__name__ == 'SetStructuralPlasticityStatus':
            status = nest.GetStructuralPlasticityStatus(kwargs['params'])
        elif call.__name__ == 'SetStatus':
            status = nest.GetStatus(kwargs['nodes'])
        for key, val in kwargs['params'].items():
            if key in status:
                kwargs['params'][key] = type(status[key])(val)
    return args, kwargs


@get_or_error
def api_client(call, *args, **kwargs):
    """ API Client to call function in NEST.
    """
    call = getattr(nest, call)
    if callable(call):
        if kwargs.get('inspect', None) == 'getdoc':
            response = inspect.getdoc(call)
        elif kwargs.get('inspect', None) == 'getsource':
            response = inspect.getsource(call)
        else:
            args, kwargs = serialize(call, args, kwargs)
            response = call(*args, **kwargs)
    else:
        response = call
    return nest.hl_api.serializable(response)
