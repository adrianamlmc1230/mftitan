"""SignalGenerator 屬性測試。"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from core.signal import SignalGenerator


# Feature: football-quant-v2-refactor, Property 22: 訊號產生正確性
@given(
    guard=st.integers(min_value=0, max_value=3),
    strength=st.sampled_from([0, 1, 2, 3, 4]),
    pw=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    pl=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    t=st.floats(min_value=1.01, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_property22_signal_generation_correctness(guard, strength, pw, pl, t):
    """訊號產生正確性：
    - guard in (0, 3) → 訊號為空字串
    - Home 方向：pw > pl → 'A'，pl > pw → 'B'
    - Away 方向：pw < pl → 'A'，pl < pw → 'B'
    - 數值：strength==4→2, guard==2且ratio>t→1, guard==2且ratio≤t→0.5, guard==1→0.2
    """
    gen = SignalGenerator()

    # 測試 Home 方向 (greater)
    home_sig = gen.generate(guard, strength, pw, pl, t, "greater")
    # 測試 Away 方向 (less)
    away_sig = gen.generate(guard, strength, pw, pl, t, "less")

    if guard in (0, 3):
        assert home_sig == "", f"guard={guard} 時 Home 訊號應為空，得到 '{home_sig}'"
        assert away_sig == "", f"guard={guard} 時 Away 訊號應為空，得到 '{away_sig}'"
        return

    # guard 為 1 或 2 時應有訊號
    assert home_sig != "", f"guard={guard} 時 Home 訊號不應為空"
    assert away_sig != "", f"guard={guard} 時 Away 訊號不應為空"

    # 驗證方向字母
    # 注意：guard 不為 0 或 3 時，pw != pl（因為 guard=0 需要 pw==pl）
    # 但 strength 可能不匹配 guard，這裡只驗證 generate 的行為
    home_letter = home_sig[0]
    away_letter = away_sig[0]

    if pw > pl:
        assert home_letter == "A", f"Home: pw>pl 時應為 A，得到 {home_letter}"
        assert away_letter == "B", f"Away: pw>pl 時應為 B，得到 {away_letter}"
    elif pl > pw:
        assert home_letter == "B", f"Home: pl>pw 時應為 B，得到 {home_letter}"
        assert away_letter == "A", f"Away: pl>pw 時應為 A，得到 {away_letter}"
    # pw == pl 且 guard != 0 → 邊界情況，不額外驗證字母

    # 驗證數值部分
    home_val_str = home_sig[1:]
    home_val = float(home_val_str)

    if strength == 4:
        assert home_val == 2.0, f"strength=4 時數值應為 2，得到 {home_val}"
    elif guard == 2:
        max_val = max(pw, pl)
        min_val = min(pw, pl)
        ratio = max_val / min_val if min_val > 0 else float("inf")
        if ratio > t:
            assert home_val == 1.0, f"guard=2, ratio>t 時數值應為 1，得到 {home_val}"
        else:
            assert home_val == 0.5, f"guard=2, ratio<=t 時數值應為 0.5，得到 {home_val}"
    elif guard == 1:
        assert home_val == 0.2, f"guard=1 時數值應為 0.2，得到 {home_val}"
