import mock
import nengo
import pytest
from six import iteritems

from nengo_spinnaker.builder.builder import (Model, ObjectPort, Signal,
                                             InputPort)
from nengo_spinnaker.operators import Filter
from nengo_spinnaker.utils.model import (remove_childless_filters,
                                         remove_sinkless_signals,
                                         remove_passthrough_nodes)
import nengo_spinnaker


def test_remove_sinkless_signals():
    """Signals with no sink should be removed."""
    # Create a netlist including some signals with no sinks, these signals
    # should be removed.
    o1 = mock.Mock(name="O1")
    o2 = mock.Mock(name="O2")

    # Create 4 signals (2 associated with connections, 2 not)
    cs1 = Signal(ObjectPort(o1, None), ObjectPort(o2, None), None)
    cs2 = Signal(ObjectPort(o1, None), [], None)
    ss1 = Signal(ObjectPort(o1, None), ObjectPort(o2, None), None)
    ss2 = Signal(ObjectPort(o1, None), [], None)

    # Create two mock connections
    c1 = mock.Mock(name="Connection 1")
    c2 = mock.Mock(name="Connection 2")

    # Create the model
    model = Model()
    model.extra_operators = [o1, o2]
    model.connections_signals = {c1: cs1, c2: cs2}
    model.extra_signals = [ss1, ss2]

    # Remove sinkless signals
    remove_sinkless_signals(model)

    # Check that signals were removed as necessary
    assert model.connections_signals == {c1: cs1}
    assert model.extra_signals == [ss1]


def test_remove_childless_filters():
    """Filter operators which don't transmit to anything, and their incoming
    signals, can be removed.
    """
    # Create a netlist including some filters that do and don't transmit to
    # other objects, check that all the filters which don't connect to anything
    # are removed.
    #
    #          -S1---             F3
    #        /       \       S4  ^  \  S5
    #       /        v          /    v
    #     F1         O1 +S3-> F2     F5
    #      ^        /   |      \     ^
    #      \       /    |   S4  v   /  S6
    #       \-S2---     v        F4
    #                  O2
    #
    # F1 should remain, O1 and O2 should be untouched and F2..5 should be
    # removed.  S1 and S2 should be unchanged, S3 should have F2 removed from
    # its sinks and S4..6 should be removed entirely.

    # Create the filter operators
    f1 = mock.Mock(name="F1", spec=Filter)
    f2 = mock.Mock(name="F2", spec=Filter)
    f3 = mock.Mock(name="F3", spec=Filter)
    f4 = mock.Mock(name="F4", spec=Filter)
    f5 = mock.Mock(name="F5", spec=Filter)

    # The other operator
    o1 = mock.Mock(name="O1")
    o2 = mock.Mock(name="O2")

    # Create some objects which map to some of the operators
    oo1 = mock.Mock()
    of3 = mock.Mock()

    # Create the signals
    s1 = Signal(ObjectPort(f1, None), ObjectPort(o1, None), None)
    s2 = Signal(ObjectPort(o1, None), ObjectPort(f1, None), None)
    s3 = Signal(ObjectPort(o1, None), [ObjectPort(f2, None),
                                       ObjectPort(o2, None)], None)
    s4 = Signal(ObjectPort(f2, None), [ObjectPort(f3, None),
                                       ObjectPort(f4, None)], None)
    s5 = Signal(ObjectPort(f3, None), ObjectPort(f5, None), None)
    s6 = Signal(ObjectPort(f4, None), ObjectPort(f5, None), None)

    # Create some connections which map to the signals
    cs4 = mock.Mock()
    cs5 = mock.Mock()

    # Create the model
    model = Model()
    model.object_operators = {
        oo1: o1,
        of3: f3,
    }
    model.extra_operators = [f1, f2, f4, f5]
    model.connections_signals = {
        cs4: s4,
        cs5: s5,
    }
    model.extra_signals = [s1, s2, s3, s6]

    # Perform the optimisation
    remove_childless_filters(model)

    # Check that objects have been removed
    assert model.object_operators == {oo1: o1}
    assert model.extra_operators == [f1]
    assert model.connections_signals == {}
    assert model.extra_signals == [s1, s2, s3]
    assert [s.obj for s in s3.sinks] == [o2]


