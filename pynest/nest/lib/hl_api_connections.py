# -*- coding: utf-8 -*-
#
# hl_api_connections.py
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

"""
Functions for connection handling
"""

import numpy

from ..ll_api import *
from .. import pynestkernel as kernel
from .hl_api_helper import *
from .hl_api_nodes import Create
from .hl_api_types import GIDCollection, Connectome, Mask, Parameter
from .hl_api_info import GetStatus
from .hl_api_simulation import GetKernelStatus, SetKernelStatus

__all__ = [
    'CGConnect',
    'CGParse',
    'CGSelectImplementation',
    'Connect',
    'Disconnect',
    'GetConnections',
]


@check_stack
def GetConnections(source=None, target=None, synapse_model=None,
                   synapse_label=None):
    """Return an array of connection identifiers.

    Any combination of source, target, synapse_model and
    synapse_label parameters is permitted.

    Parameters
    ----------
    source : GIDCOllection or list, optional
        Source GIDs, only connections from these
        pre-synaptic neurons are returned
    target : GIDCollection or list, optional
        Target GIDs, only connections to these
        post-synaptic neurons are returned
    synapse_model : str, optional
        Only connections with this synapse type are returned
    synapse_label : int, optional
        (non-negative) only connections with this synapse label are returned

    Returns
    -------
    array:
        Connections as 5-tuples with entries
        (source-gid, target-gid, target-thread, synapse-id, port)

    Notes
    -----
    Only connections with targets on the MPI process executing
    the command are returned.


    Raises
    ------
    TypeError
    """

    params = {}

    if source is not None:
        if isinstance(source, GIDCollection):
            params['source'] = source
        else:
            try:
                params['source'] = GIDCollection(source)
            except kernel.NESTError:
                raise TypeError("source must be GIDCollection or convertible"
                                " to GIDCollection")

    if target is not None:
        if isinstance(target, GIDCollection):
            params['target'] = target
        else:
            try:
                params['target'] = GIDCollection(target)
            except kernel.NESTError:
                raise TypeError("target must be GIDCollection or convertible"
                                " to GIDCollection")

    if synapse_model is not None:
        params['synapse_model'] = kernel.SLILiteral(synapse_model)

    if synapse_label is not None:
        params['synapse_label'] = synapse_label

    sps(params)
    sr("GetConnections")

    conns = spp()

    if isinstance(conns, tuple):
        conns = Connectome(None)

    return conns


def _process_conn_spec(conn_spec):
    if conn_spec is None:
        # Get default conn_spec
        sr('/Connect /conn_spec GetOption')
        return spp()
    elif isinstance(conn_spec, str):
        processed_conn_spec = {'rule': conn_spec}
        return processed_conn_spec
    elif isinstance(conn_spec, dict):
        return conn_spec
    else:
        raise TypeError("conn_spec must be a string or dict")


