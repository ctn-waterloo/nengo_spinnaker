"""LIF Ensemble

Takes an intermediate representation of a LIF ensemble and returns a vertex and
appropriate callbacks to load and prepare the ensemble for simulation on
SpiNNaker.  The build method also manages the partitioning of the ensemble into
appropriate sized slices.
"""

import collections
import nengo
import numpy as np
from rig.machine import Cores, SDRAM
from six import iteritems
import struct

from nengo.connection import LearningRule

from nengo_spinnaker.builder.builder import InputPort, netlistspec, OutputPort
from nengo_spinnaker.builder.ports import EnsembleInputPort
from nengo_spinnaker.regions.filters import (
    make_filter_regions, make_filters, FilterRegion, FilterRoutingRegion
)
from .. import regions
from nengo_spinnaker.netlist import VertexSlice
from nengo_spinnaker import partition_and_cluster as partition
from nengo_spinnaker.utils.application import get_application
from nengo_spinnaker.utils import type_casts as tp


class EnsembleLIF(object):
    """Controller for an ensemble of LIF neurons."""
    def __init__(self, ensemble):
        """Create a new LIF ensemble controller."""
        self.ensemble = ensemble
        self.direct_input = np.zeros(ensemble.size_in)
        self.local_probes = list()

    def make_vertices(self, model, n_steps):  # TODO remove n_steps
        """Construct the data which can be loaded into the memory of a
        SpiNNaker machine.
        """
        # Build encoders, gain and bias regions
        params = model.params[self.ensemble]

        # Combine the encoders with the gain and then convert to S1615 before
        # creating the region.
        encoders_with_gain = params.encoders * params.gain[:, np.newaxis]
        self.encoders_region = regions.MatrixRegion(
            tp.np_to_fix(encoders_with_gain),
            sliced_dimension=regions.MatrixPartitioning.rows
        )

        # Combine the direct input with the bias before converting to S1615 and
        # creating the region.
        bias_with_di = params.bias + np.dot(encoders_with_gain,
                                            self.direct_input)
        assert bias_with_di.ndim == 1
        self.bias_region = regions.MatrixRegion(
            tp.np_to_fix(bias_with_di),
            sliced_dimension=regions.MatrixPartitioning.rows
        )

        # Convert the gains to S1615 before creating the region
        self.gain_region = regions.MatrixRegion(
            tp.np_to_fix(params.gain),
            sliced_dimension=regions.MatrixPartitioning.rows
        )

        # Extract all the filters from the incoming connections
        incoming = model.get_signals_connections_to_object(self)
        
        # Filter out modulatory incoming connections
        modulatory_incoming = { port:signal 
                               for (port, signal) in iteritems(incoming) 
                               if isinstance(port, LearningRule) }
        
        self.input_filters, self.input_filter_routing = make_filter_regions(
            incoming[InputPort.standard], model.dt, True,
            model.keyspaces.filter_routing_tag, width=self.ensemble.size_in
        )
        self.inhib_filters, self.inhib_filter_routing = make_filter_regions(
            incoming[EnsembleInputPort.global_inhibition], model.dt, True,
            model.keyspaces.filter_routing_tag, width=1
        )

        # Extract all the decoders for the outgoing connections and build the
        # regions for the decoders and the regions for the output keys.
        outgoing = model.get_signals_connections_from_object(self)
        decoders, output_keys = \
            get_decoders_and_keys(model, outgoing[OutputPort.standard])
        
        # Create, initially empty, PES region
        self.pes_region = PESRegion()
        
        # Loop through modulatory incoming connections
        mod_filters = list()
        mod_keyspace_routes = list()
        for (l, m) in iteritems(modulatory_incoming):
            # Extract the learning rule's types
            l_type = l.learning_rule_type
            
            # If this learning rule is PES
            if isinstance(l_type, nengo.PES):
                # If a matching outgoing learnt connection is found
                if l in outgoing:
                    # Cache what will be this PES rule's 
                    # filter and decoder index
                    filter_index = len(mod_filters)
                    decoder_offset = decoders.shape[1]
                    
                    # Create new decoders and output keys for learnt 
                    # connection and add to object's list
                    learnt_decoders, learnt_output_keys = \
                        get_decoders_and_keys(model, outgoing[l])
                    print decoders.shape, learnt_decoders.shape
                    decoders = np.hstack((decoders, learnt_decoders))
                    output_keys.extend(learnt_output_keys)
                    
                    print "Creating %u learnt decoders" % learnt_decoders.shape[1]
                    
                    # Create modulatory filter and add to list
                    filters, keyspace_routes = make_filters(m, minimise=False)
                    mod_filters.extend(filters)
                    mod_keyspace_routes.extend(keyspace_routes)
                    
                    print "Creating %u modulatory filters" % len(mod_filters)
                    
                    # Add a new learning rule to the PES region
                    self.pes_region.learning_rules.append(
                        PESLearningRule(learning_rate=l_type.learning_rate,
                                        filter_index=filter_index,
                                        decoder_offset=decoder_offset))
                else:
                    raise ValueError(
                        "Ensemble %s has incoming modulatory PES "
                        "connection, but no corresponding outgoing "
                        "learnt connection" % self.ensemble.label
                    )
            else:
                raise NotImplementedError(
                    "SpiNNaker currently only supports PES learning."
                )
        
        # Create modulatory filter and routing regions
        self.mod_filters = FilterRegion(mod_filters, model.dt)
        self.mod_filter_routing = FilterRoutingRegion(mod_keyspace_routes, 
                                                      model.keyspaces.filter_routing_tag)
  
        # Now decoder is fully built, extract size
        size_out = decoders.shape[1]

        self.decoders_region = regions.MatrixRegion(
            tp.np_to_fix(decoders / model.dt),
            sliced_dimension=regions.MatrixPartitioning.rows
        )
        self.output_keys_region = regions.KeyspacesRegion(
            output_keys, fields=[regions.KeyField({'cluster': 'cluster'})]
        )

        # Create the regions list
        self.regions = [
            SystemRegion(self.ensemble.size_in,
                         size_out,
                         model.machine_timestep,
                         self.ensemble.neuron_type.tau_ref,
                         self.ensemble.neuron_type.tau_rc,
                         model.dt,
                         False  # Base this on whether we have a probe attached
                         ),
            self.bias_region,
            self.encoders_region,
            self.decoders_region,
            self.output_keys_region,
            self.input_filters,
            self.input_filter_routing,
            self.inhib_filters,
            self.inhib_filter_routing,
            self.gain_region,
            self.mod_filters,
            self.mod_filter_routing,
            self.pes_region,
            None,
            None  # Will be the spike recording region
        ]

        # Partition the ensemble and get a list of vertices to load to the
        # machine.  We can expect to be DTCM or CPU bound, so the SDRAM bound
        # can be quite lax to allow for lots of data probing.
        # TODO: Include other DTCM usage
        # TODO: Include CPU usage constraint
        self.vertices = list()
        sdram_constraint = partition.Constraint(8*2**20)  # Max 8MiB
        dtcm_constraint = partition.Constraint(64*2**10, .75)  # 75% of 64KiB
        constraints = {
            sdram_constraint: lambda s: regions.utils.sizeof_regions(
                self.regions, s),
            dtcm_constraint: lambda s: regions.utils.sizeof_regions(
                self.regions, s),
        }
        for sl in partition.partition(slice(0, self.ensemble.n_neurons),
                                      constraints):
            resources = {
                Cores: 1,
                SDRAM: regions.utils.sizeof_regions(self.regions, sl),
            }
            vsl = VertexSlice(sl, get_application("ensemble"), resources)
            self.vertices.append(vsl)

        # Return the vertices and callback methods
        return netlistspec(self.vertices, self.load_to_machine)

    def load_to_machine(self, netlist, controller):
        """Load the ensemble data into memory."""
        # For each slice
        for vertex in self.vertices:
            # Layout the slice of SDRAM we have been given
            region_memory = regions.utils.create_app_ptr_and_region_files(
                netlist.vertices_memory[vertex], self.regions, vertex.slice)

            # Write in each region
            for region, mem in zip(self.regions, region_memory):
                if region is None:
                    pass
                elif region is self.output_keys_region:
                    self.output_keys_region.write_subregion_to_file(
                        mem, vertex.slice, cluster=vertex.cluster)
                else:
                    region.write_subregion_to_file(mem, vertex.slice)

    def before_simulation(self, netlist, controller, simulator, n_steps):
        """Load data for a specific number of steps to the machine."""
        # TODO When supported by executables
        raise NotImplementedError

    def after_simulation(self, netlist, controller, simulator, n_steps):
        """Retrieve data from a simulation and ensure."""
        raise NotImplementedError
        # If we have probed the spikes then retrieve the spike data and store
        # it in the simulator data.