def test_remove_passnodes():
    """Test that passnodes can be correctly removed from a network.

    We create and build the following model and then ensure that the pass node
    is removed related connections are moved as required.

        E1 -->\    /---> E5
               \  /
        E2 -->\    /---> E6
                PN
        E3 -->/  | \---> E7
               / |\
        E4 -->/  | \---> E8
                 \
                  \----> P1

    Should become:

        E1 -+----------> E5
             \
        E2 ---+--------> E6
              \
        E3 ----+-------> E7
                \
        E4 ------+-----> E8
                  \
                   \---> P1
    """
    # Create the Nengo model
    with nengo.Network() as network:
        # Create the Ensembles
        e1_4 = [nengo.Ensemble(100, 1) for _ in range(4)]
        e5_8 = [nengo.Ensemble(100, 1) for _ in range(4)]

        # Add the passnode
        pn = nengo.Node(size_in=4)

        # And the probe
        p1 = nengo.Probe(pn)

        # Finally, add the connections
        connections = list()
        connections.extend(nengo.Connection(e1_4[n], pn[n], synapse=None) for
                           n in range(4))
        connections.extend(nengo.Connection(pn[n], e5_8[n], synapse=None) for
                           n in range(4))

    # Build this into a model
    nioc = nengo_spinnaker.builder.node.NodeIOController()
    model = Model()
    model.build(network, **nioc.builder_kwargs)

    # Apply the passnode remover to the model
    remove_passthrough_nodes(model)

    # Check that this was indeed done...
    # None of the original connections should be in the model
    # connections->signals mapping, but they should remain in the parameters
    # dictionary.
    for conn in connections:
        assert conn not in model.connections_signals
        assert conn in model.params

    # E5..8 should have one input each, this should be a signal from their
    # partner in E1..4 and should be paired with a signal with an appropriate
    # transform.  The signal should be of weight 1.
    for i, ens in enumerate(e5_8):
        # Get the object simulating the ensemble
        lif = model.object_operators[ens]

        # Check the incoming signals
        sigs = model.get_signals_connections_to_object(lif)[InputPort.standard]
        assert len(sigs) == 1

        for sig, conns in iteritems(sigs):
            # Check the connection is sane
            assert len(conns) == 1
            conn = conns[0]
            assert conn.pre_obj is e1_4[i]

            # Check that the signal is sane
            assert sig.weight == 1
            assert sig.source.obj is model.object_operators[e1_4[i]]

    # P1 should receive many signals, one per pre-ensemble, and these should be
    # associated with similar connections.
    probe_op = model.object_operators[p1]
    sigs =\
        model.get_signals_connections_to_object(probe_op)[InputPort.standard]
    assert len(sigs) == 4
    for sig, conns in iteritems(sigs):
        # Check the connection is sane
        assert len(conns) == 1
        conn = conns[0]
        assert conn.pre_obj in e1_4

        # Check that the signal is sane
        # assert sig.weight == 1
        assert sig.source.obj is model.object_operators[conn.pre_obj]


@pytest.mark.parametrize("signal_in", ["input", "output"])
def test_remove_passthrough_nodes_aborts_multisink(signal_in):
    """Check that removing passthrough Nodes does nothing in the case that
    there is an input signal with multiple sinks.
    """
    # Create a Nengo model
    with nengo.Network() as network:
        a = nengo.Ensemble(500, 5)
        b = nengo.Node(size_in=5)
        c = nengo.Ensemble(100, 5)

        a_b = nengo.Connection(a, b)
        b_c = nengo.Connection(b, c)

    # Build this into a model
    nioc = nengo_spinnaker.builder.node.NodeIOController()
    model = Model()
    model.build(network, **nioc.builder_kwargs)

    if signal_in == "input":
        # Add an extra sink to the signal associated with a->b
        model.connections_signals[a_b].sinks.append(ObjectPort(None, None))
    else:
        # Add an extra sink to the signal associated with b->c
        model.connections_signals[b_c].sinks.append(ObjectPort(None, None))

    # Check that removing passthrough Nodes does nothing
    remove_passthrough_nodes(model)
    assert b in model.object_operators
    assert a_b in model.connections_signals
    assert b_c in model.connections_signals


def test_remove_passthrough_nodes_aborts_merge_filters():
    """Check that removing passthrough Nodes does nothing in the case that
    there is a synapse on both the incoming and the outgoing connection.
    """
    # Create a Nengo model
    with nengo.Network() as network:
        a = nengo.Ensemble(500, 5)
        b = nengo.Node(size_in=5)
        c = nengo.Ensemble(100, 5)

        a_b = nengo.Connection(a, b, synapse=0.005)
        b_c = nengo.Connection(b, c, synapse=0.001)

    # Build this into a model
    nioc = nengo_spinnaker.builder.node.NodeIOController()
    model = Model()
    model.build(network, **nioc.builder_kwargs)

    # Check that removing passthrough Nodes does nothing
    remove_passthrough_nodes(model)
    assert b in model.object_operators
    assert a_b in model.connections_signals
    assert b_c in model.connections_signals
