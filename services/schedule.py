from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Exam:
    subject: str
    component: str
    unit_code: str
    paper_code: str
    board: str
    level: str
    date: date | None
    date_label: str
    session: str | None
    duration: str | None
    start_time: str | None
    end_time: str | None
    extra_time_minutes: int | None
    end_time_with_extra: str | None
    venue: str | None
    seat: str | None

    @property
    def sort_key(self) -> tuple[int, date, str]:
        if self.date is None:
            return (1, date.max, self.subject)
        return (0, self.date, self.subject)

    @property
    def days_until(self) -> int | None:
        if self.date is None:
            return None
        return (self.date - date.today()).days

    @property
    def label(self) -> str:
        return f"{self.subject} - {self.component}"


def load_exams(path: Path) -> list[Exam]:
    raw_exams = json.loads(path.read_text(encoding="utf-8"))
    return [parse_exam(item) for item in raw_exams]


def parse_exam(item: dict[str, Any]) -> Exam:
    exam_date = None
    if item.get("date"):
        exam_date = datetime.strptime(item["date"], "%Y-%m-%d").date()

    return Exam(
        subject=item["subject"],
        component=item["component"],
        unit_code=item["unit_code"],
        paper_code=item["paper_code"],
        board=item["board"],
        level=item["level"],
        date=exam_date,
        date_label=item["date_label"],
        session=item["session"],
        duration=item["duration"],
        start_time=item["start_time"],
        end_time=item["end_time"],
        extra_time_minutes=item["extra_time_minutes"],
        end_time_with_extra=item["end_time_with_extra"],
        venue=item["venue"],
        seat=item["seat"],
    )


def subjects_from_exams(exams: list[Exam]) -> list[str]:
    return sorted({exam.subject for exam in exams})


def exams_for_subject(exams: list[Exam], subject: str) -> list[Exam]:
    return sorted(
        [exam for exam in exams if exam.subject == subject],
        key=lambda exam: exam.sort_key,
    )


def upcoming_exams(exams: list[Exam], limit: int = 8) -> list[Exam]:
    scheduled = [exam for exam in exams if exam.date is not None and exam.days_until is not None]
    return sorted(scheduled, key=lambda exam: exam.sort_key)[:limit]
