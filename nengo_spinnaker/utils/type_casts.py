"""Standard typecasts for Nengo on SpiNNaker."""
import rig.type_casts as tp


N_FRAC = 19  # Number of fractional bits

value_to_fix = tp.float_to_fix(True, 32, N_FRAC)
fix_to_value = tp.fix_to_float(True, 32, N_FRAC)

np_to_fix = tp.NumpyFloatToFixConverter(True, 32, N_FRAC)
fix_to_np = tp.NumpyFixToFloatConverter(N_FRAC)
