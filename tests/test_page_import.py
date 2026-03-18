from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pbi.images import add_image
from pbi.page_import import import_page
from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA


def _make_project(root: Path) -> Project:
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps(
            {
                "$schema": REPORT_SCHEMA,
                "themeCollection": {},
                "layoutOptimization": "None",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


def test_import_page_rewrites_visual_ids_and_group_references() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _make_project(root / "source")
        target = _make_project(root / "target")

        source_page = source.create_page("Source")
        first = source.create_visual(source_page, "cardVisual", x=0, y=0, width=100, height=50)
        second = source.create_visual(source_page, "cardVisual", x=120, y=0, width=100, height=50)
        group = source.create_group(source_page, [first, second], display_name="Cards")

        result = import_page(
            target,
            from_project=source,
            page="Source",
            name="Imported",
        )

        assert result.visual_count == 3
        imported_page = target.find_page("Imported")
        imported_visuals = target.get_visuals(imported_page)
        imported_names = {visual.name for visual in imported_visuals}

        assert len(imported_visuals) == 3
        assert group.name not in imported_names
        child_groups = {
            visual.data["parentGroupName"]
            for visual in imported_visuals
            if visual.data.get("parentGroupName")
        }
        assert child_groups
        assert child_groups <= imported_names


def test_import_page_copies_registered_resources_when_requested() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _make_project(root / "source")
        target = _make_project(root / "target")

        image_path = root / "logo.png"
        image_path.write_bytes(b"fake-image")
        registered_name = add_image(source, image_path)

        source_page = source.create_page("Source")
        visual = source.create_visual(source_page, "image", x=0, y=0, width=100, height=50)
        visual.data.setdefault("visual", {}).setdefault("objects", {})["image"] = [{
            "properties": {
                "source": {
                    "ResourcePackageItem": {
                        "PackageName": "RegisteredResources",
                        "PackageType": 1,
                        "ItemName": registered_name,
                    }
                }
            }
        }]
        visual.save()

        result = import_page(
            target,
            from_project=source,
            page="Source",
            name="Imported",
            include_resources=True,
        )

        assert result.resource_count == 1
        copied_file = target.report_folder / "StaticResources" / "RegisteredResources" / registered_name
        assert copied_file.exists()

        report_data = json.loads((target.definition_folder / "report.json").read_text(encoding="utf-8"))
        items = report_data["resourcePackages"][0]["resourcePackage"]["items"]
        assert any(item["name"] == registered_name for item in items)
