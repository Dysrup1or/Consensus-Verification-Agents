from modules.schemas import RunTelemetry


def test_run_telemetry_schema_required_keys():
    t = RunTelemetry(
        run_id="00000000-0000-0000-0000-000000000000",
        project_id="p1",
        mode="diff",
        coverage={
            "included_files_count": 0,
            "header_covered_count": 0,
            "full_text_covered_count": 0,
            "slice_covered_count": 0,
            "truncated_files": [],
            "unknown_files": [],
            "changed_files_total": 0,
            "changed_files_fully_covered_count": 0,
            "changed_files_header_covered_count": 0,
            "changed_files_unknown_count": 0,
            "fully_covered_percent_of_changed": 100.0,
            "forced_files_count": 0,
            "skip_reasons": {},
        },
        cost={
            "lane1_deterministic_tokens": 0,
            "lane2_llm_input_tokens_est": 0,
            "lane2_llm_stable_prefix_tokens_est": 0,
            "lane2_llm_variable_suffix_tokens_est": 0,
        },
        cache={
            "cached_vs_uncached": "unknown",
            "reason": "provider_cache_not_enabled",
        },
        latency={
            "run_started_at": "2025-01-01T00:00:00",
            "run_final_at": "2025-01-01T00:00:01",
            "ttff_ms": 0,
            "time_to_final_ms": 1000,
        },
        skipped={
            "skipped_imports": [],
        },
    )

    dumped = t.model_dump()
    for key in ["coverage", "cost", "cache", "latency", "skipped"]:
        assert key in dumped
