# Built-in heuristics

This directory is intentionally empty in the public package.
Users put their own heudiconv heuristics under
`$FMRIFLOW_HOME/addons/heuristics/`.

A heuristic dropped here would be selectable by every fmriflow
install; that's a strong claim that no concrete heuristic
currently meets. When we have one that's truly generic (e.g.
"single-task single-session BIDS layout from a Siemens product
sequence"), it lands here.
