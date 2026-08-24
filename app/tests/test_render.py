from datetime import date, datetime
from enum import Enum

import pytest

from src.utils.render import render_experience_content


class TestRenderExperienceContent:
    def test_renders_simple_fields(self):
        content = {
            "title": "미술사 연구",
            "description": "17세기 스페인 회화를 연구했다.",
        }

        result = render_experience_content(content)

        assert result == (
            "제목: 미술사 연구\n"
            "description: 17세기 스페인 회화를 연구했다."
        )

    def test_renders_title_as_korean_label(self):
        content = {
            "title": "전시 기획 프로젝트",
        }

        result = render_experience_content(content)

        assert result == "제목: 전시 기획 프로젝트"

    def test_renders_list_as_comma_separated_values(self):
        content = {
            "tags": [
                "미술사",
                "소논문",
                "17세기 스페인 회화",
                "무리요",
            ],
        }

        result = render_experience_content(content)

        assert result == (
            "tags: 미술사, 소논문, 17세기 스페인 회화, 무리요"
        )

    def test_does_not_render_list_as_python_or_json_representation(self):
        content = {
            "tags": [
                "미술사",
                "소논문",
                "무리요",
            ],
        }

        result = render_experience_content(content)

        assert result == "tags: 미술사, 소논문, 무리요"

        assert '["' not in result
        assert "['" not in result
        assert '"]' not in result
        assert "']" not in result

    def test_renders_date_range(self):
        content = {
            "연구 기간": {
                "start": "2024-10",
                "end": "2024-12",
            },
        }

        result = render_experience_content(content)

        assert result == "연구 기간: 2024-10 ~ 2024-12"

    def test_renders_range_with_only_start(self):
        content = {
            "period": {
                "start": "2024-10",
            },
        }

        result = render_experience_content(content)

        assert result == "period: 2024-10"

    def test_renders_range_with_only_end(self):
        content = {
            "period": {
                "end": "2024-12",
            },
        }

        result = render_experience_content(content)

        assert result == "period: 2024-12"

    def test_renders_nested_mapping(self):
        content = {
            "research-paper": {
                "주제": "17세기 스페인 회화",
                "연구자": "홍길동",
            },
        }

        result = render_experience_content(content)

        assert result == (
            "research paper:\n"
            "  주제: 17세기 스페인 회화\n"
            "  연구자: 홍길동"
        )

    def test_renders_nested_list(self):
        content = {
            "research": {
                "keywords": [
                    "미술사",
                    "무리요",
                    "바로크",
                ],
            },
        }

        result = render_experience_content(content)

        assert result == (
            "research:\n"
            "  keywords: 미술사, 무리요, 바로크"
        )

    def test_renders_deeply_nested_mapping(self):
        content = {
            "project": {
                "research": {
                    "period": {
                        "start": "2024-10",
                        "end": "2024-12",
                    },
                    "topics": [
                        "미술사",
                        "회화",
                    ],
                },
            },
        }

        result = render_experience_content(content)

        assert result == (
            "project:\n"
            "  research:\n"
            "    period: 2024-10 ~ 2024-12\n"
            "    topics: 미술사, 회화"
        )

    def test_omits_none_values(self):
        content = {
            "title": "연구",
            "description": None,
            "tags": ["미술사"],
        }

        result = render_experience_content(content)

        assert result == (
            "제목: 연구\n"
            "tags: 미술사"
        )

    def test_omits_empty_strings(self):
        content = {
            "title": "연구",
            "description": "",
            "summary": "   ",
        }

        result = render_experience_content(content)

        assert result == "제목: 연구"

    def test_omits_empty_lists(self):
        content = {
            "title": "연구",
            "tags": [],
        }

        result = render_experience_content(content)

        assert result == "제목: 연구"

    def test_omits_empty_mappings(self):
        content = {
            "title": "연구",
            "research": {},
        }

        result = render_experience_content(content)

        assert result == "제목: 연구"

    def test_preserves_false_values(self):
        content = {
            "is_completed": False,
        }

        result = render_experience_content(content)

        assert result == "is completed: 아니오"

    def test_preserves_zero_values(self):
        content = {
            "score": 0,
        }

        result = render_experience_content(content)

        assert result == "score: 0"

    def test_renders_true_as_korean_text(self):
        content = {
            "is_completed": True,
        }

        result = render_experience_content(content)

        assert result == "is completed: 예"

    def test_renders_datetime(self):
        value = datetime(2024, 10, 15, 13, 30, 0)

        content = {
            "created_at": value,
        }

        result = render_experience_content(content)

        assert result == "created at: 2024-10-15T13:30:00"

    def test_renders_date(self):
        content = {
            "date": date(2024, 10, 15),
        }

        result = render_experience_content(content)

        assert result == "date: 2024-10-15"

    def test_renders_mixed_list_values(self):
        content = {
            "items": [
                "미술사",
                123,
                True,
            ],
        }

        result = render_experience_content(content)

        assert result == "items: 미술사, 123, 예"

    def test_ignores_empty_items_inside_list(self):
        content = {
            "tags": [
                "미술사",
                None,
                "",
                "무리요",
            ],
        }

        result = render_experience_content(content)

        assert result == "tags: 미술사, 무리요"

    def test_normalizes_field_names(self):
        content = {
            "research_period": {
                "start_date": "2024-10",
                "end-date": "2024-12",
            },
        }

        result = render_experience_content(content)

        assert result == (
            "research period:\n"
            "  start date: 2024-10\n"
            "  end date: 2024-12"
        )

    def test_strips_whitespace_from_scalar_values(self):
        content = {
            "title": "  미술사 연구  ",
        }

        result = render_experience_content(content)

        assert result == "제목: 미술사 연구"

    def test_empty_content_returns_empty_string(self):
        content = {}

        result = render_experience_content(content)

        assert result == ""

    def test_rejects_non_mapping_content(self):
        with pytest.raises(TypeError, match="must be a mapping"):
            render_experience_content(["invalid", "content"])