class SystemRegion(collections.namedtuple(
    "SystemRegion", "n_input_dimensions, n_output_dimensions, "
                    "machine_timestep, t_ref, t_rc, dt, probe_spikes")):
    """Region of memory describing the general parameters of a LIF ensemble."""

    def sizeof(self, vertex_slice=slice(None)):
        """Get the number of bytes necessary to represent this region of
        memory.
        """
        return 8 * 4  # 8 words

    sizeof_padded = sizeof

    def write_subregion_to_file(self, fp, vertex_slice):
        """Write the system region for a specific vertex slice to a file-like
        object.
        """
        n_neurons = vertex_slice.stop - vertex_slice.start
        data = struct.pack(
            "<8I",
            self.n_input_dimensions,
            self.n_output_dimensions,
            n_neurons,
            self.machine_timestep,
            int(self.t_ref // self.dt),
            tp.value_to_fix(self.dt / self.t_rc),
            (0x1 if self.probe_spikes else 0x0),
            1
        )
        fp.write(data)

PESLearningRule = collections.namedtuple(
    "PESLearningRule", "learning_rate, filter_index, decoder_offset")

class PESRegion(regions.Region):
    """Region representing parameters for PES learning rules.
    """
    def __init__(self):
        self.learning_rules = []
    
    def sizeof(self, *args):
        return 4 + (len(self.learning_rules) * 12)

    def write_subregion_to_file(self, fp, vertex_slice):
        # Write number of learning rules
        fp.write(struct.pack("<I", len(self.learning_rules)))
        
        # Write learning rules
        for l in self.learning_rules:
            data = struct.pack(
                "<iII",
                tp.value_to_fix(l.learning_rate),
                l.filter_index,
                l.decoder_offset
            )
            fp.write(data)


def get_decoders_and_keys(model, signals_connections):
    """Get a combined decoder matrix and a list of keys to use to transmit
    elements decoded using the decoders.
    """
    decoders = list()
    keys = list()

    # For each signal with a single connection we save the decoder and generate
    # appropriate keys
    for signal, connections in iteritems(signals_connections):
        assert len(connections) == 1
        decoder = model.params[connections[0]].decoders
        transform = model.params[connections[0]].transform

        decoder = np.dot(transform, decoder.T)
        decoders.append(decoder.T)

        for i in range(decoder.shape[0]):
            keys.append(signal.keyspace(index=i))

    # Stack the decoders
    if len(decoders) > 0:
        decoders = np.hstack(decoders)
    else:
        decoders = np.array([[]])

    return decoders, keys