def _process_syn_spec(syn_spec, conn_spec, prelength, postlength):
    if syn_spec is None:
        return syn_spec
    rule = conn_spec['rule']
    if isinstance(syn_spec, str):
        sps(syn_spec)
        sr("cvlit")
        return spp()
    elif isinstance(syn_spec, dict):
        for key, value in syn_spec.items():
            # if value is a list, it is converted to a numpy array
            if isinstance(value, (list, tuple)):
                value = numpy.asarray(value)

            if isinstance(value, (numpy.ndarray, numpy.generic)):
                if len(value.shape) == 1:
                    if rule == 'one_to_one':
                        if value.shape[0] != prelength:
                            raise kernel.NESTError(
                                "'" + key + "' has to be an array of "
                                "dimension " + str(prelength) + ", a "
                                "scalar or a dictionary.")
                        else:
                            syn_spec[key] = value
                    else:
                        raise kernel.NESTError(
                            "'" + key + "' has the wrong type. "
                            "One-dimensional parameter arrays can "
                            "only be used in conjunction with rule "
                            "'one_to_one'.")

                elif len(value.shape) == 2:
                    if rule == 'all_to_all':
                        if value.shape[0] != postlength or \
                                value.shape[1] != prelength:

                            raise kernel.NESTError(
                                "'" + key + "' has to be an array of "
                                "dimension " + str(postlength) + "x" +
                                str(prelength) +
                                " (n_target x n_sources), " +
                                "a scalar or a dictionary.")
                        else:
                            syn_spec[key] = value.flatten()
                    elif rule == 'fixed_indegree':
                        indegree = conn_spec['indegree']
                        if value.shape[0] != postlength or \
                                value.shape[1] != indegree:
                            raise kernel.NESTError(
                                "'" + key + "' has to be an array of "
                                "dimension " + str(postlength) + "x" +
                                str(indegree) +
                                " (n_target x indegree), " +
                                "a scalar or a dictionary.")
                        else:
                            syn_spec[key] = value.flatten()
                    elif rule == 'fixed_outdegree':
                        outdegree = conn_spec['outdegree']
                        if value.shape[0] != prelength or \
                                value.shape[1] != outdegree:
                            raise kernel.NESTError(
                                "'" + key + "' has to be an array of "
                                "dimension " + str(prelength) + "x" +
                                str(outdegree) +
                                " (n_sources x outdegree), " +
                                "a scalar or a dictionary.")
                        else:
                            syn_spec[key] = value.flatten()
                    else:
                        raise kernel.NESTError(
                            "'" + key + "' has the wrong type. "
                            "Two-dimensional parameter arrays can "
                            "only be used in conjunction with rules "
                            "'all_to_all', 'fixed_indegree' or "
                            "'fixed_outdegree'.")
        # sps(syn_spec)
        return syn_spec
    else:
        raise TypeError("syn_spec must be a string or dict")


def _process_spatial_projections(conn_spec, syn_spec):
    allowed_conn_spec_keys = ['mask',
                              'multapses', 'autapses', 'rule', 'indegree', 'outdegree', 'p', 'use_on_source']
    allowed_syn_spec_keys = ['weight', 'delay']
    for key in conn_spec.keys():
        if key not in allowed_conn_spec_keys:
            raise ValueError(
                "'{}' is not allowed in conn_spec when connecting with mask or kernel".format(key))

    projections = {}
    for key in ['mask']:
        if key in conn_spec:
            projections[key] = conn_spec[key]
    if 'p' in conn_spec:
        projections['kernel'] = conn_spec['p']
    # TODO: change topology names of {mul,aut}apses to be consistent
    if 'multapses' in conn_spec:
        projections['allow_multapses'] = conn_spec['multapses']
    if 'autapses' in conn_spec:
        projections['allow_autapses'] = conn_spec['autapses']
    if syn_spec is not None:
        for key in syn_spec.keys():
            if key not in allowed_syn_spec_keys:
                raise ValueError(
                    "'{}' is not allowed in syn_spec when connecting with mask or kernel".format(key))
        # TODO: change topology names of weights, delays to be consistent
        if 'weight' in syn_spec:
            projections['weights'] = syn_spec['weight']
        if 'delay' in syn_spec:
            projections['delays'] = syn_spec['delay']

    if conn_spec['rule'] == 'fixed_indegree':
        if 'use_on_source' in conn_spec:
            raise ValueError(
                "'use_on_source' can only be set when using pairwise_bernoulli")
        projections['connection_type'] = 'convergent'
        projections['number_of_connections'] = conn_spec['indegree']

    elif conn_spec['rule'] == 'fixed_outdegree':
        if 'use_on_source' in conn_spec:
            raise ValueError(
                "'use_on_source' can only be set when using pairwise_bernoulli")
        projections['connection_type'] = 'divergent'
        projections['number_of_connections'] = conn_spec['outdegree']

    elif conn_spec['rule'] == 'pairwise_bernoulli':
        if ('use_on_source' in conn_spec and
                conn_spec['use_on_source']):
            projections['connection_type'] = 'convergent'
        else:
            projections['connection_type'] = 'divergent'
    else:
        raise kernel.NESTError("When using kernel or mask, the only possible "
                               "connection rules are 'pairwise_bernoulli', "
                               "'fixed_indegree', or 'fixed_outdegree'")
    return projections


