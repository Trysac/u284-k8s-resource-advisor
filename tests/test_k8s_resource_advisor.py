"""Tests for k8s_resource_advisor."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from k8s_resource_advisor import (
    AdvisorError,
    Policy,
    Recommendation,
    Resources,
    Sample,
    assess,
    main,
    parse_quantity,
    read_samples_csv,
    recommend,
    render_patch,
)

# ---------------------------------------------------------------------------
# parse_quantity tests
# ---------------------------------------------------------------------------


def test_parse_quantity_cpu_no_suffix() -> None:
    assert parse_quantity("0.1", "cpu") == 100
    assert parse_quantity("1", "cpu") == 1000
    assert parse_quantity("0.0005", "cpu") == 1  # rounded up


def test_parse_quantity_cpu_millicores() -> None:
    assert parse_quantity("250m", "cpu") == 250
    assert parse_quantity("1m", "cpu") == 1


def test_parse_quantity_memory_no_suffix() -> None:
    assert parse_quantity("123456", "memory") == 123456


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("1k", 1_000),
        ("1M", 1_000_000),
        ("500M", 500_000_000),
        ("1G", 1_000_000_000),
        ("1T", 1_000_000_000_000),
        ("1Ki", 1024),
        ("1Mi", 1024**2),
        ("1Gi", 1024**3),
        ("1Ti", 1024**4),
    ],
)
def test_parse_quantity_memory_suffixes(q: str, expected: int) -> None:
    assert parse_quantity(q, "memory") == expected


def test_parse_quantity_acceptance_specific() -> None:
    assert parse_quantity("1Gi", "memory") == 1073741824
    assert parse_quantity("500M", "memory") == 500000000


def test_parse_quantity_invalid_cpu_suffix() -> None:
    with pytest.raises(AdvisorError) as excinfo:
        parse_quantity("100M", "cpu")
    assert excinfo.value.code == "invalid_quantity"


def test_parse_quantity_invalid_memory_suffix() -> None:
    with pytest.raises(AdvisorError) as excinfo:
        parse_quantity("100m", "memory")
    assert excinfo.value.code == "invalid_quantity"


def test_parse_quantity_exponent_invalid() -> None:
    for q in ["1e3", "1E3", "1e+3"]:
        with pytest.raises(AdvisorError) as excinfo:
            parse_quantity(q, "cpu")
        assert excinfo.value.code == "invalid_quantity"


def test_parse_quantity_negative_invalid() -> None:
    with pytest.raises(AdvisorError) as excinfo:
        parse_quantity("-1", "cpu")
    assert excinfo.value.code == "invalid_quantity"


def test_parse_quantity_length_limit() -> None:
    long_q = "1" * 40
    with pytest.raises(AdvisorError) as excinfo:
        parse_quantity(long_q, "cpu")
    assert excinfo.value.code == "invalid_quantity"


def test_parse_quantity_non_string_invalid() -> None:
    with pytest.raises(AdvisorError) as excinfo:
        parse_quantity(100, "cpu")  # type: ignore[arg-type]
    assert excinfo.value.code == "invalid_quantity"


def test_parse_quantity_rounding_up_memory() -> None:
    # 0.1Mi = 104857.6 -> ceil 104858
    assert parse_quantity("0.1Mi", "memory") == 104858


# ---------------------------------------------------------------------------
# read_samples_csv tests
# ---------------------------------------------------------------------------

SAMPLE_CSV = """timestamp,namespace,workload,container,cpu_m,memory_bytes
2023-01-01T00:00:00Z,default,web,app,100,251658240
2023-01-01T00:01:00Z,default,web,app,120,251658240
"""


def test_read_samples_csv_valid() -> None:
    stream = io.StringIO(SAMPLE_CSV)
    samples = read_samples_csv(stream)
    assert len(samples) == 2
    assert samples[0].cpu_m == 100
    assert samples[0].memory_bytes == 251658240
    assert samples[1].namespace == "default"


def test_read_samples_csv_missing_column() -> None:
    csv_no_mem = """timestamp,namespace,workload,container,cpu_m
2023-01-01T00:00:00Z,default,web,app,100
"""
    with pytest.raises(AdvisorError) as excinfo:
        read_samples_csv(io.StringIO(csv_no_mem))
    assert excinfo.value.code == "missing_column"


def test_read_samples_csv_invalid_sample_row_number() -> None:
    csv_invalid = """timestamp,namespace,workload,container,cpu_m,memory_bytes
