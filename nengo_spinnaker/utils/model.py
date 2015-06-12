"""Model Optimisations
"""
from __future__ import absolute_import

import itertools
import nengo
from nengo.utils.builder import full_transform
import numpy as np
from six import iteritems, itervalues

from nengo_spinnaker.operators import Filter


def remove_sinkless_signals(model):
    """Remove all Signals which do not have any sinks from a
    :py:class:`~nengo_spinnaker.builder.Model`.
    """
    # Create a list of signals to remove by iterating through the signals which
    # are related to connections and finding any with no sinks.
    sinkless_signals = [(c, s) for c, s in iteritems(model.connections_signals)
                        if len(s.sinks) == 0]

    # Now remove all sinkless signals
    for conn, sig in sinkless_signals:
        model.connections_signals.pop(conn)

    # Create a list of signals to remove by finding signals which are not
    # related to connections and which have no sinks.
    sinkless_signals = [s for s in model.extra_signals if len(s.sinks) == 0]

    # Now remove all sinkless signals
    for sig in sinkless_signals:
        model.extra_signals.remove(sig)


def remove_childless_filters(model):
    """Remove all Filter operators which do not transmit to anything from a
    :py:class:`~nengo_spinnaker.builder.Model`.

    Transmitting values to a filter which then doesn't forward them is a waste
    of network bandwidth. This method optimises out all filters which do not
    transmit to at least one other operator. This method will not remove cycles
    of Filters which have no output.
    """
    # We loop through removing filters that aren't connected to anything so
    # that we can deal with the case:
    #
    #     Filter -> Filter -> Filter -> Filter
    #
    # Which should result in the removal of all of the above filters. We break
    # as soon as there are no more childless filters.
    while True:
        # Childless Filters are those in EITHER the dictionary of object
        # operators or the set of extra operators which have no outgoing
        # signals.
        childless_filters = [
            (k, v) for k, v in
            itertools.chain(iteritems(model.object_operators),
                            ((None, v) for v in model.extra_operators)) if
            (isinstance(v, Filter) and  # It's a filter
             model.get_signals_connections_from_object(v) == {})  # Unconnected
        ]

        if not childless_filters:
            # If there are no childless filters then we have nothing to do
            break

        # Remove each of the childless filters in turn.
        for obj, filt in childless_filters:
            # Remove the filter from the list of sinks of each of the signals
            # which target it.
            for sig in itertools.chain(itervalues(model.connections_signals),
                                       model.extra_signals):
                sinks = [s for s in sig.sinks if s.obj is filt]
                for sink in sinks:
                    sig.sinks.remove(sink)

            # Remove the Filter operator itself
            if obj is None:
                model.extra_operators.remove(filt)
            else:
                model.object_operators.pop(obj)

        # Removing filters from the lists of sinks of signals may produce
        # signals which have no sinks, we should remove these as it will allow
        # us to find further filters with no children.
        remove_sinkless_signals(model)


def remove_passthrough_nodes(model):
    """Remove passthrough Nodes from the model."""
    # Find and remove each passthrough Node in turn.  To do this we take all of
    # the connections feeding in to the passthrough Node and combine them with
    # the connections leaving the passthrough Node.  We also pair the sources
    # and sinks of the signals associated with the connections.
    for obj, op in iteritems(model.object_operators):
        # If the object is not a Node, or not a passthrough Node then we move
        # on to the next object.
        # NOTE: These lines are tested but continue is optimised out.
        if (not isinstance(obj, nengo.Node) or  # pragma: no branch
                obj.output is not None):
            continue  # pragma: no cover

        # The object is a passthrough Node, so we get the list of all incoming
        # signals and connections and all outgoing signals and connections.  If
        # there is anything odd we don't bother dealing with this passthrough
        # Node and move onto the next.
        incoming_connections_signals = list()
        valid = True
        for sig, conns in itertools.chain(
                *(iteritems(sc) for sc in itervalues(
                    model.get_signals_connections_to_object(op)))):
            # We're happy ONLY in cases that there is a pairing of ONE signal
            # to ONE connection and there is only ONE sink for the signal.
            if len(conns) != 1 or len(sig.sinks) != 1:
                valid = False
                break

            # Just add the pair of signal and connection to the list of
            # incoming signals and connections.
            incoming_connections_signals.append((sig, conns[0]))

        if not valid:
            continue

        outgoing_connections_signals = list()
        for sig, conns in itertools.chain(
                *(iteritems(sc) for sc in itervalues(
                    model.get_signals_connections_from_object(op)))):
            # We're happy ONLY in cases that there is a pairing of ONE signal
            # to ONE connection and there is only ONE sink for the signal.
            if len(conns) != 1 or len(sig.sinks) != 1:
                valid = False
                break

            # Just add the pair of signal and connection to the list of
            # incoming signals and connections.
            outgoing_connections_signals.append((sig, conns[0]))

        if not valid:
            continue

        # Try to combine all connections and signals. Multiply the transforms
        # together to find out what the final transform would be; if this is
        # zero (a not uncommon occurrence) then don't bother adding the new
        # signal/connection.  If any of the combinations are not possible then
        # abort this process (e.g., combining synapses).
        new_connections = list()
        for (in_sig, in_conn) in incoming_connections_signals:
            for (out_sig, out_conn) in outgoing_connections_signals:
                # If one of the synapses is None then we can continue
                if (in_conn.synapse is not None and
                        out_conn.synapse is not None):
                    valid = False
                    break

                # If the combination of the transforms is zero then we don't
                # bother adding a new signal or connection to the model.
                new_transform = np.dot(
                    full_transform(out_conn),
                    full_transform(in_conn)
                )
                if np.all(new_transform == 0):
                    continue

                # Create a new connection to add this to the list of
                # connections to add.
                new_connections.append(
                    nengo.Connection(
                        in_conn.pre_obj, out_conn.post_obj,
                        function=in_conn.function,
                        synapse=in_conn.synapse or out_conn.synapse,
                        transform=new_transform,
                        add_to_container=False
                    )
                )

            if not valid:
                break

        if not valid:
            continue

        # Remove all the incoming and outgoing connections and signals and then
        # build all the new connections.
        for (in_sig, in_conn) in incoming_connections_signals:
            model.connections_signals.pop(in_conn)

        for (out_sig, out_conn) in outgoing_connections_signals:
            model.connections_signals.pop(out_conn)

        # Build all the new connections
        for connection in new_connections:
            model.make_connection(connection)
