# コードとデータの分離

コードの取得・変更と、データの取得・更新を独立して行います。データの場所は `src/paths.py` だけが解決し、数値計算の共通関数はファイルを読まない `src/model_math.py` にあります。加工スクリプトを import しても取得・加工・保存は始まりません。

## 配置

```text
hinomoto-twin-pub/              コードリポジトリ
  src/                         取得・加工・推定・検証・抽出
  catalog/                     出典、取得用の表定義、入力形式、固定版のハッシュ
  site/                        HTML/JavaScript。分布データ本体は含まない
  tests/                       小さな人工データで実行する契約テスト
  dist/site/                   配信用の組み立て結果（Git管理外）

hinomoto-twin-data/             データルート（別フォルダ・別リポジトリ・マウント先でも可）
  raw/                         原表と取得レスポンス
  sources/                     正規化済み入力
  data/                        モデル・配布用データ・推定例
  validation/                  計算・検証・感度分析の結果
  web/graph.json               公開ページ用の版付きデータ
```

省略時のデータルートはコードリポジトリの隣の `hinomoto-twin-data` です。作業ディレクトリを移動しても変わりません。

```sh
export HINOMOTO_DATA_ROOT="/path/to/hinomoto-twin-data"
make paths
```

入力だけ共有し、結果を別の場所に作ることもできます。正規化済み入力はビルド時に書き換えません。

```sh
python src/pipeline.py build \
  --sources-dir /datasets/japan-2020-2022/sources \
  --output-dir /runs/experiment-a/data \
  --reports-dir /runs/experiment-a/validation

python src/pipeline.py verify \
  --sources-dir /datasets/japan-2020-2022/sources \
  --output-dir /runs/experiment-a/data \
  --reports-dir /runs/experiment-a/validation

python src/persona_v2.py --data-dir /runs/experiment-a/data \
  --municipality 13103 --age 35 --income-only
```

環境変数は `HINOMOTO_RAW_DIR`、`HINOMOTO_SOURCES_DIR`、`HINOMOTO_OUTPUT_DIR`、`HINOMOTO_REPORTS_DIR`、`HINOMOTO_WEB_DIR` に対応します。すべての既存スクリプトから利用できます。

JSON設定は `config.example.json` をコピーして用意し、`HINOMOTO_CONFIG=/path/to/config.local.json` または `pipeline.py --config` で指定します。キーは `data_root`、`raw_dir`、`sources_dir`、`output_dir`、`reports_dir`、`web_dir` です。JSON内の相対パスは設定ファイルの場所が基準です。環境変数・コマンドラインの相対パスは実行時の作業ディレクトリが基準です。個別パスはデータルートより優先し、同じキーではコマンドライン、環境変数、JSON、省略値の順です。

## 初回取得と移行

新規利用ではコードとは別にデータを取得します。

```sh
make dataset       # 固定版の正規化済み入力・公開ページ用データを取得
make build         # 外部データだけを読み、外部データへ結果を保存
make verify
```

移行前の一体型フォルダが手元にある場合は、そのまま取り込めます。

```sh
export HINOMOTO_DATA_ROOT="/path/to/new-data-root"
python src/dataset.py migrate --from /path/to/legacy-checkout
```

移行はコピーで行い、元ファイルを削除しません。同じ保存先に異なる内容がある場合は停止します。移行元と保存先が同じ、または保存先が移行元データディレクトリの配下の場合も停止します。

`make dataset` は移行用の初期版として、分離直前のコミットを固定したアーカイブから許可されたデータだけを取り込みます。旧コードは取り出さず、実行しません。各ファイルのSHA-256を `catalog/baseline.json` と照合します。旧HTMLから取り出す公開ページ用データもこの検証対象です。データ専用の配布先をまだ作っていなくても、新規利用とGitHub Pagesの再配信を継続できるようにしています。過去のGit履歴を削除する変更はしません。

元の政府統計から再取得する場合は `make install-source` と `make fetch`、取得済み原表からの加工は `make prepare` です。

## データの受け渡しと互換性

```sh
# 正規化済み入力と画面用データを、コードを含まないアーカイブにする
python src/dataset.py pack /path/to/japan-2020-2022.tar.gz

# 別の保存先・別のコードチェックアウトで取り込む
HINOMOTO_DATA_ROOT=/another/data-root \
  python src/dataset.py import /path/to/japan-2020-2022.tar.gz

python src/dataset.py check
```

アーカイブの `dataset.json` は形式バージョンとファイル別ハッシュを持ちます。取り込み時はハッシュと保存先を検証し、異なる既存ファイルを上書きしません。生の原表、計算済みの巨大な配列、実行ごとの検証結果はこの入力アーカイブに含めません。

