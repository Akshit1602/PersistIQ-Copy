# Changelog

## Unreleased

- Copilot now generates visualizations. Chart specs are renderer-neutral
  (`continum/AskData/chart_spec.py`), SQL results auto-chart when the rows are
  chartable, generic chart kinds (bar/line/pie/…) are available alongside the
  three named experiment charts, and every chart producer emits a `UIArtifact`
  so it reaches the SSE stream — previously charts existed only in subgraph
  state and never reached the UI.
- Chat renders backend artifact cards. `ArtifactCardRenderer` was defined but
  imported nowhere, so no backend card ever appeared; it now lives in
  `components/chat/ArtifactCard.tsx`, is mounted by `ChatStream`, and draws
  charts as inline SVG (`ArtifactChart.tsx`) in the app's own tokens.
- Reports tab updates after Copilot output. A chat turn that produced a chart or
  a computed stat card now files a report alongside module runs; reports render
  their charts inline. Reports previously came only from local module runs.
- Fixed the supervisor's clarification path parsing tool output as a Python
  literal, which made every parseable `missing_inputs` report as
  "(see tool output)" instead of naming the field.
- Auto-populate experiment inputs from the selected experiment's own data: new `/api/suggestions/inputs` endpoint profiles the warehouse (falling back to the bundled sample datasets) and a single frontend suggestion engine pre-fills the Analytics Lab forms, both hypothesis wizards, and the chat interview with provenance badges — replacing the hardcoded constants that were previously labelled "auto-detected".
