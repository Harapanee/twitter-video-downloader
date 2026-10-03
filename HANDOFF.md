# HANDOFF — セッション間の引き継ぎ

> 新しいセッションはまずここを読む。**「いま何が進行中で、次に何をすべきか」だけ**を書く。
> 恒久的な規則は CLAUDE.md、変更の履歴は git / CHANGELOG に置き、ここには重複させない。
> 更新は作業を終えるたびに行い、古くなった項目は消す(積み上げない)。
> Stop フックが機械的に強制する: セッション中の変更やコミットがこのファイルより新しいと終了がブロックされる。
> 引き継ぐ内容が無いときは「最終更新」日付だけ更新すればよい。

最終更新: 2026-10-03

## いま進行中のこと

| 項目 | 状態 | 次の一手 |
|---|---|---|
| (なし) | | |

## 直近の知見(CLAUDE.md に入れたもの以外)

- **ローカル開発は `npx wrangler dev --persist-to ~/.cache/hozon-wrangler` で起動する**。
  assets.directory が `.`(ルート)なので、既定の `.wrangler/state` への書き込みを
  ファイル監視が拾い「Reloading local server...」が無限ループする(1リクエストで368回を実測)。
  `.assetsignore` はアップロード除外のみで監視は止めない。外に出せば0回。

- **localhost の「サーバー変換に失敗」は修正済み**(2026-10-03)。旧 server.py の `/convert` 前提だった
  `useServerConvert` を false 固定にし、ローカルも本番と同じブラウザ内変換に統一。DoodStream系は
  server.py(curl_cffi)依存だったため現在非対応。
- **gofile.run も Video Landing 系**(2026-10-03 追加)。Video Landing 系の着地ページは
  ワーカーの `ALLOWED_HOSTS_RE` にも入れること。入れないと `/proxy` が403 → 公開CORSプロキシ
  頼みになり(全滅して)解析が「読み込み中...」で止まる。
- **`video.twimg-image.com` は shield 系ではなく Video Landing (land-page API) 系**。
  名前が酷似する `video.twimg-image.cc` は暗号化 shield 系で**別物**。ホスト名から系統を
  推測せず、バンドルに `apiShieldInitPath` があるか / `app-api/flow/land-page/getInfo` を
  叩くかで判別すること。`LAND_PAGE_HOSTS` を正規表現化しないのはこのため。
- Video Landing 系のエントリバンドルは `assets/app-<hex>.js` から
  **`assets/index-<base64url>.js` (Vite) に移行済み**。gofile.host も移行しており、
  旧正規表現は両ホストで既に機能していなかった(`LAND_PAGE_BUNDLE_RE` で対応)。
- API origin はバンドル内で `hj(\`https://…\`, globalThis.window?.location?.origin||\`\`)`
  の第1引数として現れる。`discoverLandPageApiBase` の 2 番目のパターンがこれを拾う。
  現状の値はたまたま `LAND_PAGE_API_FALLBACK` と同一なので、フォールバックと
  区別して検証すること(実抽出できているのは確認済み)。
- 検証スクリプト(使い捨て): scratchpad の `verify_landpage.mjs` / `which_pattern.mjs`。
  実 HTML・実バンドルに対して正規表現を回す形。再検証時はこの形が早い。
