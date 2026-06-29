"""
Tests for issue #121: splitIntoSentences() Thai text fallback.

The function lives in src/search/index.js. It previously split only on ASCII
terminators (. ! ?) — Thai text has no such terminators, so the entire chunk
was returned as a single "sentence", making selectBestPassage() useless for Thai.

AC (from issue body): Add a character-count fallback — when no sentence boundaries
are found OR the resulting sentence exceeds ~200 characters, split the text into
fixed-length sub-windows as an approximation of sentence boundaries for Thai.
"""

import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_MODULE = os.path.join(REPO_ROOT, "src", "search", "index.js")


def _extract_split_function():
    """Extract the sentence-splitting section (constants + helpers + splitIntoSentences)."""
    import re
    with open(SEARCH_MODULE) as f:
        src = f.read()
    # Grab from the section header comment through to (but not including) the
    # next async function — i.e., selectBestPassage.
    m = re.search(
        r"(// -{3,}\n// Sentence splitting.*?)(?=\nasync\s+function\s)",
        src,
        re.DOTALL,
    )
    assert m, "Sentence splitting section not found in src/search/index.js"
    return m.group(1)


def _run_split(text):
    """Call splitIntoSentences() via Node subprocess and return parsed result."""
    fn_src = _extract_split_function()
    test_script = f"""
{fn_src}
const result = splitIntoSentences({json.dumps(text)});
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=test_script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Node error (rc={result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# AC1 — Pure Thai text (no ASCII terminators) must be split into >1 sub-window
# ---------------------------------------------------------------------------

THAI_LONG = (
    "การค้นหาแบบเวกเตอร์ช่วยให้สามารถค้นหาความหมายแทนการจับคู่คำสำคัญ "
    "ซึ่งทำให้ผลลัพธ์มีความเกี่ยวข้องมากขึ้น แม้ว่าคำที่ใช้จะแตกต่างกัน "
    "ระบบใช้โมเดลการฝังข้อความเพื่อแปลงทั้งคำถามและเอกสารให้เป็นเวกเตอร์ "
    "จากนั้นจึงคำนวณความคล้ายคลึงระหว่างเวกเตอร์เหล่านั้น "
    "วิธีนี้ช่วยให้ระบบเข้าใจความตั้งใจของผู้ใช้ได้ดีกว่าการค้นหาแบบดั้งเดิม"
)


def test_ac1_thai_text_no_ascii_splits_into_multiple_windows():
    """
    AC1: Pure Thai text (no ASCII . ! ?) must produce more than 1 segment
    via the character-count fallback, so selectBestPassage has real options.
    """
    assert len(THAI_LONG) > 200, "Test input must exceed 200 chars to trigger fallback"
    sentences = _run_split(THAI_LONG)
    assert len(sentences) > 1, (
        f"splitIntoSentences() must split long Thai text into >1 sub-window; "
        f"got {len(sentences)} segment(s). "
        "Add a character-count fallback when no ASCII terminators are found."
    )


def test_ac1_thai_segments_are_non_empty():
    """AC1: Every sub-window produced for Thai text must have non-empty text."""
    sentences = _run_split(THAI_LONG)
    for i, s in enumerate(sentences):
        assert s["text"].strip(), (
            f"Segment {i} has empty text: {s!r}"
        )


# ---------------------------------------------------------------------------
# AC2 — A single sentence > 200 chars must also be sub-windowed
# ---------------------------------------------------------------------------

ASCII_LONG_NO_BOUNDARY = "a" * 250  # 250-char 'sentence' with no inner boundaries


def test_ac2_long_ascii_sentence_gets_split():
    """
    AC2: A sentence longer than the 200-char threshold must be split into
    sub-windows even when it starts with ASCII text, as long as no ASCII
    terminators subdivide it further.
    """
    sentences = _run_split(ASCII_LONG_NO_BOUNDARY)
    assert len(sentences) > 1, (
        f"A 250-char run with no sentence terminators must produce >1 sub-window "
        f"via the character-count fallback; got {len(sentences)} segment(s)."
    )


# ---------------------------------------------------------------------------
# AC3 — Fallback windows must carry correct start/end byte offsets
# ---------------------------------------------------------------------------

def test_ac3_thai_segment_offsets_are_consistent():
    """
    AC3: Each sub-window's (start, end) must match the position of its text
    inside the original string, so downstream offset-based highlighting works.
    """
    sentences = _run_split(THAI_LONG)
    for seg in sentences:
        text = seg["text"]
        start = seg["start"]
        end = seg["end"]
        assert end - start == len(text), (
            f"Offset mismatch: text len={len(text)}, start={start}, end={end} "
            f"(end-start={end-start}). Offsets must equal text length."
        )
        assert THAI_LONG[start:end] == text, (
            f"Segment text does not match original string slice at [{start}:{end}]. "
            f"Expected: {THAI_LONG[start:end]!r}, got: {text!r}"
        )


# ---------------------------------------------------------------------------
# AC4 — ASCII sentence splitting still works as before (regression guard)
# ---------------------------------------------------------------------------

ASCII_SENTENCES = "The dog barked. The cat ran. The bird flew."


def test_ac4_ascii_sentences_still_split_correctly():
    """
    AC4: Existing ASCII sentence splitting must be unaffected by the Thai
    fallback — three ASCII sentences must produce exactly 3 segments.
    """
    sentences = _run_split(ASCII_SENTENCES)
    texts = [s["text"] for s in sentences]
    assert len(sentences) == 3, (
        f"Expected 3 ASCII sentences, got {len(sentences)}: {texts}"
    )
    assert texts[0] == "The dog barked.", f"First sentence wrong: {texts[0]!r}"
    assert texts[1] == "The cat ran.", f"Second sentence wrong: {texts[1]!r}"
    assert texts[2] == "The bird flew.", f"Third sentence wrong: {texts[2]!r}"


def test_ac4_ascii_offsets_correct():
    """AC4: ASCII segment offsets must be correct after the Thai fallback is added."""
    sentences = _run_split(ASCII_SENTENCES)
    for seg in sentences:
        assert ASCII_SENTENCES[seg["start"]:seg["end"]] == seg["text"], (
            f"ASCII offset mismatch for segment: {seg!r}"
        )


# ---------------------------------------------------------------------------
# AC5 — Short text (< 200 chars, no terminator) stays as one segment
# ---------------------------------------------------------------------------

SHORT_THAI = "ค้นหา"  # 5 Thai characters, well under 200


def test_ac5_short_thai_text_stays_one_segment():
    """
    AC5: Thai text shorter than the fallback threshold must remain a single
    segment — the fallback must not over-fragment short inputs.
    """
    sentences = _run_split(SHORT_THAI)
    assert len(sentences) == 1, (
        f"Short Thai text (< 200 chars) must stay as 1 segment; "
        f"got {len(sentences)}: {sentences}"
    )
    assert sentences[0]["text"] == SHORT_THAI


# ---------------------------------------------------------------------------
# AC6 — splitIntoSentences is exported (or internally callable) from the module
# ---------------------------------------------------------------------------

def test_ac6_search_module_contains_fallback_logic():
    """
    AC6: src/search/index.js must contain character-count fallback logic
    referencing a threshold (≈200) or sub-window/window size constant.
    """
    import re
    with open(SEARCH_MODULE) as f:
        src = f.read()
    # Look for a numeric constant used as the sentence-length threshold
    has_threshold = bool(re.search(r"\b(1[5-9]\d|2[0-9]\d|300)\b", src))
    # Or look for window/chunk-based splitting logic inside splitIntoSentences
    has_window_split = bool(re.search(
        r"(SENTENCE_MAX|MAX_SENTENCE|WINDOW|window|fallback|subwindow)",
        src, re.IGNORECASE
    ))
    assert has_threshold or has_window_split, (
        "src/search/index.js must contain a character-count threshold or "
        "window/fallback constant for the Thai sentence-splitting fallback."
    )
