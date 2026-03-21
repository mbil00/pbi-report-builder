from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import (
    RoleMember,
    RoleSpec,
    RoleTablePermission,
    SemanticModel,
    add_role_member,
    clear_role_table_filter,
    create_role,
    set_role_table_filter,
)
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from tests.cli_regressions_support import make_project, write_model_table


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "real-report-fixtures"
MODEL_HEAVY_DIR = FIXTURE_ROOT / "report-02-model-heavy"
MODEL_HEAVY_PBIP = MODEL_HEAVY_DIR / "02-model-heavy.pbip"


def _write_model(root: Path, content: str) -> Path:
    definition = root / "Sample.SemanticModel" / "definition"
    definition.mkdir(parents=True, exist_ok=True)
    path = definition / "model.tmdl"
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class RoleModelTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> None:
        make_project(root)
        _write_model(
            root,
            """
model Model
\tref table Sales
\tref table Department
            """,
        )
        write_model_table(
            root,
            "Sales.tmdl",
            """
table Sales
\tmeasure Revenue = SUM ( Sales[Amount] )
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
            """,
        )
        write_model_table(
            root,
            "Department.tmdl",
            """
table Department
\tcolumn DepartmentCode
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: DepartmentCode
            """,
        )

    def test_create_and_load_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)

            name, changed = create_role(
                root,
                "Finance Readers",
                RoleSpec(
                    model_permission="read",
                    table_permissions=[
                        RoleTablePermission(
                            table="Department",
                            filter_expression="Department[DepartmentCode] = \"FIN\"",
                        )
                    ],
                    members=[RoleMember(name="finance@example.com")],
                ),
            )
            self.assertTrue(changed)
            self.assertEqual(name, "Finance Readers")

            model = SemanticModel.load(root)
            role = model.find_role("Finance Readers")
            self.assertEqual(role.model_permission, "read")
            self.assertEqual(role.table_permissions[0].table, "Department")
            self.assertEqual(role.members[0].name, "finance@example.com")

    def test_role_mutations_update_members_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_model_project(root)
            create_role(root, "Finance Readers", RoleSpec(model_permission="read"))

            _, _, changed = set_role_table_filter(
                root,
                "Finance Readers",
                "Department",
                "Department[DepartmentCode] = \"FIN\"",
            )
            self.assertTrue(changed)
            _, _, changed = add_role_member(
                root,
                "Finance Readers",
                RoleMember(name="finance@example.com", member_type="group"),
            )
            self.assertTrue(changed)
            _, _, changed = clear_role_table_filter(root, "Finance Readers", "Department")
            self.assertTrue(changed)

            role = SemanticModel.load(root).find_role("Finance Readers")
            self.assertEqual(role.members[0].member_type, "group")
            self.assertEqual(role.table_permissions, [])

    def test_model_export_and_apply_round_trip_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            self._make_model_project(source)
            create_role(
                source,
                "Finance Readers",
                RoleSpec(
                    model_permission="read",
                    table_permissions=[
                        RoleTablePermission(
                            table="Department",
                            filter_expression="Department[DepartmentCode] = \"FIN\"",
                        )
                    ],
                    members=[
                        RoleMember(name="finance@example.com"),
                        RoleMember(name="finance-group@example.com", member_type="group"),
                    ],
                ),
            )

            exported = yaml.safe_load(export_model_yaml(source))
            self.assertIn("roles", exported)
            self.assertEqual(
                exported["roles"]["Finance Readers"]["filters"]["Department"],
                "Department[DepartmentCode] = \"FIN\"",
            )

            target = Path(tmp) / "target"
            self._make_model_project(target)
            result = apply_model_yaml(target, yaml.safe_dump(exported, sort_keys=False))
            self.assertEqual(result.errors, [])
            self.assertEqual(result.roles_created, ["Finance Readers"])

            round_tripped = yaml.safe_load(export_model_yaml(target))
            self.assertEqual(round_tripped["roles"], exported["roles"])


class RoleCliTests(unittest.TestCase):
    def _make_model_project(self, root: Path) -> Path:
        make_project(root)
        _write_model(
            root,
            """
model Model
\tref table Department
            """,
        )
        write_model_table(
            root,
            "Department.tmdl",
            """
table Department
\tcolumn DepartmentCode
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: DepartmentCode
            """,
        )
        return root / "Sample.pbip"

    def test_cli_role_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            pbip = self._make_model_project(Path(tmp))

            create_result = runner.invoke(
                app,
                ["model", "role", "create", "Finance Readers", "--project", str(pbip)],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            set_result = runner.invoke(
                app,
                ["model", "role", "set", "Finance Readers", "permission=readRefresh", "--project", str(pbip)],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            filter_result = runner.invoke(
                app,
                [
                    "model",
                    "role",
                    "filter",
                    "set",
                    "Finance Readers",
                    "Department",
                    "Department[DepartmentCode] = \"FIN\"",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(filter_result.exit_code, 0, filter_result.stdout)

            member_result = runner.invoke(
                app,
                [
                    "model",
                    "role",
                    "member",
                    "create",
                    "Finance Readers",
                    "finance@example.com",
                    "--type",
                    "group",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(member_result.exit_code, 0, member_result.stdout)

            get_result = runner.invoke(
                app,
                ["model", "role", "get", "Finance Readers", "--json", "--project", str(pbip)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            parsed = json.loads(get_result.stdout)
            self.assertEqual(parsed["modelPermission"], "readRefresh")
            self.assertEqual(parsed["filters"][0]["table"], "Department")
            self.assertEqual(parsed["members"][0]["type"], "group")

            clear_result = runner.invoke(
                app,
                ["model", "role", "filter", "clear", "Finance Readers", "Department", "--project", str(pbip)],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            delete_member_result = runner.invoke(
                app,
                [
                    "model",
                    "role",
                    "member",
                    "delete",
                    "Finance Readers",
                    "finance@example.com",
                    "--force",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(delete_member_result.exit_code, 0, delete_member_result.stdout)

            delete_role_result = runner.invoke(
                app,
                ["model", "role", "delete", "Finance Readers", "--force", "--project", str(pbip)],
            )
            self.assertEqual(delete_role_result.exit_code, 0, delete_role_result.stdout)


class RealRoleFixtureTests(unittest.TestCase):
    def test_model_heavy_fixture_role_commands_and_export(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            copied_root = Path(tmp) / MODEL_HEAVY_DIR.name
            shutil.copytree(MODEL_HEAVY_DIR, copied_root)
            pbip = copied_root / MODEL_HEAVY_PBIP.name

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "role",
                    "create",
                    "Department Finance",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            filter_result = runner.invoke(
                app,
                [
                    "model",
                    "role",
                    "filter",
                    "set",
                    "Department Finance",
                    "Department",
                    "Department[Division] = \"Corporate\"",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(filter_result.exit_code, 0, filter_result.stdout)

            member_result = runner.invoke(
                app,
                [
                    "model",
                    "role",
                    "member",
                    "create",
                    "Department Finance",
                    "finance@example.com",
                    "--project",
                    str(pbip),
                ],
            )
            self.assertEqual(member_result.exit_code, 0, member_result.stdout)

            get_result = runner.invoke(
                app,
                ["model", "role", "get", "Department Finance", "--json", "--project", str(pbip)],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            parsed = json.loads(get_result.stdout)
            self.assertEqual(parsed["filters"][0]["table"], "Department")
            self.assertEqual(parsed["members"][0]["name"], "finance@example.com")

            exported = yaml.safe_load(export_model_yaml(copied_root))
            self.assertIn("roles", exported)
            self.assertIn("Department Finance", exported["roles"])
