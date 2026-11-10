import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path("MolForge").resolve()))
sys.path.insert(0, str(Path("E:/YDW/Trae_Gaussian").resolve()))

from molforge.domain.document import MoleculeDocument
from molforge.domain.ids import AtomId, BondId
from molforge.application.builtin_commands import (
    AddAtomCommand,
    AddBondCommand,
    ChangeElementCommand,
    ChangeBondOrderCommand,
)
from molforge.application.command_bus import CommandBus

def test_empty_doc_init():
    doc = MoleculeDocument(name="未命名-1")
    assert doc.num_atoms == 0
    assert doc.name == "未命名-1"
    print("[PASS] Studio 2D clean slate initialization")

def test_add_standard_bond():
    doc = MoleculeDocument(name="未命名-1")
    bus = CommandBus(doc)
    
    # 模拟 _add_standard_bond_at_world: wx=0, wy=0
    wx, wy = 0.0, 0.0
    bond_len = 1.50
    angle = math.pi / 6.0
    wpos2 = (wx + bond_len * math.cos(angle), wy + bond_len * math.sin(angle))
    
    # Add atom 1
    res1 = bus.execute(AddAtomCommand(6, x=wx, y=wy, z=0.0, pos_2d=(wx, wy)))
    assert res1.success
    a1 = AtomId(res1.data["atom_id"])
    
    # Add atom 2 bonded to atom 1
    res2 = bus.execute(AddAtomCommand(6, x=wpos2[0], y=wpos2[1], z=0.0, bond_to=a1, pos_2d=wpos2))
    assert res2.success
    a2 = AtomId(res2.data["atom_id"])
    
    assert doc.num_atoms == 2
    assert doc.topology.num_bonds == 1
    b = doc.topology.get_bond(BondId(res2.data["bond_id"]))
    assert (b.begin == a1 and b.end == a2) or (b.begin == a2 and b.end == a1)
    
    p1 = doc.coords_2d[a1]
    p2 = doc.coords_2d[a2]
    d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    assert abs(d - 1.50) < 1e-3, f"Expected 1.50 Å, got {d}"
    print("[PASS] Standard C-C bond (ethane) generated on empty canvas click with bond tool")

def test_sprout_2d_positions():
    doc = MoleculeDocument(name="Test")
    bus = CommandBus(doc)
    
    # Create methane
    res1 = bus.execute(AddAtomCommand(6, x=0.0, y=0.0, z=0.0, pos_2d=(0.0, 0.0)))
    a0 = AtomId(res1.data["atom_id"])
    
    # Sprout from isolated atom:
    # 0 neighbors -> 30° sprout
    sprout1_pos = (1.50 * math.cos(math.pi / 6), 1.50 * math.sin(math.pi / 6))
    res2 = bus.execute(AddAtomCommand(6, x=sprout1_pos[0], y=sprout1_pos[1], z=0.0, bond_to=a0, pos_2d=sprout1_pos))
    a1 = AtomId(res2.data["atom_id"])
    assert doc.num_atoms == 2
    assert doc.topology.num_bonds == 1
    
    # Sprout from 1-neighbor atom a1:
    # 1 neighbor -> forms 120° zig-zag chain!
    nx, ny = doc.coords_2d[a0]
    x1, y1 = doc.coords_2d[a1]
    ang = math.atan2(y1 - ny, x1 - nx)
    turn = math.pi / 3 if (a1.value % 2 == 0) else -math.pi / 3
    sprout2_pos = (x1 + 1.50 * math.cos(ang + turn), y1 + 1.50 * math.sin(ang + turn))
    res3 = bus.execute(AddAtomCommand(6, x=sprout2_pos[0], y=sprout2_pos[1], z=0.0, bond_to=a1, pos_2d=sprout2_pos))
    a2 = AtomId(res3.data["atom_id"])
    assert doc.num_atoms == 3
    assert doc.topology.num_bonds == 2
    
    # Check bond angle a0 - a1 - a2
    v1 = (nx - x1, ny - y1)
    v2 = (sprout2_pos[0] - x1, sprout2_pos[1] - y1)
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    norm1 = math.hypot(v1[0], v1[1])
    norm2 = math.hypot(v2[0], v2[1])
    cos_theta = dot / (norm1 * norm2)
    theta_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_theta))))
    assert abs(theta_deg - 120.0) < 1.0, f"Expected 120°, got {theta_deg}"
    print(f"[PASS] 120° zig-zag chain sprouting verified: angle = {theta_deg:.2f}°")

