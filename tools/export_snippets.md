# プレイリスト書き出しスニペット

いずれもブラウザのConsoleに貼り付けて実行します。
`playlist.txt` がダウンロードされるので、サイトの照合欄に貼り付けてください。

---

## Apple Music（自分のライブラリのプレイリスト）

`https://music.apple.com/jp/library/playlists` を開いて実行します。
ライブラリを読むには developer token に加えて **media-user-token**（ログイン
状態を示すCookie）が必要です。ログイン済みなら自動で拾えます。

```js
(async()=>{
const dev=(()=>{try{const x=window.MusicKit?.getInstance?.()?.developerToken;if(x)return x}catch(e){}
for(const m of document.querySelectorAll('meta[name*="environment"]')){try{const x=JSON.parse(decodeURIComponent(m.content))?.MEDIA_API?.token;if(x)return x}catch(e){}}})();
const usr=document.cookie.split('; ').find(c=>c.startsWith('media-user-token='))?.split('=')[1];
console.log('developer token:',dev?'OK':'NG','/ media-user-token:',usr?'OK':'NG');
if(!dev||!usr)return console.warn('Apple Musicにログインした状態で実行してください');
const B='https://amp-api.music.apple.com',H={Authorization:`Bearer ${dev}`,'Music-User-Token':usr};
const api=async u=>{const r=await fetch(u.startsWith('http')?u:B+u,{headers:H});
if(!r.ok){console.warn(r.status,u,(await r.text()).slice(0,200));return null}return r.json()};

// 1) プレイリスト一覧
const pls=[];let n='/v1/me/library/playlists?limit=100';
while(n){const j=await api(n);if(!j)break;
(j.data||[]).forEach(p=>pls.push({id:p.id,name:p.attributes?.name||''}));
n=j.next||null}
console.log('ライブラリのプレイリスト:');pls.forEach((p,i)=>console.log(`  [${i}] ${p.name}`));
if(!pls.length)return;

// 2) 対象を選ぶ（番号をカンマ区切り。空Enterで全部）
const ans=prompt('書き出す番号をカンマ区切りで（空欄なら全部）','');
const pick=ans&&ans.trim()?ans.split(',').map(x=>pls[+x.trim()]).filter(Boolean):pls;

// 3) 曲を集める
const out=[];
for(const p of pick){
let u=`/v1/me/library/playlists/${p.id}/tracks?limit=100`;
while(u){const j=await api(u);if(!j)break;
(j.data||[]).forEach(t=>{const a=t.attributes||{};
out.push(`${a.name||''}\t${a.artistName||''}`)});
u=j.next||null;await new Promise(s=>setTimeout(s,150))}
console.log(`  ${p.name}: 計 ${out.length}`)}

const a=document.createElement('a');
a.href=URL.createObjectURL(new Blob([out.join('\n')],{type:'text/plain'}));
a.download='playlist.txt';a.click();
console.log('書き出し完了:',out.length,'曲');})();
```

うまくいかない場合の代替手段: MacのミュージックAppで
**ファイル → ライブラリ → プレイリストを書き出す** を選ぶと、
タブ区切りテキストが得られます。そのまま貼り付けて使えます。

---

## YouTube / YouTube Music の再生リスト

再生リストのページを開き、**一番下までスクロールしてから**実行します
（YouTubeは表示範囲だけを描画するため、スクロールしないと全件取れません）。

```js
(()=>{
const rows=[...document.querySelectorAll(
 'ytd-playlist-video-renderer, ytd-playlist-video-list-renderer #contents > *, ' +
 'ytmusic-responsive-list-item-renderer')];
const out=[];
for(const el of rows){
const t=el.querySelector('#video-title, .title')?.textContent.trim();
if(!t)continue;
const c=el.querySelector('ytd-channel-name #text, .secondary-flex-columns yt-formatted-string')
        ?.textContent.trim()||'';
out.push(c?`${t}\t${c}`:t)}
const uniq=[...new Set(out)];
console.log('取得:',uniq.length,'曲');
console.log(uniq.slice(0,5).join('\n'));
const a=document.createElement('a');
a.href=URL.createObjectURL(new Blob([uniq.join('\n')],{type:'text/plain'}));
a.download='playlist.txt';a.click();})();
```

取得件数が再生リストの曲数より明らかに少ない場合は、スクロール不足です。
`End` キー長押しで最下部まで送ってから再実行してください。

---

## 照合エンジンが受け付ける形式

`matcher.js` は以下をすべて解釈します。手打ちや他サービスからの
コピペでも、だいたいそのまま通ります。

| 入力例 | 解釈 |
|---|---|
| `Titanium⇥David Guetta` | 曲名＋アーティスト |
| `David Guetta - Titanium ft. Sia (Nicky Romero Remix)` | リミックス → 原曲へ解決 |
| `Levels - Skrillex Remix` | 右側をリミックス名として認識 |
| `Wake Me Up (Official Video)` | 宣伝文句を除去 |
| `5. Something Just Like This 3:42` | 連番と再生時間を除去 |
| `Aperture / Harry Styles` | FEELCYCLIST表記 |
| `Titanium` | 曲名のみ |