正規化済みCSVの契約は `catalog/source_schema.json` です。ビルドの入口でファイルと列を確認します。これは現在の日本統計モデル用の入力契約であり、任意の属性数・地域体系のデータを自動的に扱うものではありません。コード先頭の0、対象年、所得定義などの意味は `SOURCES.md` と各METHOD文書に従います。新しい年次や属性を追加するときは、形式と統計的な対応の両方を検証してください。

## 公開ページ

画面は `data/graph.json` を非同期に読み込みます。形式は `schema_version`（1〜3）、`dataset_version`、`graph` のオブジェクトです。schema 3 では `graph.emp` に段階A（就業状態・地位・産業）の全国・都道府県パラメータと、`data/employment_inputs.bin`（市区町村 × 性別 × 年齢の周辺 27 値、float32）、`data/employment/agg_<code>.bin`（全国・都道府県・政令市の集計ブロック、float32）のファイル名と SHA-256 を持ち、画面はそれらを必要時に取得します。形式の詳細は `catalog/employment_schema.json`。schema 2 のデータでは段階Aのノードは「未配信」と表示されます。`graph.workplace` があれば、市区町村パネルの「勤務地を見る」で `data/workplace/o_<code>.json`（居住する人の勤務地）と `d_<code>.json`（働きに来る人の居住地）を読み込みます（形式は `catalog/workplace_schema.json`）。`graph.household` があれば、対象市区町村の `data/household/<code>.json`（段階Bの世帯構成の要約）を市区町村パネルから読み込みます。`?data=https://example.org/graph.json` で別の配信先も指定できます（別ドメインでは配信元のCORS設定が必要）。読み込み失敗時は画面に案内を表示します。

```sh
make site
python -m http.server 8000 --directory dist/site
```

`build_site.py --graph /path/to/graph.json --output /path/to/site` で配置先も変更できます。GitHub Pagesは同じ組み立て手順で `dist/site` を配信します。

画面用データは独立した配布物です。`make build` が生成するNPZ/CSVとは別であり、この変更では既存の公開版の画面用データをそのまま分離しています。モデルを変更した場合に `make site` だけで新しい画面用分布が生成されるわけではありません。新しい画面用データの作成・検証と `dataset_version` の更新を行い、明示的に差し替えてください。画面内の解説と数値例もモデル版に対応しているため、別版を公開する際は説明の整合性を確認してください。

## 2026-09-07 属性公開版

`2020-2022-3.0-M12-20260907+A+B-trial` は段階Aの就業状態・地位・産業と、段階Bの港区・那覇市・遠軽町の試験世帯要約を同梱します。M12の既存5属性の配列と地理集計は従来公開版から変更していません。段階Aの未観測関連はモデルの仮定であり、世帯内所得相関は未推定です。試験世帯の分母は一般世帯の構成員で、個人モデルの常住人口とは異なります。勤務地のExplorer公開は含みません。

採用判断：PR #27/#28 の検証とレビューを踏まえ、上記の限界を明示して公開します。全国1,896地域の入力整合、ブラウザとPythonの比較、既存5属性の配列一致を確認しています。ロールバックは `catalog/production.json` を直前の `data-v3.0-m12-20260906` のURL・ハッシュに戻して再配信します。

## 2026-09-07 勤務地公開版

`2020-2022-3.0-M12-20260907+A+B-trial+C` は段階Cの勤務地パネルを試験公開します。居住側では産業と段階Aの年齢・性別・学歴・地位を条件にし、流入側は産業のみ対応します。非就業者には勤務地を定義しません。条件付き人数は段階Aの人数に勤務地既知率を掛けた推定で、国勢調査の全就業者数と区別します。居住地・勤務地・産業の条件付き独立、検証対象290地域以外の限界は docs/WORKPLACE_C.md を参照してください。勤務地を条件にした所得分布は提供しません。既存5属性・段階A・試験世帯のデータは変更していません。

PR #25/#29 の検証とレビューを踏まえ上記範囲で採用。固定版の参照は catalog/production.json。ロールバックは前版 data-v3.0-m12-ab-20260907 のURL・ハッシュへ戻して再配信します。

中間成果物：所得モデルの工程（status / mixture / calibrate / finalize）は `data/stages/*.npz` を順に読み書きし、各ファイルの `provenance` に入力の指紋・上流の SHA-256・係数・コード commit を持ちます。不一致の成果物は読み込まれません。工程・コマンド・容量は `docs/PIPELINE.md` を参照してください（固定版アーカイブには同梱しません）。
