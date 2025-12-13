from modules.schemas import TribunalVerdictItem, TribunalSeverity, TribunalVerdictType


def test_verdict_item_schema_roundtrip():
    item = TribunalVerdictItem(
        id="123e4567-e89b-12d3-a456-426614174000",
        type=TribunalVerdictType.CONSTITUTION,
        rule_id="R1",
        severity=TribunalSeverity.HIGH,
        file="a.py",
        line_start=1,
        line_end=1,
        message="No eval",
        suggested_fix="Use ast.literal_eval",
        auto_fixable=False,
        confidence=0.9,
    )

    dumped = item.model_dump()
    assert dumped["type"] == "constitution"
    assert dumped["severity"] == "high"