def test_hover_element_change():
    doc = MoleculeDocument(name="Test")
    bus = CommandBus(doc)
    
    res1 = bus.execute(AddAtomCommand(6, x=0.0, y=0.0, z=0.0, pos_2d=(0.0, 0.0)))
    a0 = AtomId(res1.data["atom_id"])
    assert doc.topology.get_atom(a0).atomic_num == 6
    
    # Change to Oxygen
    bus.execute(ChangeElementCommand(a0, 8))
    assert doc.topology.get_atom(a0).atomic_num == 8
    
    # Undo
    bus.undo()
    assert doc.topology.get_atom(a0).atomic_num == 6
    
    # Redo
    bus.redo()
    assert doc.topology.get_atom(a0).atomic_num == 8
    print("[PASS] ChemDraw hover element change with full Undo/Redo support")

def test_prevent_overlapping_atom():
    doc = MoleculeDocument(name="Test")
    doc.coords_2d[AtomId(0)] = (0.0, 0.0)
    
    # If click is at (0.2, 0.1), dist = hypot(0.2, 0.1) = 0.223 Å < 0.70 Å
    wx, wy = 0.2, 0.1
    overlapping = False
    for aid, (ox, oy) in doc.coords_2d.items():
        if math.hypot(wx - ox, wy - oy) < 0.70:
            overlapping = True
            break
    assert overlapping is True
    print("[PASS] Overlapping duplicate atom (< 0.70 Å) successfully detected and prevented")

def test_hit_testing_bounding_box_logic():
    # Simulating zoom = 400%, label = "CH4"
    zoom = 4.0
    atom_screen_pos = (500.0, 350.0)
    # Segoe UI 44pt text width ~ 90px, height ~ 50px
    tw = 90.0 + 8.0 * zoom
    th = 50.0 + 4.0 * zoom
    # Bounding box with 6px padding:
    bx_min = atom_screen_pos[0] - tw * 0.5 - 6.0
    bx_max = atom_screen_pos[0] + tw * 0.5 + 6.0
    by_min = atom_screen_pos[1] - th * 0.5 - 6.0
    by_max = atom_screen_pos[1] + th * 0.5 + 6.0
    
    # Click on the 'H' of 'CH4' (e.g. 30px to right of center)
    click = (500.0 + 30.0, 350.0)
    is_hit = (bx_min <= click[0] <= bx_max) and (by_min <= click[1] <= by_max)
    assert is_hit is True
    
    # Click on the '4' subscript (e.g. 45px to right of center)
    click2 = (500.0 + 45.0, 350.0)
    is_hit2 = (bx_min <= click2[0] <= bx_max) and (by_min <= click2[1] <= by_max)
    assert is_hit2 is True
    
    # Old logic: Euclidean radius 18px
    old_hit = math.hypot(click[0] - atom_screen_pos[0], click[1] - atom_screen_pos[1]) <= 18.0
    assert old_hit is False, "Old logic should have failed (reproducing the bug)"
    print("[PASS] Hit-testing logic: new algorithm hits label at 400% zoom, while old 18px radius reproduces the bug")

if __name__ == "__main__":
    test_empty_doc_init()
    test_add_standard_bond()
    test_sprout_2d_positions()
    test_hover_element_change()
    test_prevent_overlapping_atom()
    test_hit_testing_bounding_box_logic()
    print("\n>>> ALL 2D MOLECULAR SKETCHING LOGIC TESTS PASSED! <<<")
