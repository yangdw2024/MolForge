"""Element-dependent construction estimates in Å; never a geometry optimizer."""
from .elements import get_element

def estimate_bond_length(z1, z2, order=1, aromatic=False):
    """Covalent radius sum for single bonds, empirical contraction for multiple bonds.
    Only a starting geometry/fallback restraint. Charge, hybridization and environment
    require a force field or quantum optimization. Imported coordinates stay untouched.
    """
    a, b = get_element(int(z1)), get_element(int(z2))
    if a is None or b is None:
        raise ValueError("Unknown element in bond length estimate")
    factor = .93 if aromatic else {1:1., 2:.87, 3:.78}.get(int(order), 1.)
    return (a.covalent_radius + b.covalent_radius) * factor
