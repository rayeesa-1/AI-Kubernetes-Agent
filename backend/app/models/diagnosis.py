from pydantic import BaseModel, ConfigDict, Field


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    root_cause: str = Field(min_length=1, max_length=2000)
    explanation: str = Field(min_length=1, max_length=4000)
    fix: str = Field(min_length=1, max_length=3000)
    kubectl_commands: list[str] = Field(max_length=6)
    prevention_recommendation: str = Field(min_length=1, max_length=2000)
    confidence: int = Field(ge=0, le=100)
    confidence_reasoning: str = Field(min_length=1, max_length=2000)
    evidence_references: list[str] = Field(max_length=12)
    missing_evidence: list[str] = Field(max_length=12)
