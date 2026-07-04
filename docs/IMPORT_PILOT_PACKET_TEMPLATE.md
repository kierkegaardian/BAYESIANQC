# Import Ingestion Pilot Packet Template

Use this packet for each sanitized production-like instrument file before any shared-lab pilot signoff.

## File Identity
- Instrument family:
- Instrument or middleware model:
- Source system:
- Sanitized source filename:
- Sanitized source SHA-256:
- Parser profile name and version:
- Archive root used:
- Import batch id:

## Expected Rows
- Total source rows:
- Expected ignored rows:
- Expected QC result rows:
- Expected rows requiring review:
- Expected ready-to-apply rows:
- Expected applied QC records:
- Expected quarantined rows:
- Expected artifact rows:
- Expected peak rows:

## Review Notes
- Known de-identification changes:
- Known unsupported rows or columns:
- Expected run/backlog association behavior:
- Parser profile assumptions:
- Deviations found:

## SME Signoff
- Reviewer name:
- Reviewer role:
- Review date:
- Decision: approve / reject / needs parser change
- Comments:

Production readiness remains blocked until at least two sanitized instrument families have completed this packet with approved expected-row signoff.