def _connect_layers_needed(conn_spec):
    rule_is_bernoulli = conn_spec['rule'] == 'pairwise_bernoulli'
    return ('mask' in conn_spec or
            ('p' in conn_spec and not rule_is_bernoulli) or
            'use_on_source' in conn_spec)


def _connect_spatial(pre, post, projections):
    # Replace python classes with SLI datums
    def fixdict(d):
        d = d.copy()
        for k, v in d.items():
            if isinstance(v, dict):
                d[k] = fixdict(v)
            elif isinstance(v, Mask) or isinstance(v, Parameter):
                d[k] = v._datum
        return d

    projections = fixdict(projections)
    sli_func('ConnectLayers', pre, post, projections)


@check_stack
def Connect(pre, post, conn_spec=None, syn_spec=None,
            return_connectome=False):
    """
    Connect pre nodes to post nodes.

    Nodes in pre and post are connected using the specified connectivity
    (all-to-all by default) and synapse type (static_synapse by default).
    Details depend on the connectivity rule.

    Parameters
    ----------
    pre : GIDCollection
        Presynaptic nodes, as object representing the global IDs of the nodes
    post : GIDCollection
        Postsynaptic nodes, as object representing the global IDs of the nodes
    conn_spec : str or dict, optional
        Specifies connectivity rule, see below
    syn_spec : str or dict, optional
        Specifies synapse model, see below
    model : str or dict, optional
        alias for syn_spec for backward compatibility
    return_connectome: bool
        Specifies whether or not we should return a connectome of pre and post

    Raises
    ------
    kernel.NESTError

    Notes
    -----
    Connect does not iterate over subnets, it only connects explicitly
    specified nodes.

    Connectivity specification (conn_spec)
    --------------------------------------

    Connectivity is specified either as a string containing the name of a
    connectivity rule (default: 'all_to_all') or as a dictionary specifying
    the rule and any mandatory rule-specific parameters (e.g. 'indegree').

    In addition, switches setting permission for establishing
    self-connections ('autapses', default: True) and multiple connections
    between a pair of nodes ('multapses', default: True) can be contained
    in the dictionary. Another switch enables the creation of symmetric
    connections ('symmetric', default: False) by also creating connections
    in the opposite direction.

    Available rules and associated parameters
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - 'all_to_all' (default)
    - 'one_to_one'
    - 'fixed_indegree', 'indegree'
    - 'fixed_outdegree', 'outdegree'
    - 'fixed_total_number', 'N'
    - 'pairwise_bernoulli', 'p'

    Example conn-spec choices
    ~~~~~~~~~~~~~~~~~~~~~~~~~
    - 'one_to_one'
    - {'rule': 'fixed_indegree', 'indegree': 2500, 'autapses': False}
    - {'rule': 'pairwise_bernoulli', 'p': 0.1}

    Synapse specification (syn_spec)
    --------------------------------------

    The synapse model and its properties can be given either as a string
    identifying a specific synapse model (default: 'static_synapse') or
    as a dictionary specifying the synapse model and its parameters.

    Available keys in the synapse specification dictionary are:
    - 'model'
    - 'weight'
    - 'delay'
    - 'receptor_type'
    - any parameters specific to the selected synapse model.

    All parameters are optional and if not specified, the default values
    of the synapse model will be used. The key 'model' identifies the
    synapse model, this can be one of NEST's built-in synapse models
    or a user-defined model created via CopyModel().

    If 'model' is not specified the default model 'static_synapse'
    will be used.

    All other parameters can be scalars, arrays or distributions.
    In the case of scalar parameters, all keys must be doubles
    except for 'receptor_type' which must be initialised with an integer.

    Parameter arrays are available for the rules 'one_to_one',
    'all_to_all', 'fixed_indegree' and 'fixed_outdegree':
    - For 'one_to_one' the array has to be a one-dimensional
      NumPy array with length len(pre).
    - For 'all_to_all' the array has to be a two-dimensional NumPy array
      with shape (len(post), len(pre)), therefore the rows describe the
      target and the columns the source neurons.
    - For 'fixed_indegree' the array has to be a two-dimensional NumPy array
      with shape (len(post), indegree), where indegree is the number of
      incoming connections per target neuron, therefore the rows describe the
      target and the columns the connections converging to the target neuron,
      regardless of the identity of the source neurons.
    - For 'fixed_outdegree' the array has to be a two-dimensional NumPy array
      with shape (len(pre), outdegree), where outdegree is the number of
      outgoing connections per source neuron, therefore the rows describe the
      source and the columns the connections starting from the source neuron
      regardless of the identity of the target neuron.

    Any distributed parameter must be initialised with a further dictionary
    specifying the distribution type ('distribution', e.g. 'normal') and
    any distribution-specific parameters (e.g. 'mu' and 'sigma').

    To see all available distributions, run:
    nest.slirun('rdevdict info')

    To get information on a particular distribution, e.g. 'binomial', run:
    nest.help('rdevdict::binomial')

    Most common available distributions and associated parameters
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    - 'normal' with 'mu', 'sigma'
    - 'normal_clipped' with 'mu', 'sigma', 'low', 'high'
    - 'lognormal' with 'mu', 'sigma'
    - 'lognormal_clipped' with 'mu', 'sigma', 'low', 'high'
    - 'uniform' with 'low', 'high'
    - 'uniform_int' with 'low', 'high'

    Example syn-spec choices
    ~~~~~~~~~~~~~~~~~~~~~~~~~
    - 'stdp_synapse'
    - {'weight': 2.4, 'receptor_type': 1}
    - {'synapse_model': 'stdp_synapse',
       'weight': 2.5,
       'delay': {'distribution': 'uniform', 'low': 0.8, 'high': 2.5},
       'alpha': {
           'distribution': 'normal_clipped', 'low': 0.5,
           'mu': 5.0, 'sigma': 1.0}
      }
    """

    if not isinstance(pre, GIDCollection):
        raise TypeError("Not implemented, presynaptic nodes must be a "
                        "GIDCollection")
    if not isinstance(post, GIDCollection):
        raise TypeError("Not implemented, postsynaptic nodes must be a "
                        "GIDCollection")

    sps(pre)
    sps(post)

    # Converting conn_spec to dict, without putting it on the SLI stack.
    processed_conn_spec = _process_conn_spec(conn_spec)
    # If syn_spec is given, its contents are checked, and if needed converted
    # to the right formats.
    processed_syn_spec = _process_syn_spec(
        syn_spec, processed_conn_spec, len(pre), len(post))

    # In some cases we must connect with ConnectLayers instead.
    if _connect_layers_needed(processed_conn_spec):
        # Check that pre and post are layers
        if pre.spatial is None:
            raise TypeError(
                "Presynaptic GIDCollection must have spatial information")
        if post.spatial is None:
            raise TypeError(
                "Presynaptic GIDCollection must have spatial information")

        # Create the projection dictionary
        spatial_projections = _process_spatial_projections(
            processed_conn_spec, processed_syn_spec)

        # Connect using ConnectLayers
        _connect_spatial(pre, post, spatial_projections)
    else:
        sps(processed_conn_spec)
        if processed_syn_spec is not None:
            sps(processed_syn_spec)
        sr('Connect')

    if return_connectome:
        return GetConnections(pre, post)


