/**
 * FEELCYCLE 楽曲照合エンジン
 *
 * Apple Music / YouTube のプレイリストから貼り付けた行を、
 * songs.json の楽曲へ突き合わせてプログラムを特定する。
 * リミックス版は原曲へ解決する。
 *
 * index.html にそのまま読み込んで使う。Node でも動く（末尾のexport参照）。
 */

// ---------------------------------------------------------------- 正規化

// Python 側 merge_data.py の norm() と同じ規則にすること
function norm(s) {
  return (s || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/\((feat|ft)\..*?\)|\[(feat|ft)\..*?\]/g, ' ')
    .replace(/\b(feat|ft)\.\s*/g, 'feat ')
    .replace(/&/g, ' and ')
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// 動画タイトルに付く宣伝文句。リミックス表記は消さないよう限定的に列挙する。
const JUNK = new RegExp(
  '\\s*[\\(\\[]\\s*(' +
  'official\\s*(music\\s*)?(video|audio|visualizer|lyric[s]?|version)?|' +
  'music\\s*video|lyric[s]?( video)?|audio|visualizer|' +
  'hd|hq|4k|8k|full\\s*hd|mv|m/v|pv|' +
  'out\\s*now|free\\s*download|explicit|clean|' +
  'remaster(ed)?( \\d{4})?|\\d{4}\\s*remaster(ed)?|' +
  'color\\s*coded|han/rom/eng|eng\\s*sub' +
  ')\\s*[\\)\\]]', 'gi');

// リミックスを示す語（fetch_remixes.py と揃える）
const RE_REMIX = /\b(remix|rmx|bootleg|rework|refix|flip|vip|dub|extended|club|re-?work|mashup|mix)\b/i;
const RE_ORIGINAL = /\b(original\s*mix|album\s*version|single\s*version|radio\s*edit|explicit|clean|remaster(ed)?|live|acoustic|instrumental|karaoke|sped\s*up|slowed)\b/i;

/** 括弧内のリミックス表記などを外した「原曲名」 */
function baseTitle(title) {
  let t = (title || '').replace(JUNK, ' ');
  t = t.replace(/[\(\[][^\)\]]*[\)\]]/g, ' ');          // 残りの括弧を除去
  t = t.replace(/\s*[-–—]\s*[^-–—]*\b(remix|mix|edit|bootleg|version|rework|flip|vip)\b.*$/i, '');
  // 括弧に入っていない "ft. Sia" 形式の共演表記も落とす
  t = t.replace(/\s+\b(feat|ft|featuring|w\/|with)\b\.?\s+.*$/i, '');
  return norm(t);
}

/** リミックス版かどうか */
function isRemix(title) {
  const residual = (title || '').replace(RE_ORIGINAL, ' ');
  return RE_REMIX.test(residual);
}

/** リミックス名を取り出す */
function remixName(title) {
  const t = (title || '').replace(JUNK, ' ');
  for (const m of t.matchAll(/[\(\[]([^\)\]]*)[\)\]]/g)) {
    if (RE_REMIX.test(m[1].replace(RE_ORIGINAL, ' '))) return m[1].trim();
  }
  const d = t.match(/[-–—]\s*(.+\b(remix|mix|edit|bootleg|rework|flip|vip)\b.*)$/i);
  return d ? d[1].trim() : '';
}

// ------------------------------------------------- 入力行のパース

/**
 * 1行を {title, artist} へ。以下をすべて受け付ける。
 *   "Titanium\tDavid Guetta"           Apple Music書き出し(タブ区切り)
 *   "David Guetta - Titanium (Nicky Romero Remix)"   YouTube
 *   "Titanium - David Guetta"
 *   "Titanium / David Guetta"          FEELCYCLIST表記
 *   "Titanium"                         曲名だけ
 */
/**
 * "Artist - Title" を分解する。ただし右側が "Skrillex Remix" のような
 * バージョン表記の場合はアーティストではなくリミックス名として扱う。
 * 返り値: {title, artist} （分解できなければ artist は空）
 */
function splitHyphen(s) {
  const m = (s || '').match(/^(.+?)\s+[-–—]\s+(.+)$/);
  if (!m) return { title: (s || '').trim(), artist: '' };
  const left = m[1].trim(), right = m[2].trim();
  if (!/[-–—]/.test(right) &&
      RE_REMIX.test(right.replace(RE_ORIGINAL, ' ')) &&
      right.split(/\s+/).length <= 5) {
    return { title: `${left} (${right})`, artist: '' };
  }
  return { title: right, artist: left };
}

