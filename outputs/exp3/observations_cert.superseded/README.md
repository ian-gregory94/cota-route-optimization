# Superseded — first 2B confirmation batch, 2026-08-31

Six certification receipts, all admissible individually, all refused for
comparison. Preserved for provenance.

Two reasons, both correct:

1. `code_version` was the repo HEAD. A commit touching only `scripts/` and
   `OPERATIONS.md` landed between the control cells and the treatment cells, so
   the arms carried different code identities for a change that could not have
   reached either of them. `code_version` is now a content digest of the
   evaluation path only.
2. `repair_occurred` / `INCUMBENT_REPAIRED` differed between arms and was not
   declared. It is now declared, per event type, with D30's measurement as its
   written justification.

The numbers themselves were not in doubt and agree with the re-run:

    <none>                  seed 20260825  2956120.58  unserved 9745.9
    <none>                  seed 20260826  2956120.58  unserved 9745.9
    <none>                  seed 20260827  2956008.53  unserved 9746.7
    splice-011-034-WESHIGW  seed 20260825  2957680.49  unserved 9755.0
    splice-011-034-WESHIGW  seed 20260826  2957680.49  unserved 9755.0
    splice-011-034-WESHIGW  seed 20260827  2957680.49  unserved 9755.0
