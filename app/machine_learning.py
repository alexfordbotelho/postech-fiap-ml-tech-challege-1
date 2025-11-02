from pydantic import BaseModel, Field, RootModel
from typing import List, Literal, Dict, Union
import numpy as np

class FeatureInfo(BaseModel):
    name: str
    original_name: str
    dtype: Literal["float"]
    min: float
    max: float
    mean: float
    std: float

class IrisFeatures(BaseModel):
    sepal_length: float = Field(..., description="cm")
    sepal_width:  float = Field(..., description="cm")
    petal_length: float = Field(..., description="cm")
    petal_width:  float = Field(..., description="cm")

# Aceita 1 ou N registros no POST
class IrisFeaturesList(RootModel[List[IrisFeatures]]):
    root: List[IrisFeatures]

class PredictionItem(BaseModel):
    index: int
    predicted_class: int
    predicted_label: str
    probabilities: Dict[str, float]  # label -> prob (softmax)

class PredictionResponse(BaseModel):
    model_name: str
    model_version: str
    results: List[PredictionItem]

class TrainingRow(BaseModel):
    sepal_length: float
    sepal_width:  float
    petal_length: float
    petal_width:  float
    target: int | None = None
    target_label: str | None = None

# ====== Helpers ======
def softmax_logits_proba(proba_row: np.ndarray, target_names: List[str]) -> Dict[str, float]:
    # proba_row já vem normalizado do scikit-learn, só rotulamos:
    return {target_names[i]: float(proba_row[i]) for i in range(len(target_names))}