@check_stack
def CGConnect(pre, post, cg, parameter_map=None, model="static_synapse"):
    """Connect neurons using the Connection Generator Interface.

    Potential pre-synaptic neurons are taken from pre, potential
    post-synaptic neurons are taken from post. The connection
    generator cg specifies the exact connectivity to be set up. The
    parameter_map can either be None or a dictionary that maps the
    keys "weight" and "delay" to their integer indices in the value
    set of the connection generator.

    This function is only available if NEST was compiled with
    support for libneurosim.

    For further information, see
    * The NEST documentation on using the CG Interface at
      http://nest-simulator.org/connection-generator-interface
    * The GitHub repository and documentation for libneurosim at
      https://github.com/INCF/libneurosim/
    * The publication about the Connection Generator Interface at
      https://doi.org/10.3389/fninf.2014.00043

    Parameters
    ----------
    pre : list or numpy.array
        must contain a list of GIDs
    post : list or numpy.array
        must contain a list of GIDs
    cg : connection generator
        libneurosim connection generator to use
    parameter_map : dict, optional
        Maps names of values such as weight and delay to
        value set positions
    model : str, optional
        Synapse model to use

    Raises
    ------
    kernel.NESTError
    """

    sr("statusdict/have_libneurosim ::")
    if not spp():
        raise kernel.NESTError(
            "NEST was not compiled with support for libneurosim: " +
            "CGConnect is not available.")

    if parameter_map is None:
        parameter_map = {}

    sli_func('CGConnect', cg, pre, post, parameter_map, '/' + model,
             litconv=True)


