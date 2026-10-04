"""Browser-camera Flask bridge for Hazard Lens.

The service deliberately reuses cv_engine's pose estimator and fall state
machine instead of introducing a second fall-detection implementation.
"""
