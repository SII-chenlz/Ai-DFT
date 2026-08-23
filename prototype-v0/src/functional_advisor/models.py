"""Pydantic models shared across the advisor."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DftCode = Literal["vasp", "qe"]


class UserRequirement(BaseModel):
    """Normalized user requirement extracted from free text."""

    model_config = ConfigDict(extra="forbid")

    system_description: str = Field(
        ..., description="Materials system or chemistry problem, e.g. TiO2 slab + water molecule."
    )
    elements: list[str] = Field(
        default_factory=list, description="Chemical elements present in the system."
    )
    task: str = Field(
        default="geometry optimization and single-point energy",
        description="DFT task, e.g. geometry optimization, band structure, adsorption energy, NEB.",
    )
    code: DftCode = Field(default="vasp", description="Target DFT code.")
    spin_polarized: bool = Field(default=False, description="Whether magnetism matters.")
    charged: bool = Field(default=False, description="Whether the system is charged.")
    charge: int = Field(default=0, description="Net charge of the cell/molecule.")
    extra_constraints: list[str] = Field(
        default_factory=list, description="Constraints, e.g. fix bottom layers, SOC."
    )
    precision: str = Field(default="normal", description="normal | high | quick")


class FunctionalRecommendation(BaseModel):
    """LLM/rule recommendation for exchange-correlation and related settings."""

    model_config = ConfigDict(extra="forbid")

    functional: str = Field(..., description="Recommended exchange-correlation functional.")
    dispersion: str = Field(
        default="", description="Dispersion correction, e.g. D3(BJ), D4, vdW-DF2."
    )
    hubbard_u: dict[str, float] = Field(
        default_factory=dict, description="Hubbard U per element or orbital, if applicable."
    )
    recommended_for: list[str] = Field(default_factory=list)
    rationale: str = Field(..., description="Short scientific rationale.")
    caveats: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Code-agnostic numerical settings."
    )


class DftJobSpec(BaseModel):
    """Concrete job specification rendered into input cards."""

    model_config = ConfigDict(extra="forbid")

    code: DftCode = "vasp"
    system_name: str = "system"
    task: str = "geometry optimization and single-point energy"
    functional: str = "PBE"
    dispersion: str = ""
    hubbard_u: dict[str, float] = Field(default_factory=dict)
    spin_polarized: bool = False
    charged: bool = False
    charge: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)
    structure_file: str | None = None
    notes: list[str] = Field(default_factory=list)