class TestRenderExperienceContentRegression:
    """
    Regression tests for BAC-66.

    The AI must receive human-readable experience text rather than
    Python/JSON serialization of the underlying content structure.
    """

    def test_regression_tags_are_not_raw_json(self):
        content = {
            "tags": [
                "미술사",
                "소논문",
                "17세기 스페인 회화",
                "무리요",
            ],
        }

        result = render_experience_content(content)

        assert "tags: 미술사, 소논문, 17세기 스페인 회화, 무리요" in result

        assert "tags: [" not in result
        assert '["미술사"' not in result

    def test_regression_research_period_is_not_raw_json(self):
        content = {
            "research-paper": {
                "연구 기간": {
                    "start": "2024-10",
                    "end": "2024-12",
                },
            },
        }

        result = render_experience_content(content)

        assert "연구 기간: 2024-10 ~ 2024-12" in result

        assert '{"start"' not in result
        assert '"start":' not in result
        assert "'start':" not in result

    def test_regression_nested_content_contains_no_serialized_structures(self):
        content = {
            "title": "미술사 연구",
            "tags": [
                "미술사",
                "소논문",
            ],
            "research-paper": {
                "연구 기간": {
                    "start": "2024-10",
                    "end": "2024-12",
                },
                "keywords": [
                    "무리요",
                    "바로크",
                ],
            },
        }

        result = render_experience_content(content)

        assert "미술사, 소논문" in result
        assert "2024-10 ~ 2024-12" in result
        assert "무리요, 바로크" in result

        # No JSON/Python container syntax should reach the AI.
        assert "{" not in result
        assert "}" not in result
        assert "[" not in result
        assert "]" not in result
        assert '":' not in result
        assert "':" not in result