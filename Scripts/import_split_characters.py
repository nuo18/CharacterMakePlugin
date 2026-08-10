"""Rebuild split characters using one shared Skeleton.

BaseCharacter creates the one project Skeleton. Every body mesh is imported as
a Skeletal Mesh bound to it. Eye, helmet, beard, and every other split part are
imported as Static Meshes.
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

import unreal


SOURCE_ROOT = Path(
    os.environ.get("CHARACTERSET_SOURCE_ROOT", r"E:\Work\CharacterSet\Export")
)
DESTINATION_ROOT = "/Game/Character/Imported"
MASTER_CHARACTER = "BaseCharacter"
REPORT_PATH = Path(unreal.Paths.project_saved_dir()) / "SplitCharacterImportReport.json"


def set_property_if_available(obj, name: str, value) -> None:
    try:
        obj.set_editor_property(name, value)
    except Exception:
        unreal.log_warning(
            f"[SharedSkeletonImport] Unsupported property '{name}'; using default."
        )


def skeletal_options(skeleton=None):
    options = unreal.FbxImportUI()
    set_property_if_available(options, "automated_import_should_detect_type", False)
    set_property_if_available(options, "import_mesh", True)
    set_property_if_available(options, "import_as_skeletal", True)
    set_property_if_available(options, "import_animations", False)
    set_property_if_available(options, "import_materials", True)
    set_property_if_available(options, "import_textures", True)
    set_property_if_available(
        options, "mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH
    )
    set_property_if_available(options, "create_physics_asset", False)
    if skeleton is not None:
        set_property_if_available(options, "skeleton", skeleton)

    data = options.get_editor_property("skeletal_mesh_import_data")
    set_property_if_available(data, "import_morph_targets", True)
    set_property_if_available(data, "preserve_smoothing_groups", True)
    set_property_if_available(data, "use_t0_as_ref_pose", False)
    set_property_if_available(data, "convert_scene", True)
    set_property_if_available(data, "convert_scene_unit", True)
    set_property_if_available(data, "import_meshes_in_bone_hierarchy", False)
    return options


def static_options():
    options = unreal.FbxImportUI()
    set_property_if_available(options, "automated_import_should_detect_type", False)
    set_property_if_available(options, "import_mesh", True)
    set_property_if_available(options, "import_as_skeletal", False)
    set_property_if_available(options, "import_animations", False)
    set_property_if_available(options, "import_materials", True)
    set_property_if_available(options, "import_textures", True)
    set_property_if_available(
        options, "mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH
    )

    data = options.get_editor_property("static_mesh_import_data")
    set_property_if_available(data, "combine_meshes", True)
    set_property_if_available(data, "auto_generate_collision", False)
    set_property_if_available(data, "generate_lightmap_u_vs", True)
    set_property_if_available(data, "convert_scene", True)
    set_property_if_available(data, "convert_scene_unit", True)
    return options


def asset_name(character: str, source_file: Path) -> str:
    if source_file.stem.lower().startswith(character.lower()):
        return source_file.stem
    return f"{character}_{source_file.stem}"


def import_fbx(
    source_file: Path,
    destination: str,
    destination_name: str,
    expected_class,
    options,
):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source_file))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", destination_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    set_property_if_available(task, "replace_existing_settings", True)
    task.set_editor_property("save", False)
    task.set_editor_property("options", options)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported_paths = list(task.get_editor_property("imported_object_paths"))
    matches = []
    for object_path in imported_paths:
        asset = unreal.load_asset(object_path)
        if isinstance(asset, expected_class):
            matches.append(asset)

    if not matches:
        expected_path = f"{destination}/{destination_name}"
        expected = unreal.load_asset(expected_path)
        if isinstance(expected, expected_class):
            matches.append(expected)

    return (matches[0] if matches else None), imported_paths


def split_files(character_dir: Path) -> list[Path]:
    files = sorted(character_dir.glob("*.fbx"), key=lambda path: path.name.lower())
    if any(path.stem.lower().endswith("bodymesh") for path in files):
        suffixes = ("bodymesh", "eye", "helmet", "beard")
        files = [path for path in files if path.stem.lower().endswith(suffixes)]
    return files


def body_file(character_dir: Path, files: list[Path]) -> Path:
    candidates = [path for path in files if path.stem.lower().endswith("bodymesh")]
    if candidates:
        return candidates[0]
    exact = [path for path in files if path.stem.lower() == character_dir.name.lower()]
    if exact:
        return exact[0]
    raise RuntimeError(f"No body mesh FBX found in {character_dir}")


def skeleton_from_mesh(mesh):
    try:
        return mesh.get_editor_property("skeleton")
    except Exception:
        return mesh.get_skeleton()


def import_master(character_dir: Path, report: dict):
    files = split_files(character_dir)
    source_file = body_file(character_dir, files)
    destination = f"{DESTINATION_ROOT}/{character_dir.name}"
    mesh, imported = import_fbx(
        source_file,
        destination,
        asset_name(character_dir.name, source_file),
        unreal.SkeletalMesh,
        skeletal_options(),
    )
    if mesh is None:
        raise RuntimeError(f"Master Skeletal Mesh was not created from {source_file}")
    skeleton = skeleton_from_mesh(mesh)
    if skeleton is None:
        raise RuntimeError(f"Master Skeleton was not created from {source_file}")
    report["characters"].append(
        {
            "character": character_dir.name,
            "status": "ok",
            "parts": [
                {
                    "file": source_file.name,
                    "role": "body_skeletal_master",
                    "assets": imported,
                }
            ],
        }
    )
    return skeleton


def run() -> dict:
    if not SOURCE_ROOT.is_dir():
        raise RuntimeError(f"Split FBX source directory does not exist: {SOURCE_ROOT}")

    character_dirs = sorted(
        [path for path in SOURCE_ROOT.iterdir() if path.is_dir()],
        key=lambda path: path.name.lower(),
    )
    directory_by_name = {path.name.lower(): path for path in character_dirs}
    master_dir = directory_by_name.get(MASTER_CHARACTER.lower())
    if master_dir is None:
        raise RuntimeError(f"Master character directory was not found: {MASTER_CHARACTER}")

    report = {
        "source_root": str(SOURCE_ROOT),
        "destination_root": DESTINATION_ROOT,
        "master_character": MASTER_CHARACTER,
        "characters": [],
        "warnings": [],
        "errors": [],
    }

    if unreal.EditorAssetLibrary.does_directory_exist(DESTINATION_ROOT):
        unreal.log(f"[SharedSkeletonImport] Removing previous {DESTINATION_ROOT}")
        if not unreal.EditorAssetLibrary.delete_directory(DESTINATION_ROOT):
            raise RuntimeError(f"Could not remove previous directory: {DESTINATION_ROOT}")

    unreal.log(f"[SharedSkeletonImport] Importing master {MASTER_CHARACTER}")
    common_skeleton = import_master(master_dir, report)
    common_skeleton_path = common_skeleton.get_path_name()
    report["shared_skeleton"] = common_skeleton_path

    remaining = [path for path in character_dirs if path != master_dir]
    for index, character_dir in enumerate(remaining, start=1):
        files = split_files(character_dir)
        entry = {"character": character_dir.name, "status": "ok", "parts": []}
        unreal.log(
            f"[SharedSkeletonImport] ({index}/{len(remaining)}) {character_dir.name}"
        )
        try:
            primary = body_file(character_dir, files)
            destination = f"{DESTINATION_ROOT}/{character_dir.name}"
            mesh, imported = import_fbx(
                primary,
                destination,
                asset_name(character_dir.name, primary),
                unreal.SkeletalMesh,
                skeletal_options(common_skeleton),
            )
            if mesh is None:
                raise RuntimeError(f"No Skeletal Mesh was created from {primary}")
            actual_skeleton = skeleton_from_mesh(mesh)
            if actual_skeleton is None or actual_skeleton.get_path_name() != common_skeleton_path:
                raise RuntimeError(
                    f"Body did not bind to shared Skeleton: {primary}; "
                    f"actual={actual_skeleton.get_path_name() if actual_skeleton else None}"
                )
            entry["parts"].append(
                {"file": primary.name, "role": "body_skeletal", "assets": imported}
            )

            for part_file in files:
                if part_file == primary:
                    continue
                static_mesh, imported = import_fbx(
                    part_file,
                    destination,
                    asset_name(character_dir.name, part_file),
                    unreal.StaticMesh,
                    static_options(),
                )
                if static_mesh is None:
                    warning = {
                        "character": character_dir.name,
                        "file": part_file.name,
                        "warning": "No Static Mesh was created; source may contain no polygons.",
                    }
                    report["warnings"].append(warning)
                    entry["parts"].append(
                        {
                            "file": part_file.name,
                            "role": "static_empty_skipped",
                            "assets": imported,
                        }
                    )
                    unreal.log_warning(
                        f"[SharedSkeletonImport] Empty/static import skipped: {part_file}"
                    )
                    continue
                entry["parts"].append(
                    {"file": part_file.name, "role": "part_static", "assets": imported}
                )
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = str(exc)
            report["errors"].append(
                {
                    "character": character_dir.name,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            unreal.log_error(f"[SharedSkeletonImport] {character_dir.name}: {exc}")
        report["characters"].append(entry)

    unreal.EditorAssetLibrary.save_directory(
        DESTINATION_ROOT, only_if_is_dirty=False, recursive=True
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    unreal.log(
        f"[SharedSkeletonImport] Finished: {len(report['characters'])} characters, "
        f"{len(report['warnings'])} warnings, {len(report['errors'])} errors."
    )
    return report


try:
    run()
finally:
    unreal.SystemLibrary.quit_editor()
