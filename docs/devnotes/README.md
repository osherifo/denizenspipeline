# Dev Notes

Design decisions, known issues, and workarounds encountered during development.

- [batch-convert.md](batch-convert.md) — Batch DICOM-to-BIDS with parallel execution, WebSocket progress, CLI
- [saved-convert-configs.md](saved-convert-configs.md) — Persistent conversion config storage (YAML, ConfigStore pattern)
- [convert-module.md](convert-module.md) — DICOM-to-BIDS conversion module (heudiconv wrapper + heuristic registry)
- [convert-frontend.md](convert-frontend.md) — DICOM-to-BIDS web UI (full-stack: backend API + React frontend)
- [composer-features-ux-redesign.md](composer-features-ux-redesign.md) — Redesign of features UX in the pipeline composer
- [composer-autocomplete-from-configs.md](composer-autocomplete-from-configs.md) — Autocomplete fields from saved experiment configs
- [composer-response-params-gap.md](composer-response-params-gap.md) — Gap between response loader params and composer UI
- [run-name-mismatch.md](run-name-mismatch.md) — When response and stimulus data use different naming conventions
- [textgrid-parsing.md](textgrid-parsing.md) — Short-format TextGrid files that existing parsers can't handle
- [skip-stimulus-stage.md](skip-stimulus-stage.md) — Design for skipping stimuli when features are precomputed
