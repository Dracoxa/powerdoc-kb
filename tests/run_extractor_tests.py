from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app


class Upload:
    def __init__(self, path: Path):
        self.path = path
        self.name = path.name

    def getvalue(self) -> bytes:
        return self.path.read_bytes()


def parse_sample(name: str) -> dict:
    doc = app.parse_upload(Upload(ROOT / "test_docs" / name))
    return app.extract_knowledge(doc)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_topology_sample_builds_power_system_model() -> None:
    payload = parse_sample("sample_space_power_topology.txt")
    system = payload["power_system"]
    check(system["schema"] == "aerospace_power_system.v1", "schema mismatch")
    check(len(system["topology_scheme"]["features"]) >= 5, "too few topology features")
    check(len(system["metrics"]) >= 8, "too few metrics")
    check(len(system["constraints"]) >= 5, "too few constraints")


def test_deliverables_sample_extracts_file_list() -> None:
    payload = parse_sample("sample_space_power_deliverables.txt")
    deliverables = payload["power_system"]["deliverables"]
    check(len(deliverables) >= 10, "too few deliverables")
    check(any("FMEA" in item["name"] for item in deliverables), "missing FMEA deliverable")
    check(any(item["category"] == "分系统设计" for item in deliverables), "missing subsystem design deliverables")


def test_constraints_sample_keeps_system_constraints_grouped() -> None:
    payload = parse_sample("sample_space_power_constraints.txt")
    constraints = payload["power_system"]["constraints"]
    names = {item["name"] for item in constraints}
    check("火工品母线" in names, "missing pyro bus constraint")
    check("阶跃负载特性" in names, "missing step-load constraint")
    check("磁特性" in names, "missing magnetic constraint")


if __name__ == "__main__":
    tests = [
        test_topology_sample_builds_power_system_model,
        test_deliverables_sample_extracts_file_list,
        test_constraints_sample_keeps_system_constraints_grouped,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
