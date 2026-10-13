"""Combination checks for the reviewed GW/BSE input subset.

Upstream: ctrl_io/quasiparticle_methods.rs, post_scf_analysis/mod.rs,
ri_gw/{mod,scgw}.rs and ri_bse/mod.rs at capabilities.UPSTREAM_COMMIT.
Types are checked by the shared capability catalog before this function.
No geometry recipe, result parsing or numerical-accuracy claims belong here.
"""

from __future__ import annotations

import math
from typing import Any


def quasiparticle_errors(ctrl: dict[str, Any], qp: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mode = qp.get("gw_or_bse")
    scheme = qp.get("gw_scheme")
    scgw = qp.get("scgw", "g0w0")
    unrestricted = ctrl.get("spin_polarization", False)
    if mode not in {"gw", "bse"}:
        errors.append("[quasiparticle_methods] requires explicit gw_or_bse=gw or bse")
    if scheme is None:
        errors.append("[quasiparticle_methods] requires an explicit gw_scheme; default is no gw")
    if ctrl.get("job_type") != "energy":
        errors.append("The reviewed GW/BSE input contract requires job_type=energy")
    if ctrl.get("eri_type", "ri-v") not in {"ri-v", "ri_v"}:
        errors.append("GW/BSE requires RI-V integrals (eri_type=ri-v or ri_v)")
    if ctrl.get("spin", 1) > 1 and not unrestricted:
        errors.append("ROHF GW/BSE is not covered; use a reviewed unrestricted reference")
    if qp.get("w_rs") and not qp.get("renormalized_singles"):
        errors.append("w_rs=true requires renormalized_singles=true")
    if scgw == "evgw" and "evgw_rounds" not in qp:
        errors.append("scgw=evgw requires explicit positive evgw_rounds")
    if "evgw_rounds" in qp and scgw != "evgw":
        errors.append("evgw_rounds requires scgw=evgw")
    if unrestricted:
        if scgw != "g0w0" or scheme != "extrapolated":
            errors.append("Unrestricted GW requires scgw=g0w0 and gw_scheme=extrapolated")
        if qp.get("renormalized_singles"):
            errors.append("Unrestricted renormalized_singles GW is not implemented upstream")
    if scheme == "parse from file":
        if mode != "bse" or not str(qp.get("parse_qp_path", "")).strip():
            errors.append("gw_scheme=parse from file requires BSE and explicit parse_qp_path")
        if scgw != "g0w0" or qp.get("renormalized_singles"):
            errors.append("parse from file skips GW; do not attach evGW or rsGW settings")
    elif "parse_qp_path" in qp:
        errors.append("parse_qp_path requires gw_scheme=parse from file")
    if qp.get("homo_lumo_gw_qp"):
        if mode != "gw" or unrestricted or scgw != "g0w0" or qp.get("renormalized_singles"):
            errors.append("homo_lumo_gw_qp is reviewed only for restricted GW-only G0W0")
    for key in ("bse_auxbas_path", "save_qp_path", "parse_qp_path"):
        if key in qp and not qp[key].strip():
            errors.append(f"{key} must name a nonempty path in the REST run environment")
    if mode == "gw":
        if any(key.startswith(("bse_", "davidson_")) for key in qp):
            errors.append("BSE / Davidson settings require gw_or_bse=bse")
        return errors
    if mode == "bse":
        channel = qp.get("bse_spin")
        allowed = {"singlet", "unrestricted"} if unrestricted else {"singlet", "triplet", "both"}
        if channel not in allowed:
            errors.append(
                "bse_spin must select a valid channel: restricted singlet/triplet/both; "
                "unrestricted reference has one coupled channel, not triplet/both"
            )
        if "bse_tda" not in qp:
            errors.append("BSE requires explicit bse_tda=true (TDA) or false (full BSE)")
        davidson_keys = {key for key in qp if key.startswith("davidson_")}
        if davidson_keys and not qp.get("bse_davidson_solver", False):
            errors.append("Davidson settings require bse_davidson_solver=true")
        if qp.get("bse_davidson_solver"):
            # Mirror the *parser's* effective defaults, not QuasiParticle::default().
            roots = qp.get("davidson_target_excitations", 6)
            maximum = qp.get("davidson_maximum_subspace_size", max(100, roots * 20))
            restart = qp.get("davidson_restart_dimensions", max(6, math.ceil(roots * 1.5)))
            if maximum <= roots:
                errors.append("davidson_maximum_subspace_size must exceed target excitations")
            if not roots <= restart < maximum:
                errors.append("davidson_restart_dimensions must cover roots and be below subspace")
    return errors
