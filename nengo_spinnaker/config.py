"""Nengo/SpiNNaker specific configuration."""
import nengo
from nengo.params import BoolParam, DictParam, NumberParam, Parameter
from rig import place_and_route as par

from .simulator import SpiNNakerSimulator


def add_spinnaker_params(config):
    """Add SpiNNaker specific parameters to a configuration object."""
    # Add simulator parameters
    config.configures(SpiNNakerSimulator)

    config[SpiNNakerSimulator].set_param(
        "placer", CallableParameter(default=par.place))
    config[SpiNNakerSimulator].set_param(
        "placer_kwargs", DictParam(default={}))

    config[SpiNNakerSimulator].set_param(
        "allocater", CallableParameter(default=par.allocate))
    config[SpiNNakerSimulator].set_param(
        "allocater_kwargs", DictParam(default={}))

    config[SpiNNakerSimulator].set_param(
        "router", CallableParameter(default=par.route))
    config[SpiNNakerSimulator].set_param(
        "router_kwargs", DictParam(default={}))

    # Add function_of_time parameters to Nodes
    config[nengo.Node].set_param("function_of_time", BoolParam(default=False))
    config[nengo.Node].set_param("function_of_time_period",
                                 NumberParam(default=None, optional=True))


class CallableParameter(Parameter):
    """Parameter which only accepts callables."""
    def validate(self, instance, callable_obj):
        if not callable(callable_obj):
            raise ValueError(
                "must be callable, got type {}".format(type(callable_obj))
            )
