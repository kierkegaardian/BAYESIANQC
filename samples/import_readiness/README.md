# Import Readiness Synthetic Fixtures

These files are synthetic test fixtures for BAYESIANQC import-readiness checks.
They are not vendor exports and do not contain production or patient data.

Source patterns used to shape the fixtures:
- Thermo Chromeleon can export reports for injections, sequences, or multiple sequences using report templates and selected channels.
- Benchling connector docs describe OpenLab/Chromeleon outputs becoming CSV files where rows represent injections, peaks, or chromatogram points.
- ASTM D86 automated distillation workflows report temperature as a function of percent recovered, often as a table or graph.
- Shimadzu LabSolutions report configuration includes summary tables, chromatograms, calibration curves, audit-trail logs, and peak integration/quantitation result information.
