# -*- coding: utf-8 -*-
"""
アーティスト名の表記ゆれ吸収

Deezer / Apple Music / FEELCYCLIST でアーティスト名が英語表記と日本語表記に
割れるため、カタカナを発音の近いローマ字へ変換してから突き合わせる。
  スティング -> sutingu  と  sting  を同一視する。

完全な音写は目指さない。「同じアーティストか」を判定できる程度の粗さで足りる。
"""

import difflib
import re
import unicodedata

# 2文字の拗音を先に処理する必要があるので、長いキーから順に適用する
KANA = {
    "キャ": "kya", "キュ": "kyu", "キョ": "kyo", "シャ": "sha", "シュ": "shu",
    "ショ": "sho", "チャ": "cha", "チュ": "chu", "チョ": "cho", "ニャ": "nya",
    "ニュ": "nyu", "ニョ": "nyo", "ヒャ": "hya", "ヒュ": "hyu", "ヒョ": "hyo",
    "ミャ": "mya", "ミュ": "myu", "ミョ": "myo", "リャ": "rya", "リュ": "ryu",
    "リョ": "ryo", "ギャ": "gya", "ギュ": "gyu", "ギョ": "gyo", "ジャ": "ja",
    "ジュ": "ju", "ジョ": "jo", "ビャ": "bya", "ビュ": "byu", "ビョ": "byo",
    "ピャ": "pya", "ピュ": "pyu", "ピョ": "pyo",
    "ウィ": "wi", "ウェ": "we", "ウォ": "wo", "ヴァ": "va", "ヴィ": "vi",
    "ヴェ": "ve", "ヴォ": "vo", "ヴュ": "vyu", "ファ": "fa", "フィ": "fi",
    "フェ": "fe", "フォ": "fo", "フュ": "fyu", "ティ": "ti", "ディ": "di",
    "トゥ": "tu", "ドゥ": "du", "チェ": "che", "シェ": "she", "ジェ": "je",
    "ツァ": "tsa", "ツィ": "tsi", "ツェ": "tse", "ツォ": "tso",
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヲ": "o", "ン": "n", "ヴ": "vu",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o",
    "ャ": "ya", "ュ": "yu", "ョ": "yo", "ッ": "", "ー": "",
}
_KEYS = sorted(KANA, key=len, reverse=True)
_PAT = re.compile("|".join(re.escape(k) for k in _KEYS))


# 冠詞や役割語は共通しやすく、これだけで一致とみなすと誤判定になる
STOP = {"the", "and", "feat", "ft", "featuring", "with", "dj", "mc",
        "of", "de", "la", "le", "los", "las", "el", "official", "band",
        "music", "project", "group"}


def strip_accents(s):
    """
    Beyoncé -> Beyonce のようにラテン文字のアクセント記号だけ落とす。
    日本語の濁点・半濁点は意味を持つ（デ と テ は別）ので残す。
    """
    out = []
    for ch in unicodedata.normalize("NFKD", s or ""):
        if unicodedata.combining(ch) and out and ord(out[-1]) < 0x3000:
            continue
        out.append(ch)
    return unicodedata.normalize("NFKC", "".join(out))


def drop_stopwords(s):
    words = re.split(r"[^\w]+", s or "")
    return " ".join(w for w in words if w and w.lower() not in STOP)


def romaji(s):
    """カタカナを含む文字列をローマ字寄りに変換する。"""
    s = unicodedata.normalize("NFKC", s or "")
    # ひらがなはカタカナに寄せる
    s = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)
    return _PAT.sub(lambda m: KANA[m.group(0)], s)


# 音写のぶれを吸収するための単純化。
# 日本語表記は語尾の子音が落ちたり母音が挿入されたりするので、
# 子音の骨格だけを残して類似度で比較する。
def phonetic(s):
    s = romaji(strip_accents(drop_stopwords(s))).lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    for a, b in (("l", "r"), ("v", "b"), ("c", "k"), ("q", "k"),
                 ("x", "ks"), ("j", "z"), ("y", "")):
        s = s.replace(a, b)
    s = re.sub(r"[aiueo]", "", s)            # 母音を落とす
    s = re.sub(r"(.)\1+", r"\1", s)          # 連続する同じ文字を1つに
    return s


def tokens(s):
    """表記に依存しないアーティスト語の集合。"""
    s = romaji(strip_accents(drop_stopwords(s))).lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return {w for w in s.split() if len(w) > 1}


