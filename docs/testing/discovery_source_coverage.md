# Discovery Source Coverage Matrix

## Multi-Method Discovery Phase 2

| Requirement | Implementation | Test Coverage | Status |
| --- | --- | --- | --- |
| REQ-DISC-001 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Partial: model layer only |
| REQ-DISC-002 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Partial: model layer only |
| REQ-DISC-003 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Partial: hint model distinct from candidate records |
| REQ-DISC-005 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Partial: hint source fields defined |
| REQ-DISC-008 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Partial: source constant defined |
| REQ-DISC-009 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Covered |
| REQ-DISC-010 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Covered |
| REQ-DISC-011 | `src/galaxy/discovery_sources.py` | `tests/test_discovery_sources.py` | Covered |

## Remaining Coverage Gaps

- REQ-DISC-004 requires integration with MAST-backed candidate manifest generation.
- REQ-DISC-006 requires conversion from discovery hints into Galaxy project search inputs or suggestions.
- REQ-DISC-007 requires an adapter-level failure isolation test.
