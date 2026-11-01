"""Prueba mínima del paquete RADICH sin dependencias externas."""

import radich


def test_radich_package_imports():
    assert radich.__name__ == "radich"
