# Scientific workflow invariants from prior repairs

- FCHK Cartesian geometry is Bohr on input; convert to Å once at import. Preserve input
  coordinate units and compare an independent known value.
- RMSF must specify alignment and PBC handling. Kabsch alignment plus streaming Welford
  avoids treating rigid translation as fluctuation. PBC artifacts can survive alignment.
  NoJump requires a physically appropriate initial structure; do not call a raw-trajectory
  spike intrinsic molecular motion. The existing raw 71,554-atom/101-frame trajectory is
  expensive: use a small counterexample before repeating full analysis.
- RDF intramolecular exclusions and first-peak selection need explicit statistical
  definitions. A large global peak is not automatically the first shell.
- GROMACS generated PowerShell must propagate every engine exit code, preserve input box
  and dependencies, reject nonempty output directories and avoid default maxwarn.
  Generating scripts and mocked queue checks do not prove a real GPU simulation ran.
- LLM network work runs off the Qt main thread; document tools run on the main thread
  through CommandBus. Configuring an endpoint is not a successful live model request.
  Distinguish OpenAI-compatible function calling from a real MCP protocol server.
- Marking analysis entries Experimental is not implementing those algorithms. Preserve
  unresolved items in the issue matrix and report only checks actually run.