2023-01-01T00:00:00Z,default,web,app,100,1000
2023-01-01T00:01:00Z,default,web,app,100,1000
2023-01-01T00:02:00Z,default,web,app,100,1000
2023-01-01T00:03:00Z,default,web,app,-5,1000
"""
    with pytest.raises(AdvisorError) as excinfo:
        read_samples_csv(io.StringIO(csv_invalid))
    assert excinfo.value.code == "invalid_sample"
    assert "row 4" in str(excinfo.value)


def test_read_samples_csv_too_many_rows() -> None:
    max_rows = 5
    lines = ["timestamp,namespace,workload,container,cpu_m,memory_bytes"]
    for i in range(max_rows + 1):
        lines.append(f"2023-01-01T00:{i:02d}:00Z,default,web,app,100,1000")
    csv_data = "\n".join(lines) + "\n"
    with pytest.raises(AdvisorError) as excinfo:
        read_samples_csv(io.StringIO(csv_data), max_rows=max_rows)
    assert excinfo.value.code == "too_many_rows"


# ---------------------------------------------------------------------------
# recommend tests
# ---------------------------------------------------------------------------


def make_samples(cpu_values: list[int], mem_values: list[int] | None = None):
    if mem_values is None:
        mem_values = [100_000_000] * len(cpu_values)
    samples = []
    for i, cpu in enumerate(cpu_values):
        samples.append(
            Sample(
                timestamp=f"t{i}",
                namespace="default",
                workload="web",
                container="app",
                cpu_m=cpu,
                memory_bytes=mem_values[i],
            )
        )
    return samples


def test_recommend_acceptance() -> None:
    samples = make_samples(
        [100, 120, 90, 300, 110, 105, 95, 130, 115, 125],
        [240 * 1024**2] * 10,
    )
    recs = recommend(samples)
    assert len(recs) == 1
    rec = recs[0]
    assert rec.status == "ok"
    assert rec.cpu_request_m == 150
    # margin 15%: 251658240 * 1.15 = 289406976 exactly, already multiple of 1MiB
    assert rec.memory_request_b == 289406976
    assert rec.cpu_limit_m == 0
    assert rec.memory_limit_b == rec.memory_request_b


def test_recommend_insufficient_data() -> None:
    samples = make_samples([100] * 9, [1_000_000] * 9)
    recs = recommend(samples, policy=Policy(min_samples=10))
    assert len(recs) == 1
    rec = recs[0]
    assert rec.status == "insufficient_data"
    assert rec.cpu_request_m == 0
    assert rec.memory_request_b == 0


def test_recommend_floor() -> None:
    samples = make_samples([1] * 10, [1] * 10)
    recs = recommend(samples)
    rec = recs[0]
    assert rec.cpu_request_m == Policy().min_cpu_m  # 10
    assert rec.memory_request_b == Policy().min_memory_b  # 16Mi


def test_recommend_step_rounding_boundary() -> None:
    policy = Policy(margin_pct=0, memory_step_b=100, min_memory_b=0, min_samples=5)
    # value 150 -> round up to 200
    samples = make_samples([10] * 5, [150] * 5)
    recs = recommend(samples, policy=policy)
    assert recs[0].memory_request_b == 200
    # value 200 -> stays 200
    samples = make_samples([10] * 5, [200] * 5)
    recs = recommend(samples, policy=policy)
    assert recs[0].memory_request_b == 200


def test_recommend_all_zero_cpu_floor() -> None:
    samples = make_samples([0] * 10, [1000] * 10)
    recs = recommend(samples)
    rec = recs[0]
    assert rec.cpu_request_m == Policy().min_cpu_m  # 10


def test_recommend_cpu_limit_factor() -> None:
    samples = make_samples([100] * 10, [1000] * 10)
    policy = Policy(cpu_limit_factor=2.0)
    recs = recommend(samples, policy=policy)
    rec = recs[0]
    assert rec.cpu_request_m == 120  # 100*1.15=115 -> ceil to 120
    assert rec.cpu_limit_m == 240  # 120*2=240 -> already multiple of 10


# ---------------------------------------------------------------------------
# assess tests
# ---------------------------------------------------------------------------


def make_recommendation(cpu=150, mem=289406976) -> Recommendation:
    return Recommendation(
        namespace="default",
        workload="web",
        container="app",
        samples=10,
        cpu_request_m=cpu,
        memory_request_b=mem,
        cpu_limit_m=0,
        memory_limit_b=mem,
        status="ok",
    )


def test_assess_ok() -> None:
    rec = make_recommendation()
    current = Resources(cpu_request="150m", memory_request="276Mi")
    result = assess(rec, current)
    assert result == {"cpu": "ok", "memory": "ok"}


def test_assess_over_provisioned() -> None:
    rec = make_recommendation()
    current = Resources(cpu_request="500m", memory_request="128Mi")
    result = assess(rec, current)
    assert result["cpu"] == "over_provisioned"
    assert result["memory"] == "under_provisioned"


def test_assess_under_provisioned() -> None:
    rec = make_recommendation()
    current = Resources(cpu_request="100m", memory_request="100Mi")
    result = assess(rec, current)
    assert result["cpu"] == "under_provisioned"
    assert result["memory"] == "under_provisioned"


def test_assess_unset() -> None:
    rec = make_recommendation()
    current = Resources()
    result = assess(rec, current)
    assert result == {"cpu": "unset", "memory": "unset"}
    current = Resources(cpu_request="100m")
    result = assess(rec, current)
    assert result["cpu"] == "under_provisioned"  # 100m < 150m recommendation
    assert result["memory"] == "unset"


# ---------------------------------------------------------------------------
# render_patch tests
# ---------------------------------------------------------------------------


def test_render_patch_no_cpu_limit() -> None:
    rec = make_recommendation()
    patch = render_patch(rec)
    expected = (
        "resources:\n  requests:\n    cpu: 150m\n    memory: 276Mi\n  limits:\n    memory: 276Mi\n"
    )
    assert patch == expected


def test_render_patch_with_cpu_limit() -> None:
    rec = Recommendation(
        namespace="default",
        workload="web",
        container="app",
        samples=10,
        cpu_request_m=150,
        memory_request_b=289406976,
        cpu_limit_m=300,
        memory_limit_b=289406976,
        status="ok",
    )
    patch = render_patch(rec)
    expected = (
        "resources:\n"
        "  requests:\n"
        "    cpu: 150m\n"
        "    memory: 276Mi\n"
        "  limits:\n"
        "    cpu: 300m\n"
        "    memory: 276Mi\n"
    )
    assert patch == expected


def test_render_patch_omits_memory_limit_when_disabled() -> None:
    rec = Recommendation(
        namespace="default",
        workload="web",
        container="app",
        samples=10,
        cpu_request_m=150,
        memory_request_b=289406976,
        cpu_limit_m=0,
        memory_limit_b=0,
        status="ok",
    )
    patch = render_patch(rec)
    assert "memory: 276Mi" in patch
    limits_block = patch.split("  limits:\n", 1)[1]
    assert "memory:" not in limits_block


# ---------------------------------------------------------------------------
# main tests
# ---------------------------------------------------------------------------


def test_main_success(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    csv_content = SAMPLE_CSV
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text(csv_content)
    exit_code = main([str(csv_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "# default/web/app insufficient_data" in captured.out
    assert "    cpu: 0m" not in captured.out
    assert "    memory: 0Mi" not in captured.out
    assert "resources:" not in captured.out


def test_main_under_provisioned(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rows = "\n".join(f"2023-01-01T00:{i:02d}:00Z,default,web,app,100,251658240" for i in range(10))
    csv_content = "timestamp,namespace,workload,container,cpu_m,memory_bytes\n" + rows + "\n"
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text(csv_content)
    current_data = {"default/web/app": {"cpu_request": "50m", "memory_request": "100Mi"}}
    current_path = tmp_path / "current.json"
    current_path.write_text(json.dumps(current_data))
    exit_code = main([str(csv_path), "--current", str(current_path)])
    capsys.readouterr()
    assert exit_code == 1


def test_main_usage_csv_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    rows = "\n".join(f"2023-01-01T00:{i:02d}:00Z,default,web,app,100,251658240" for i in range(10))
    Path("usage.csv").write_text(
        "timestamp,namespace,workload,container,cpu_m,memory_bytes\n" + rows + "\n"
    )
    assert main(["usage.csv"]) == 0
    out = capsys.readouterr().out
    assert "# default/web/app" in out
    assert "    cpu: 120m\n" in out
    assert "    memory: 276Mi\n" in out

    current_data = {"default/web/app": {"cpu_request": "50m", "memory_request": "100Mi"}}
    Path("current.json").write_text(json.dumps(current_data))
    assert main(["usage.csv", "--current", "current.json"]) == 1
    capsys.readouterr()


def test_main_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    exit_code = main(["nonexistent.csv"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error" in captured.err


def test_main_invalid_csv(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("no,columns\n1,2\n")
    exit_code = main([str(csv_path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error" in captured.err


def test_main_numeric_current_value(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rows = "\n".join(f"2023-01-01T00:{i:02d}:00Z,default,web,app,100,251658240" for i in range(10))
    csv_content = "timestamp,namespace,workload,container,cpu_m,memory_bytes\n" + rows + "\n"
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text(csv_content)
    current_path = tmp_path / "current.json"
    current_path.write_text(json.dumps({"default/web/app": {"cpu_request": 100}}))
    exit_code = main([str(csv_path), "--current", str(current_path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error" in captured.err


def test_main_non_object_current_json(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rows = "\n".join(f"2023-01-01T00:{i:02d}:00Z,default,web,app,100,251658240" for i in range(10))
    csv_content = "timestamp,namespace,workload,container,cpu_m,memory_bytes\n" + rows + "\n"
    csv_path = tmp_path / "samples.csv"
    csv_path.write_text(csv_content)
    current_path = tmp_path / "current.json"
    current_path.write_text(json.dumps([{"cpu_request": "100m"}]))
    exit_code = main([str(csv_path), "--current", str(current_path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Error" in captured.err
