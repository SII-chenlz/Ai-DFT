# Advanced REST input contracts


Use `get_rest_capabilities` once for the current coverage; query `section` for only the needed keyword schema. This is local and does not consume a literature-search round. Do not search packaged source code for schemas. REST operations are activated by sections as well as `job_type`:

| User's task | Saved task settings | Required checks |
| --- | --- | --- |
| Harmonic frequencies | `job_type=energy`, `rest_options.hessian={frequencies:true}` | Confirm geometry and method; the current native Hessian contract is closed shell |
| Open-shell/RSH/mGGA frequencies | `job_type=energy`, `rest_options.ctrl={analdrv_tasks:["hessian"]}`, optional `rest_options.analdrv` | Explicitly choose the newer analdrv path; no ROHF, post-SCF Hessian or unverified VV10 derivatives; do not replace the method |
| Thermal corrections/free energy | Hessian plus `rest_options.thermo` | Temperature K, pressure atm, appropriate optimized geometry; finite/positive values and RRHO limitations |
| Electric multipoles | `job_type=energy`, `rest_options.ctrl={analdrv_tasks:["multipole"]}`, `rest_options.analdrv` | Orders 1–4; origin in Bohr regardless of geometry unit; post-SCF is limited to reviewed restricted PT2 methods without frozen core |
| TDDFT excitation energies | `job_type=energy`, `rest_options.tddft` | Restricted triplet/both needs AO mode; unrestricted reference must omit `tddft_spin` |
| Frequency-domain polarizability/response | `job_type=energy`, `rest_options.tddft={response_tddft:true,external_field_freq:0.1}` for a confirmed 0.1 Hartree frequency | Restricted reference; damping in Hartree and response grid in Bohr; this run skips excitation eigenvalues |
| FEAST excitation solver | `job_type=energy`, `rest_options.tddft={tddft_feast_solver:true}` plus confirmed range/solver settings | Restricted MO mode, ordered Hartree interval; not unrestricted/AO |
| PySOC transition export | `job_type=energy`, `rest_options.tddft={pysoc:true,tddft_spin:"both",tddft_mode:"ao"}` | Restricted reference; prepares an export, not a completed SOC spectrum |
| Excited-state force | `job_type=force`, `rest_options.tddft={tddft_grad_state:1}` for confirmed first excited state | Restricted single channel, reviewed HF/LDA/GGA/ordinary hybrid, root within nroots; eigenvalue run required; no RSH/mGGA, response, FEAST, combined-spin gradient or excited-state optimization |
| One-/two-dimensional RRS-PBC | `job_type=energy`, `rest_options.geom` with `rrs_pbc=true`, `pbc_dim`, `unit_cell_index`, `rrs_pbc_vec`, `max_step`, `k_points` | Closed shell; zero-based core-cell indices, vector unit follows geometry; finite-cluster post-SCF reconstruction, not periodic SCF; 3D sampling pending |
| Transition-state optimization | `job_type=opt`, `rest_options.geometric_pyo3={transition:true,hessian:"first"}` | Appropriate initial geometry; later confirm the saddle by frequency/IRC, never claim a TS from card generation |
| IRC | `job_type=opt`, geometric section `irc=true`, `irc_direction` | Requires a suitable transition-state geometry; preserve result dependencies |
| Frozen atoms | Five-column geometry `Element fix x y z` | `0` fixed / `1` movable; geometric-pyo3 and tric/dlc/hdlc coordinates |
| VV10 method optimization | Reviewed parse_xc method plus `rest_options.ctrl={numerical_force:true}` | Slower numerical derivative; no added D3/D4, no claim of verified analytic VV10 derivatives |

Put extra tables in `PlanTask.rest_options`, keyed by exact section name, for example `{"hessian":{"frequencies":true},"thermo":{"temperature":298.15,"pressure":1.0}}`. The backend preserves them in plan revisions and card provenance. It rejects unknown keys and attempts to override the core method, coordinates, charge or multiplicity. A section's presence can trigger an operation even if empty; avoid inserting empty sections by habit. `convergence_*` is the actual geometric convergence keyword prefix read by the pinned source; do not copy README's obsolete `converge_*` spelling.

`[analdrv]` alone only configures the driver: use the **array** `ctrl.analdrv_tasks=["hessian"]` or `["multipole"]` to request a property. Native and analdrv Hessians are alternative routes. Thermochemistry with analdrv requires all atoms; a partial atom Hessian is not a full molecular free-energy calculation. Split stability, frequency-domain response, FEAST and excited-state gradient requests into suitable separate tasks. Do not attach the gradient to a FEAST/response-only run that lacks the required eigenvectors. Query the latest section schema and honor blockers for each combination.

Optimization-result dependencies still apply to later frequency, thermochemistry, or excited-state tasks. Keep coordinates/unit unknown until the genuine result arrives; neither an input file nor an energy-only result proves a successful optimization. Native thermo pressure is **atm**, geometric `thermo=[T,P]` pressure is **bar**. Do not silently convert user quantities without recording the conversion and its source.

GW/BSE, MD/AIMD/QM-MM/pure-MM, 3D RRS-PBC sampling, multipole density export and advanced excited-state optimization/gradient combinations remain integration gaps. Use the capability tool's latest pending list rather than generalizing a gap to an entire method family. Explain pending scientific steps and preserve requirements; do not generate a replacement card for the requested unintegrated operation. A requested theoretical spectrum needs the appropriate excited-state/transition-intensity analysis and broadening; ground-state total energies alone are not a simulated XPS/absorption spectrum.

