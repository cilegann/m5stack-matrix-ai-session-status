"""Import USB control directly with: from control import set_state."""
from .matrix_control import MatrixController, detect_port, set_state

__all__ = ['MatrixController', 'detect_port', 'set_state']