@check_stack
def CGParse(xml_filename):
    """Parse an XML file and return the corresponding connection
    generator cg.

    The library to provide the parsing can be selected
    by CGSelectImplementation().

    Parameters
    ----------
    xml_filename : str
        Filename of the xml file to parse.

    Raises
    ------
    kernel.NESTError
    """

    sr("statusdict/have_libneurosim ::")
    if not spp():
        raise kernel.NESTError(
            "NEST was not compiled with support for libneurosim: " +
            "CGParse is not available.")

    sps(xml_filename)
    sr("CGParse")
    return spp()


@check_stack
def CGSelectImplementation(tag, library):
    """Select a library to provide a parser for XML files and associate
    an XML tag with the library.

    XML files can be read by CGParse().

    Parameters
    ----------
    tag : str
        XML tag to associate with the library
    library : str
        Library to use to parse XML files

    Raises
    ------
    kernel.NESTError
    """

    sr("statusdict/have_libneurosim ::")
    if not spp():
        raise kernel.NESTError(
            "NEST was not compiled with support for libneurosim: " +
            "CGSelectImplementation is not available.")

    sps(tag)
    sps(library)
    sr("CGSelectImplementation")


@check_stack
def Disconnect(pre, post, conn_spec='one_to_one', syn_spec='static_synapse'):
    """Disconnect pre neurons from post neurons.

    Neurons in pre and post are disconnected using the specified disconnection
    rule (one-to-one by default) and synapse type (static_synapse by default).
    Details depend on the disconnection rule.

    Parameters
    ----------
    pre : GIDCollection
        Presynaptic nodes, given as list of GIDs
    post : GIDCollection
        Postsynaptic nodes, given as list of GIDs
    conn_spec : str or dict
        Disconnection rule, see below
    syn_spec : str or dict
        Synapse specifications, see below

    conn_spec
    ---------
    Apply the same rules as for connectivity specs in the Connect method

    Possible choices of the conn_spec are
    - 'one_to_one'
    - 'all_to_all'

    syn_spec
    --------
    The synapse model and its properties can be inserted either as a
    string describing one synapse model (synapse models are listed in the
    synapsedict) or as a dictionary as described below.

    Note that only the synapse type is checked when we disconnect and that if
    syn_spec is given as a non-empty dictionary, the 'model' parameter must be
    present.

    If no synapse model is specified the default model 'static_synapse'
    will be used.

    Available keys in the synapse dictionary are:
    - 'model'
    - 'weight'
    - 'delay',
    - 'receptor_type'
    - parameters specific to the synapse model chosen

    All parameters are optional and if not specified will use the default
    values determined by the current synapse model.

    'model' determines the synapse type, taken from pre-defined synapse
    types in NEST or manually specified synapses created via CopyModel().

    All other parameters are not currently implemented.

    Notes
    -----
    Disconnect only disconnects explicitly specified nodes.
    """

    sps(pre)
    sps(post)

    if is_string(conn_spec):
        conn_spec = {'rule': conn_spec}
    if is_string(syn_spec):
        syn_spec = {'synapse_model': syn_spec}

    sps(conn_spec)
    sps(syn_spec)

    sr('Disconnect_g_g_D_D')