function parseLine(line) {
  let s = (line || '').trim();
  if (!s) return null;
  s = s.replace(/^\d+[\.\)]\s+/, '');          // 先頭の連番
  s = s.replace(/\s*[\(\[]?\d{1,2}:\d{2}[\)\]]?\s*$/, ''); // 末尾の再生時間

  if (s.includes('\t')) {
    const p = s.split('\t').map(x => x.trim());
    let title = p[0] || '';
    let channel = (p[1] || '').replace(/\s*-\s*Topic$/i, '');
    // 動画タイトル側の "Artist - Title" を優先する。
    // チャンネル名は VEVO 等で当てにならないため補助扱い。
    const d = splitHyphen(title);
    return { title: d.title, artist: d.artist || channel, raw: line,
             swappable: !!d.artist };
  }
  if (s.includes(' / ')) {
    const [a, b] = s.split(' / ');
    return { title: a.trim(), artist: b.trim(), raw: line };
  }
  const d = splitHyphen(s);
  return { title: d.title, artist: d.artist, raw: line, swappable: !!d.artist };
}

// ------------------------------------------------- 索引と照合

/** songs.json から索引を作る */
function buildIndex(songs) {
  const byBase = new Map();
  for (const s of songs) {
    const k = baseTitle(s.title);
    if (!k) continue;
    if (!byBase.has(k)) byBase.set(k, []);
    byBase.get(k).push(s);
  }
  return { byBase, keys: [...byBase.keys()] };
}

function tokens(s) { return new Set(norm(s).split(' ').filter(Boolean)); }

function jaccard(a, b) {
  if (!a.size || !b.size) return 0;
  let inter = 0;
  for (const x of a) if (b.has(x)) inter++;
  return inter / (a.size + b.size - inter);
}

/** アーティスト名の一致度。リミックスは別名義になりがちなので緩めに見る */
function artistScore(inputArtist, songArtist) {
  if (!inputArtist || !songArtist) return 0.5;      // 判断材料なし
  const a = tokens(inputArtist), b = tokens(songArtist);
  const j = jaccard(a, b);
  if (j > 0) return 0.5 + j * 0.5;
  for (const x of a) if (x.length > 3 && b.has(x)) return 0.7;
  return 0.15;
}

/**
 * 1件を照合する。
 * 返り値 match: 'exact' 完全一致 / 'base' リミックス→原曲 /
 *               'fuzzy' あいまい一致 / 'none' 該当なし
 */
function matchOne(input, index) {
  const remix = isRemix(input.title);
  const key = baseTitle(input.title);
  if (!key) return { input, match: 'none', candidates: [] };

  let pool = index.byBase.get(key) || [];
  let match = pool.length ? (remix ? 'base' : 'exact') : 'none';

  // 完全一致が無ければトークン類似で拾う
  if (!pool.length) {
    const kt = tokens(key);
    const scored = index.keys
      .map(k => ({ k, j: jaccard(kt, tokens(k)) }))
      .filter(x => x.j >= 0.6)
      .sort((a, b) => b.j - a.j)
      .slice(0, 3);
    if (scored.length) {
      pool = scored.flatMap(x => index.byBase.get(x.k));
      match = 'fuzzy';
    }
  }

  // アーティスト名で絞り込む。" - " の左右取り違えにも備える
  const cands = pool.map(s => {
    let sc = artistScore(input.artist, s.artist);
    if (input.swappable) {
      sc = Math.max(sc, artistScore(input.title, s.artist));
    }
    return { song: s, score: sc };
  }).sort((a, b) => b.score - a.score);

  if (!cands.length) return { input, match: 'none', candidates: [] };

  // アーティストが明確に食い違う場合は確度を落とす
  if (input.artist && cands[0].score <= 0.2 && match !== 'fuzzy') {
    match = 'fuzzy';
  }

  return {
    input,
    match,
    isRemix: remix,
    remixName: remix ? remixName(input.title) : '',
    song: cands[0].song,
    programs: cands[0].song.programs || [],
    alternatives: cands.slice(1, 4).map(c => c.song),
  };
}

/** テキストを丸ごと照合する */
function matchPlaylist(text, songs) {
  const index = buildIndex(songs);
  const seen = new Set();
  const results = [];
  for (const line of (text || '').split('\n')) {
    const p = parseLine(line);
    if (!p || !p.title) continue;
    const dedupe = norm(p.title) + '|' + norm(p.artist);
    if (seen.has(dedupe)) continue;
    seen.add(dedupe);
    results.push(matchOne(p, index));
  }
  const hit = results.filter(r => r.match !== 'none');
  return {
    results,
    summary: {
      total: results.length,
      matched: hit.length,
      viaRemix: results.filter(r => r.match === 'base').length,
      fuzzy: results.filter(r => r.match === 'fuzzy').length,
      none: results.filter(r => r.match === 'none').length,
      programs: [...new Set(hit.flatMap(r => r.programs.map(p => p.name)))],
    },
  };
}

if (typeof module !== 'undefined') {
  module.exports = { norm, baseTitle, isRemix, remixName, parseLine,
                     buildIndex, matchOne, matchPlaylist };
}
