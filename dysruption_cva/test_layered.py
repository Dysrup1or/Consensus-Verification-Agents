"""Quick test for the layered verification system."""
import asyncio
from modules.monitoring.layered_verification import LayeredVerificationDaemon


async def test():
    print("=" * 60)
    print("LAYERED VERIFICATION TEST")
    print("=" * 60)
    
    d = LayeredVerificationDaemon(".", poll_interval_seconds=1)
    
    print("\nRunning single verification cycle...")
    result = await d.run_cycle()
    
    print(f"\nResults:")
    print(f"  Git changes detected: {result.git_diff.has_changes}")
    print(f"  Changed files: {len(result.git_diff.changed_files)}")
    if result.git_diff.changed_files:
        for f in result.git_diff.changed_files[:5]:
            print(f"    - {f}")
        if len(result.git_diff.changed_files) > 5:
            print(f"    ... and {len(result.git_diff.changed_files) - 5} more")
    
    if result.quick_scan:
        print(f"  Quick scan violations: {len(result.quick_scan.violations)}")
        print(f"  Total score: {result.quick_scan.total_score}")
        print(f"  Scan time: {result.quick_scan.scan_time_ms}ms")
        
        if result.quick_scan.violations:
            print("\n  Violations found:")
            for v in result.quick_scan.violations[:5]:
                print(f"    [{v.severity.upper()}] {v.rule_id}: {v.message}")
                print(f"           in {v.file}:{v.line_start}")
    
    if result.escalation:
        print(f"\n  Escalation decision: {'YES' if result.escalation.should_escalate else 'NO'}")
        print(f"  Reason: {result.escalation.reason}")
    
    print(f"\n  Total cycle time: {result.total_time_ms}ms")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test())
