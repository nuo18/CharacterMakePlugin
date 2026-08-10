"""Verify the shared-Skeleton/static-part import layout."""

import json
from collections import Counter
from pathlib import Path

import unreal


ROOT = "/Game/Character/Imported"
REPORT_PATH = Path(unreal.Paths.project_saved_dir()) / "SplitCharacterVerification.json"

registry = unreal.AssetRegistryHelpers.get_asset_registry()
registry.wait_for_completion()
asset_data_list = registry.get_assets_by_path(ROOT, recursive=True)
class_counts = Counter()
body_meshes = []
static_meshes = []

for asset_data in asset_data_list:
    class_name = str(asset_data.asset_class_path.asset_name)
    class_counts[class_name] += 1
    asset = unreal.load_asset(asset_data.package_name)
    if isinstance(asset, unreal.SkeletalMesh):
        try:
            skeleton = asset.get_editor_property("skeleton")
        except Exception:
            skeleton = asset.get_skeleton()
        body_meshes.append(
            {
                "mesh": asset.get_path_name(),
                "skeleton": skeleton.get_path_name() if skeleton else None,
                "materials": len(asset.get_editor_property("materials")),
            }
        )
    elif isinstance(asset, unreal.StaticMesh):
        static_meshes.append(
            {
                "mesh": asset.get_path_name(),
                "materials": len(asset.get_editor_property("static_materials")),
            }
        )

skeletons = sorted({item["skeleton"] for item in body_meshes if item["skeleton"]})
unexpected_skeletal_parts = [
    item["mesh"]
    for item in body_meshes
    if not (
        item["mesh"].split(".")[-1].lower().endswith("bodymesh")
        or item["mesh"].split(".")[-1].lower() == "basecharacter"
    )
]
unexpected_static_bodies = [
    item["mesh"]
    for item in static_meshes
    if item["mesh"].split(".")[-1].lower().endswith("bodymesh")
]

report = {
    "root": ROOT,
    "asset_class_counts": dict(sorted(class_counts.items())),
    "body_meshes": body_meshes,
    "static_meshes": static_meshes,
    "unique_body_skeletons": skeletons,
    "missing_body_skeletons": [
        item["mesh"] for item in body_meshes if not item["skeleton"]
    ],
    "unexpected_skeletal_parts": unexpected_skeletal_parts,
    "unexpected_static_bodies": unexpected_static_bodies,
}
REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
unreal.log(
    f"[SharedSkeletonVerification] Bodies={len(body_meshes)}, "
    f"StaticParts={len(static_meshes)}, Skeletons={len(skeletons)}"
)
unreal.SystemLibrary.quit_editor()
