"""Các kiểu dữ liệu dùng chung. Giá được lưu theo triệu đồng."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    id: str
    brand: str
    model: str
    name: str
    segment: str
    new_price: float

    @property
    def model_key(self) -> tuple[str, str]:
        return self.brand, self.model

    @property
    def title(self) -> str:
        return f"{self.brand} {self.model} {self.name}"


@dataclass(frozen=True)
class Vehicle:
    frame_id: str
    year: int
    mileage: int
    region: str
    condition: str
    dealer_service: bool
    commercial: bool
    flood: bool
    major_accident: bool

    @property
    def severe(self) -> bool:
        return self.flood or self.major_accident


FLAGS = ("dealer_service", "commercial", "flood", "major_accident")


@dataclass(frozen=True)
class Case:
    case_id: str
    vehicle: Vehicle
    price: float
