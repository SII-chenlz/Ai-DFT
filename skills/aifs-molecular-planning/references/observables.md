# Plan from the requested observable


Start from **what the user wants to obtain or compare**, for any molecular system. Do not require a novice to name ZPE, a functional, a charge/spin state or a task sequence in the opening question. Infer plausible interpretations from the physical process and experimental context, explain them briefly, and ask only for information that changes the plan. Record the observable, comparison convention, physical states and unresolved assumptions in task `purpose`/`notes` and plan `assumptions`. Neither “compare with experiment” alone nor a system name fixes the workflow or method.

| Requested quantity | Required planning |
| --- | --- |
| Electronic energy or an explicitly electronic reaction/binding/detachment difference | Consistent final electronic energies; no automatic ZPE/thermal tasks; label the result electronic only |
| Experimental vibrational 0–0 ADE/adiabatic electron affinity, adiabatic ionization threshold, or a 0 K dissociation/reaction quantity including nuclear zero-point motion | Optimized states plus frequency/ZPE sources for every participating molecular species; combine electronic energies and the stoichiometric ZPE difference |
| Vertical detachment/ionization electronic energy gap | Both electronic states at the specified initial-state geometry; do not automatically add equilibrium-geometry ZPE differences |
| Finite-temperature enthalpy, free energy or equilibrium constant | Appropriate frequencies and thermal/entropy treatment, with temperature, pressure/standard state and relevant low-frequency/conformer assumptions; ZPE alone is insufficient |
| A photoelectron band envelope or a full absorption/XPS spectrum | Identify the spectroscopy and transitions first; arrange the appropriate excited-state/vibrational/intensity/broadening treatment or pending external steps; electronic energy differences alone are not a spectrum |

If the experimental observable is unclear, use a concise DSH question panel when available, with plain explanations such as threshold, band position or full spectrum. Do not ask the user to decide whether a physically required correction exists. Do not ask again when the scope is already clear. Preserve explicit electronic-only scope; do not promise a 0–0 comparison for an uncorrected energy. If a correction is required, **save its calculation/source and analysis tasks**, not just a reminder after delivering cards.

These dependent calculations and energy combinations use the saved-workflow path automatically. Create a concise complete graph once, then patch changed inputs; do not make the user request database persistence or repeatedly serialize the entire plan. Deliver the ready files now and explain the results needed for later steps. This applies to any system, not just a cluster example.

For a zero-point-corrected energy difference, use the process stoichiometry:

`delta_E_0 = sum(products: coefficient * (E_electronic + ZPE)) - sum(reactants: coefficient * (E_electronic + ZPE))`

The ZPE correction can have either sign. Atomic species and a free electron have no molecular vibrational ZPE; record that physical zero instead of inventing an atomic frequency job. Include every required molecular state/fragment with its own identity and dependencies; do not always add exactly two frequency tasks.

For **molecular electron detachment** specifically, the reusable pattern is:

`ADE_0 = E(neutral, neutral geometry) - E(anion, anion geometry) + ZPE(neutral) - ZPE(anion)`

`ADE_electronic = E(neutral, neutral geometry) - E(anion, anion geometry)`

`VDE_electronic = E(neutral, anion geometry) - E(anion, anion geometry)`

For two molecular species this adds an anion frequency task depending on its optimization and a neutral frequency task depending on its own optimization. The corrected ADE analysis directly depends on both final-energy tasks and both ZPE sources, with the explicit formula in `analysis_formula`; an optional separate analysis reports `ADE_electronic`. VDE analysis depends on the two energies at the anion geometry. These roles apply across systems: choose actual task IDs, electron states, methods and bases from the problem, retaining original stable IDs when revising a saved plan. Do not copy a test cluster's charge, multiplicity, geometry, functional or basis.

Frequency cards use `job_type=energy` with the supported Hessian section/driver, not an invented `job_type=frequency`. For each missing optimized geometry, use `position_source=prior_result` and the corresponding `position_from_task`/`depends_on`; keep coordinates/unit null until its real result arrives. Choose a consistent frequency method/basis/scaling protocol for the participating species, normally the confirmed geometry protocol when its Hessian is supported. Frequency and final-energy decisions are independent. Query derivative coverage for each actual electronic state: open-shell needs the reviewed unrestricted analdrv route rather than the closed-shell native Hessian; post-SCF and unverified VV10 Hessians remain blocked. If a frequency protocol is unsuitable, propose a separately confirmed supported protocol or an external frequency source; never silently replace the method or assume a high-level energy method has an available Hessian.

For a supported full-molecule frequency protocol, request the thermo ZPE report; `thermo.sclzpe=1.0` explicitly records unscaled harmonic ZPE when no justified scaling factor is chosen. For the analdrv route use `ctrl.analdrv_tasks=["hessian"]` and omit `atm_list` to cover all atoms. Native and analdrv routes still obey their respective contracts. Record any justified scaling factor, changed frequency method and approximation. The thermo section's default finite-temperature outputs do not change a requested 0 K observable. Combine the separately reported ZPE correction with the chosen final electronic energies, not frequency-method `E+ZPE` totals or Gibbs/enthalpy corrections.

After external calculations, request all required energies/ZPE **with their units, species/state, method and frequency/minimum check**. Exclude translation/rotation from harmonic ZPE. For an equilibrium structure, significant imaginary vibrational modes mean the minimum is not established; do not take absolute frequencies or discard problematic modes to manufacture a valid comparison. Transition-state frequency interpretation is a separate saddle-point workflow. Convert units explicitly with a recorded source before combination. Do not invent frequencies or ZPE from prepared cards. Save unresolved result requirements in the analysis task's notes and describe it as awaiting results even though the backend labels it `analysis_only`.

AIFS currently saves tasks/formulas and prepares input cards; it does not run frequencies, parse results or evaluate free-text formulas. A detailed vibronic VDE/spectral comparison needs its own stated experimental convention and vibrational/Franck–Condon treatment; do not apply the equilibrium ADE correction to ordinary VDE automatically.

The fixed-geometry VDE is not universally the maximum of a measured photoelectron band. The 0–0 ADE is the vibrational-ground-state threshold, not automatically the first visible onset: Franck–Condon intensities, hot bands, unresolved transitions and the experimental assignment matter. Describe the comparison conditionally; do not save a blanket peak/onset equality in task notes. See [a primary study demonstrating a band maximum different from VDE](https://iopenshell.usc.edu/pubs/abstracts/134/).

Definition references for molecular ADE: [neutral-minus-anion ZPE correction to the 0–0 transition](https://pubs.rsc.org/en/content/articlehtml/2020/cp/d0cp05204c) and [electronic differences at each optimized geometry with ZPE corrections](https://pmc.ncbi.nlm.nih.gov/articles/PMC9862062/). These define observables, not functional recommendations for a particular system.