def phonetic_v(s):
    """母音を残した版。短い名前は子音だけだと情報が足りないため併用する。"""
    s = romaji(strip_accents(drop_stopwords(s))).lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    for a, b in (("l", "r"), ("v", "b"), ("c", "k"), ("q", "k"),
                 ("x", "ks"), ("j", "z")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


SIMILAR = 0.8
SIMILAR_V = 0.8

# 音写の乖離が大きく機械的には照合できない組。気づいたら足していく。
ALIASES = [
    ("beyonce", "ビヨンセ"),
    ("the beatles", "ビートルズ"),
    ("queen", "クイーン"),
    ("michael jackson", "マイケル・ジャクソン"),
    ("guns n roses", "ガンズ・アンド・ローゼズ"),
    ("earth wind fire", "アース・ウィンド・アンド・ファイアー"),
    ("black eyed peas", "ブラック・アイド・ピーズ"),
    ("red hot chili peppers", "レッド・ホット・チリ・ペッパーズ"),
    ("linkin park", "リンキン・パーク"),
    ("bon jovi", "ボン・ジョヴィ"),
]
_ALIAS_KEY = {}
for _en, _ja in ALIASES:
    _k = f"__alias{len(_ALIAS_KEY)}"
    _ALIAS_KEY[_en] = _k
    _ALIAS_KEY[_ja] = _k


def _alias(s):
    """対応表に載っている名前なら共通のキーを返す。"""
    n = strip_accents(unicodedata.normalize("NFKC", s or "")).lower()
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    for k, v in _ALIAS_KEY.items():
        kk = re.sub(r"[^\w\s]", " ", strip_accents(k).lower())
        kk = re.sub(r"\s+", " ", kk).strip()
        if kk and kk in n:
            return v
    return None


def same_artist(a, b):
    """
    同じアーティストとみなせるか。
    1) 語の一致（英語同士・日本語同士）
    2) 子音の骨格の類似（スティング と Sting、カルヴィン・ハリス と Calvin Harris）
    """
    ka, kb = _alias(a), _alias(b)
    if ka and kb:
        return ka == kb

    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    # 2文字の語（Ed, Lil など）は共通しやすいので、それだけでは決めない
    if {t for t in ta & tb if len(t) >= 3}:
        return True

    pa, pb = phonetic(a), phonetic(b)
    if min(len(pa), len(pb)) >= 3:
        # 連名（"Sting & Shaggy" と "スティング"）は包含で拾う
        if pa in pb or pb in pa:
            return True
        if difflib.SequenceMatcher(None, pa, pb).ratio() >= SIMILAR:
            return True
    # 子音だけでは情報が足りない名前（Avicii, Rihanna など）は母音込みで見る
    va, vb = phonetic_v(a), phonetic_v(b)
    if min(len(va), len(vb)) >= 4 and \
            difflib.SequenceMatcher(None, va, vb).ratio() >= SIMILAR_V:
        return True
    # 語単位でも見る。片方の語がもう片方の語と近ければ同一とみなす。
    for x in ta:
        px, vx = phonetic(x), phonetic_v(x)
        for y in tb:
            py, vy = phonetic(y), phonetic_v(y)
            if min(len(px), len(py)) >= 3 and \
                    difflib.SequenceMatcher(None, px, py).ratio() >= 0.85:
                return True
            if min(len(vx), len(vy)) >= 4 and \
                    difflib.SequenceMatcher(None, vx, vy).ratio() >= 0.85:
                return True
    return False


if __name__ == "__main__":
    cases = [
        ("Sting", "スティング", True),
        ("Gregory Porter", "グレゴリー・ポーター", True),
        ("Havana Brown", "ハヴァナ・ブラウン", True),
        ("David Guetta", "デヴィッド・ゲッタ", True),
        ("Calvin Harris", "カルヴィン・ハリス", True),
        ("Avicii", "アヴィーチー", True),
        ("Ed Sheeran", "エド・シーラン", True),
        ("Sting & Shaggy", "スティング", True),
        ("Queen", "Basstrologe", False),
        ("Justin Bieber", "Victoria La Mala", False),
        ("Zombie Nation", "Agenda", False),
        ("Nelly", "Benjamin Milic", False),
        ("Bruno Mars", "ブルーノ・マーズ", True),
        ("Beyoncé", "ビヨンセ", True),
        ("The Beatles", "ビートルズ", True),
        ("Skrillex", "スクリレックス", True),
        ("Maroon 5", "マルーン5", True),
        ("Eminem", "エミネム", True),
        ("Rihanna", "リアーナ", True),
        ("Coldplay", "コールドプレイ", True),
        ("Drake", "ドレイク", True),
        ("Alesso", "Avicii", False),
        ("Kygo", "Martin KO", False),
        ("Madonna", "マドンナ", True),
        ("Sia", "Zedd", False),
        ("The Beatles", "The Beach Boys", False),
        ("Beyoncé", "Beyond", False),
        ("Bon Jovi", "Jon Bellion", False),
        ("The Weeknd", "The Chainsmokers", False),
        ("DJ Snake", "DJ Khaled", False),
        ("Ed Sheeran", "Ed Solo", False),
    ]
    ok = 0
    for a, b, exp in cases:
        got = same_artist(a, b)
        ok += got == exp
        print(f"  {'OK ' if got == exp else 'NG '}{a:<18}{b:<22}"
              f"期待={exp} 判定={got}   [{phonetic(a)} / {phonetic(b)}]")
    print(f"\n{ok}/{len(cases)} 一致")
