"""中文檔名解析器（舊版，保留向後相容）。

新版解析器在 core/filename_parser.py，不再拆分國家和聯賽名。
此檔案僅供舊程式碼參考，建議使用 core.filename_parser.FilenameParser。
"""

import logging
import os
import re

from core.models import ParsedFilename

logger = logging.getLogger(__name__)

FILENAME_PATTERN = re.compile(
    r"^(?P<prefix>.+?)"
    r"(?P<year>\d{4}(?:-\d{4})?)"
    r"(?P<phase>第.+?階段)"
    r"(?P<timing>早|即)"
    r"(?P<play>亞讓|大小)"
    r"\.xlsx$"
)

TIMING_MAP = {"早": "Early", "即": "RT"}
PLAY_TYPE_MAP = {"亞讓": "HDP", "大小": "OU"}


def parse_filename(
    filepath: str, known_league_names: list[str] | None = None
) -> ParsedFilename | None:
    """解析 RPA 中文檔名，回傳結構化資訊。解析失敗回傳 None。"""
    if not filepath:
        return None

    basename = os.path.basename(filepath)
    if not basename.endswith(".xlsx"):
        return None

    match = FILENAME_PATTERN.match(basename)
    if not match:
        return None

    prefix = match.group("prefix")
    year = match.group("year")
    phase = match.group("phase")
    timing_zh = match.group("timing")
    play_zh = match.group("play")

    return ParsedFilename(
        name_zh=prefix,  # 完整中文名，不拆分
        season_year=year,
        phase=phase,
        timing=TIMING_MAP[timing_zh],
        play_type=PLAY_TYPE_MAP[play_zh],
        original_path=filepath,
    )
