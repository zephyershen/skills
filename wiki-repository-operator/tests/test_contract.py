import copy
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wiki_repository.actions import ACTION_BY_KEY, ACTIONS  # noqa: E402
from wiki_repository.contract import (  # noqa: E402
    EXCLUDED_OPERATIONS,
    MANUAL_OPERATIONS,
    audit_openapi,
)


def complete_openapi():
    specification = {
        "openapi": "3.1.0",
        "info": {"title": "Wiki Repository Platform API", "version": "4.0.0"},
        "paths": {},
    }
    operations = [
        (action.method, action.path, action.scope, action.risk, action.body_required)
        for action in ACTIONS
    ] + [
        (operation.method, operation.path, operation.scope, operation.risk, operation.body_required)
        for operation in MANUAL_OPERATIONS
    ] + [
        (method, path, "", "high", True)
        for method, path in EXCLUDED_OPERATIONS
    ]
    for method, path, scope, risk, body_required in operations:
        operation = {"x-risk-level": risk}
        if scope:
            operation["x-required-scope"] = scope
        if body_required:
            operation["requestBody"] = {"required": True}
        specification["paths"].setdefault(path, {})[method.lower()] = operation
    return specification


class ContractTests(unittest.TestCase):
    def test_current_operator_contract_is_complete(self):
        result = audit_openapi(complete_openapi())
        self.assertTrue(result["compatible"])
        self.assertEqual(result["api_operation_count"], 72)
        self.assertEqual(result["managed_api_operation_count"], 71)
        self.assertEqual(result["covered_api_operation_count"], 71)
        self.assertEqual(result["operator_command_count"], 71)
        self.assertEqual(result["unsupported_operations"], [])
        self.assertEqual(result["unavailable_commands"], [])
        self.assertEqual(result["metadata_mismatches"], [])

    def test_contract_flags_api_risk_drift_and_new_mutation(self):
        specification = copy.deepcopy(complete_openapi())
        specification["paths"]["/projects/{projectId}"]["put"]["x-risk-level"] = "medium"
        specification["paths"]["/future/settings"] = {
            "put": {"x-risk-level": "high", "x-required-scope": "workspace:manage"},
        }

        result = audit_openapi(specification)

        self.assertFalse(result["compatible"])
        self.assertEqual(result["unsupported_operations"], [{"method": "PUT", "path": "/future/settings"}])
        self.assertEqual(result["metadata_mismatches"][0]["command"], "projects.update")
        self.assertEqual(result["metadata_mismatches"][0]["operator"], "high")
        self.assertEqual(result["metadata_mismatches"][0]["api"], "medium")

    def test_known_risk_levels_match_the_production_contract(self):
        self.assertEqual(ACTION_BY_KEY[("projects", "update")].risk, "high")
        self.assertEqual(ACTION_BY_KEY[("people", "user-update")].risk, "medium")
        self.assertTrue(ACTION_BY_KEY[("projects", "update")].body_required)


if __name__ == "__main__":
    unittest.main()
