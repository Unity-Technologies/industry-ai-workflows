"""Read-only walk of the live Asset Transformer session.

Written for the Asset Transformer MCP `run_python` tool. Because the scene is
stateful across tool calls, run this first when you don't know what's currently
loaded. It mutates nothing — safe to run any time.

Prints, for the root and each occurrence in its subtree: id, name, triangle
count, and (for the whole model) the axis-aligned bounding box.
"""

from pxz import scene


def walk(root: int) -> list[int]:
    """Breadth-first list of every occurrence under `root` (root included)."""
    out: list[int] = []
    stack = [root]
    while stack:
        occ = stack.pop()
        out.append(occ)
        stack.extend(scene.getChildren(occ))
    return out


root = scene.getRoot()
occurrences = walk(root)

total_tris = scene.getPolygonCount([root], asTriangleCount=True)
print(f"root={root}  occurrences={len(occurrences)}  total_triangles={total_tris}")

aabb = scene.getAABB([root])
print(f"AABB: {aabb}")

# Per-occurrence detail (cap the print so huge assemblies don't flood stdout).
for occ in occurrences[:50]:
    name = scene.getOccurrenceName(occ)
    tris = scene.getPolygonCount([occ], asTriangleCount=True)
    print(f"  [{occ}] {name!r}  tris={tris}")

if len(occurrences) > 50:
    print(f"  ... {len(occurrences) - 50} more")
