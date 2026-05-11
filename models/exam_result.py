"""
Veri modeli tanımları.
Sınav sonuçlarını normalize edilmiş şekilde temsil eder.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SubjectScore:
    """Tek bir dersin skoru."""
    dogru: float = 0.0
    yanlis: float = 0.0
    net: float = 0.0


@dataclass
class StudentResult:
    """Tek bir öğrencinin bir sınavdaki sonuçları."""
    adi: str = ""
    soyadi: str = ""
    sinif: str = ""
    numara: str = ""

    turkce: SubjectScore = field(default_factory=SubjectScore)
    ink_tar: SubjectScore = field(default_factory=SubjectScore)
    din_kul: SubjectScore = field(default_factory=SubjectScore)
    ingilizce: SubjectScore = field(default_factory=SubjectScore)
    matematik: SubjectScore = field(default_factory=SubjectScore)
    fen_bil: SubjectScore = field(default_factory=SubjectScore)

    toplam_net: float = 0.0
    lgs_puan: float = 0.0

    class_rank: Optional[int] = None
    school_rank: Optional[int] = None
    district_rank: Optional[int] = None
    city_rank: Optional[int] = None
    general_rank: Optional[int] = None

    @property
    def full_name(self) -> str:
        return f"{self.adi} {self.soyadi}".strip()

    @property
    def hesaplanan_toplam_net(self) -> float:
        """Tüm derslerin netlerini topla."""
        return (
            self.turkce.net
            + self.ink_tar.net
            + self.din_kul.net
            + self.ingilizce.net
            + self.matematik.net
            + self.fen_bil.net
        )

    def get_subject_score(self, subject_key: str) -> SubjectScore:
        """Ders anahtarına göre skor döndür."""
        mapping = {
            "turkce": self.turkce,
            "ink_tar": self.ink_tar,
            "din_kul": self.din_kul,
            "ingilizce": self.ingilizce,
            "matematik": self.matematik,
            "fen_bil": self.fen_bil,
        }
        return mapping.get(subject_key, SubjectScore())


@dataclass
class ExamResult:
    """Bir sınavın tüm sonuçlarını temsil eder."""
    exam_name: str = ""
    exam_date: str = ""
    institution: str = ""
    source_file: str = ""
    detected_format: str = ""

    students: list = field(default_factory=list)  # list[StudentResult]

    @property
    def student_count(self) -> int:
        return len(self.students)

    @property
    def average_total_net(self) -> float:
        if not self.students:
            return 0.0
        return sum(s.toplam_net for s in self.students) / len(self.students)

    @property
    def average_lgs_puan(self) -> float:
        if not self.students:
            return 0.0
        return sum(s.lgs_puan for s in self.students) / len(self.students)
